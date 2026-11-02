"""Shared pieces for the voice tests: stubbed model clients, never the network."""
import json
import os
import re
import struct
import unittest
from contextlib import contextmanager

from app import store, voice as voice_mod, voice_flow
from app.tests.helpers import AppTestCase, csrf_token

NOW_MONTH = "2026-11"


def make_wav(seconds=1, rate=16000, channels=1, bits=16, fmt=1):
    """A silent WAV with the given header fields."""
    data_len = int(rate * seconds) * channels * (bits // 8)
    header = b"RIFF" + struct.pack("<I", 36 + data_len) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, fmt, channels, rate,
                                    rate * channels * bits // 8, channels * bits // 8, bits)
    header += b"data" + struct.pack("<I", data_len)
    return header + b"\x00" * data_len


class ScriptedExtraction:
    """Returns the scripted replies in order and records every call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def extract(self, text):
        self.calls.append(text)
        if not self.replies:
            raise AssertionError("unexpected extraction call for %r" % text)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class ScriptedTranscription:
    def __init__(self, *transcripts):
        self.transcripts = list(transcripts)
        self.audio = []

    def transcribe(self, wav):
        self.audio.append(wav)
        return self.transcripts.pop(0), {}


@contextmanager
def stub_clients(extraction=None, transcription=None):
    old = (getattr(voice_mod, "EXTRACTION_CLIENT", None), getattr(voice_mod, "TRANSCRIBE_CLIENT", None))
    voice_mod.EXTRACTION_CLIENT = extraction
    voice_mod.TRANSCRIBE_CLIENT = transcription
    try:
        yield
    finally:
        voice_mod.EXTRACTION_CLIENT, voice_mod.TRANSCRIBE_CLIENT = old


def update(kind, language="pt", **fields):
    reply = {"intent": "update", "kind": kind, "language": language}
    reply.update(fields)
    return reply


class VoiceTestCase(AppTestCase):
    """A signed-in agent with settings saved, a fixed month and no model calls."""

    def setUp(self):
        super().setUp()
        self._old_month = os.environ.get("APP_NL_CURRENT_MONTH")
        os.environ["APP_NL_CURRENT_MONTH"] = NOW_MONTH
        self.addCleanup(self._restore_month)
        voice_flow.CONVERSATIONS.clear()
        self.save_settings()
        self.tenant = store.get_tenant_by_email(self.db_path, "test@example.com")["id"]

    def _restore_month(self):
        if self._old_month is None:
            os.environ.pop("APP_NL_CURRENT_MONTH", None)
        else:
            os.environ["APP_NL_CURRENT_MONTH"] = self._old_month

    def page_token(self, lang="pt-PT"):
        return csrf_token(self.client.get("/", accept_language=lang).body)

    def voice(self, path, token, accept_language="pt-PT", **fields):
        params = {"csrf_token": token, "format": "json"}
        params.update(fields)
        response = self.client.request("POST", path, params=params, accept_language=accept_language)
        self.assertEqual(response.code, 200, response.body[:300])
        self.assertIn("application/json", response.headers["content-type"])
        return json.loads(response.body)

    def deals(self):
        return store.list_deals(self.db_path, tenant_id=self.tenant)

    def add_deal(self, name, commission=1000000, rate="0.4", date="2026-12-15", status="active",
                 stage="confirmado", estimated=0, key=None):
        return store.insert_deal(self.db_path, {
            "name": name, "agency": "", "escritura_date": date, "month": date[:7],
            "stage": stage, "status": status, "cpcv_date": None,
            "agency_commission_cents": commission, "share_rate": "40",
            "part_base": int(commission * float(rate)), "share_rate_used": rate,
            "iva_rate": "0.23", "retencao_rate": "0.25", "irs_rate": "0.3", "ss_rate": "0.1",
            "expenses_cents": 35000, "idempotency_key": key or "seed-" + name,
            "tenant_id": self.tenant, "escritura_estimada": estimated,
        }, tenant_id=self.tenant)

