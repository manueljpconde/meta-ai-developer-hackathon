"""Real server journeys over HTTP with the standard library (rules S1, S2, criterion 8).

A server runs on a free port and urllib drives it the way the page does:
request a link, open it, save settings, create a deal, read the forecast,
run the voice conversation with the same requests the script sends, edit
and delete. Extraction and transcription are stubbed; nothing leaves the
machine.
"""
import http.cookiejar
import json
import os
import re
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from wsgiref.simple_server import WSGIRequestHandler, make_server

from app import i18n, mail, store, voice_flow, web
from app.server import ThreadingWSGIServer
from app.tests.voice_support import ScriptedExtraction, ScriptedTranscription, make_wav, stub_clients, update


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class Browser:
    """urllib with a cookie jar, like one browser tab."""

    def __init__(self, port):
        self.base = "http://127.0.0.1:%d" % port
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),  # talk to the local server directly, never through a proxy
            urllib.request.HTTPCookieProcessor(self.jar))

    def open(self, path, data=None, headers=None, accept_language=None):
        request = urllib.request.Request(self.base + path, data=data, headers=dict(headers or {}))
        if accept_language:
            request.add_header("Accept-Language", accept_language)
        with self.opener.open(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()

    def get(self, path, accept_language=None):
        status, headers, body = self.open(path, accept_language=accept_language)
        return status, body.decode("utf-8")

    def post(self, path, params, accept_language=None):
        data = urllib.parse.urlencode(params).encode("utf-8")
        status, headers, body = self.open(
            path, data, {"Content-Type": "application/x-www-form-urlencoded"}, accept_language)
        return status, headers, body.decode("utf-8")

    def post_wav(self, path, wav):
        status, headers, body = self.open(path, wav, {"Content-Type": "audio/wav"})
        return json.loads(body)


def token_in(body):
    return re.search(r'name="csrf_token" value="([^"]+)"', body).group(1)


def spoken_tone_wav(seconds, amplitude):
    """A 16 kHz mono 16-bit WAV of alternating ±amplitude samples."""
    n = int(16000 * seconds)
    samples = [int(amplitude * 32767) if i % 2 == 0 else -int(amplitude * 32767)
               for i in range(n)]
    data = struct.pack("<%dh" % n, *samples)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16) +
            b"data" + struct.pack("<I", len(data)) + data)


class RealServerTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = tmp.name + "/journey.db"
        self.old_db, web.DB_PATH = web.DB_PATH, self.db
        self.addCleanup(setattr, web, "DB_PATH", self.old_db)
        self.old_month = os.environ.get("APP_NL_CURRENT_MONTH")
        os.environ["APP_NL_CURRENT_MONTH"] = "2026-11"
        self.addCleanup(self.restore_month)
        mail.OUTBOX = []
        self.addCleanup(setattr, mail, "OUTBOX", None)
        voice_flow.CONVERSATIONS.clear()
        self.server = make_server("127.0.0.1", 0, web.application, server_class=ThreadingWSGIServer,
                                  handler_class=QuietHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.browser = Browser(self.server.server_address[1])

    def restore_month(self):
        if self.old_month is None:
            os.environ.pop("APP_NL_CURRENT_MONTH", None)
        else:
            os.environ["APP_NL_CURRENT_MONTH"] = self.old_month

    def sign_in(self, email, lang):
        b = self.browser
        status, page = b.get("/signin")
        self.assertEqual(status, 200)
        token = token_in(page)
        b.post("/language", {"lang": lang, "csrf_token": token})
        status, page = b.get("/signin")
        status, headers, body = b.post("/signin", {"email": email, "csrf_token": token_in(page)})
        self.assertEqual(status, 200)
        [mail_sent] = mail.OUTBOX
        self.assertEqual(mail_sent["to"], email)
        status, home = b.get(mail_sent["link"].split("127.0.0.1")[-1] if "127.0.0.1" in mail_sent["link"]
                             else "/auth/verify?token=" + mail_sent["link"].split("token=")[1])
        self.assertEqual(status, 200)
        self.assertIn('id="voicePanel"', home, "signed in after opening the link")
        return home

    def save_settings(self, lang):
        b = self.browser
        status, page = b.get("/settings")
        expenses = "350,00" if lang == "pt-PT" else "350.00"
        status, headers, body = b.post("/settings", {
            "csrf_token": token_in(page), "share": "40", "iva": "23", "retencao": "25", "irs": "30",
            "ss": "10", "expenses": expenses, "form_locale": lang})
        self.assertEqual(status, 200)

    def tenant(self, email):
        return store.get_tenant_by_email(self.db, email)["id"]


class RealServerVoiceJourney(RealServerTestCase):
    def journey(self, lang, code, email):
        b = self.browser
        self.sign_in(email, lang)
        self.save_settings(lang)

        # The script and the stylesheet come from the same server.
        status, script = b.get("/static/voice.js")
        self.assertEqual(status, 200)
        self.assertIn("/voice/extract", script)

        # Create a deal by the form: commission 10 000 EUR, share 40 %.
        status, form = b.get("/deals/new")
        comm = "10000,00" if lang == "pt-PT" else "10000.00"
        status, headers, review = b.post("/deals/review", {
            "csrf_token": token_in(form), "name": "Journey Deal", "commission": comm, "share": "40",
            "escritura_date": "2026-11-20", "month": "2026-11", "stage": "confirmado", "agency": "",
            "form_locale": lang})
        mine = Decimal("10000") * Decimal("0.4")
        shown = "4\u00a0000,00 €".replace("\u00a0", " ") if lang == "pt-PT" else "€4,000.00"
        self.assertIn(shown, review)
        params = dict(re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', review))
        params = {n: v.replace("&amp;", "&") for n, v in params.items()}
        status, headers, home = b.post("/deals/confirm", params)
        self.assertEqual(status, 200)
        self.assertIn("Journey Deal", home)
        self.assertIn(shown, home)
        self.assertEqual(int(mine * 100), store.list_deals(self.db, tenant_id=self.tenant(email))[0]["part_base"])

        # The voice conversation: the requests the script sends, in order.
        extraction = ScriptedExtraction(
            update("new_deal", code, name="T1 Alvalade", stage="confirmado", escritura_date="março"),
            update("new_deal", code, commission="10000", share="40"))
        with stub_clients(extraction):
            status, page = b.get("/", accept_language=lang)
            token = token_in(page)

            def send(path, **fields):
                fields.update(csrf_token=token, format="json")
                status, headers, body = b.post(path, fields)
                self.assertEqual(status, 200)
                self.assertIn("application/json", headers["Content-Type"])
                return json.loads(body)

            first = send("/voice/extract", conversation_id="",
                         text="Novo negócio T1 em Alvalade, escritura lá para março")
            expected = ("Qual é a comissão e a tua percentagem?" if code == "pt"
                        else "What is the commission and your share?")
            self.assertEqual((first["state"], first["question"]), ("ask", expected))
            self.assertEqual(len(store.list_deals(self.db, tenant_id=self.tenant(email))), 1)

            second = send("/voice/extract", conversation_id=first["conversation_id"],
                          text="10 000 euros e 40 %")
            self.assertEqual(second["state"], "confirm")
            self.assertEqual(second["conversation_id"], first["conversation_id"])
            marker = "(estimada)" if code == "pt" else "(estimated)"
            self.assertIn(marker, second["readback"])
            self.assertTrue(second["readback"].endswith("Confirmas?" if code == "pt" else "Do you confirm?"))
            self.assertEqual(len(store.list_deals(self.db, tenant_id=self.tenant(email))), 1, "nothing stored before the yes")

            done = send("/voice/extract", conversation_id=second["conversation_id"],
                        text="sim" if code == "pt" else "yes")
            self.assertEqual(done["state"], "saved")

        deals = store.list_deals(self.db, tenant_id=self.tenant(email))
        saved = [d for d in deals if d["name"] == "T1 Alvalade"]
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0]["escritura_date"], saved[0]["escritura_estimada"], saved[0]["part_base"]),
                         ("2027-03-15", 1, 400000))
        status, forecast = b.get("/?month=2027-03", accept_language=lang)
        self.assertIn("T1 Alvalade", forecast)
        self.assertIn(marker, forecast)
        self.assertIn(shown, forecast)

        # Edit the first deal, then delete it.
        did = deals[0]["id"]
        status, form = b.get("/deals/edit?id=%d" % did)
        status, headers, home = b.post("/deals/update?id=%d" % did, {
            "csrf_token": token_in(form), "name": "Journey Deal Edited", "commission": comm, "share": "40",
            "escritura_date": "2026-12-05", "stage": "confirmado", "agency": "", "status": "active",
            "form_locale": lang})
        self.assertIn("Journey Deal Edited", home)
        status, confirm = b.get("/deals/delete?id=%d" % did)
        status, headers, home = b.post("/deals/delete?id=%d" % did, {"csrf_token": token_in(confirm)})
        self.assertNotIn("Journey Deal Edited", home)

    def test_journey_pt(self):
        self.journey("pt-PT", "pt", "pt-agent@example.com")

    def test_journey_en(self):
        self.journey("en-GB", "en", "en-agent@example.com")


class RealServerMicrophoneAndConfirmJourney(RealServerTestCase):
    def test_spoken_turn_with_a_wav_body_then_the_confirm_button_saves(self):
        b = self.browser
        self.sign_in("mic@example.com", "en-GB")
        self.save_settings("en-GB")
        extraction = ScriptedExtraction(update("new_deal", "en", name="T2 Mic", stage="likely".replace("likely", "provavel"),
                                               commission="9000", share="50", escritura_date="2026-12-09"))
        transcription = ScriptedTranscription("new deal T2 Mic")
        wav = make_wav(1)
        with stub_clients(extraction, transcription):
            status, page = b.get("/", accept_language="en-GB")
            token = token_in(page)
            spoken = b.post_wav("/voice/transcribe?format=json&conversation_id=&csrf_token=" + token, wav)
            self.assertEqual(spoken["state"], "confirm")
            self.assertEqual(spoken["transcript"], "new deal T2 Mic")
            self.assertEqual(transcription.audio, [wav])
            self.assertEqual(store.count_deals(self.db), 0)
            status, headers, body = b.post("/voice/confirm", {
                "csrf_token": token, "format": "json", "conversation_id": spoken["conversation_id"]})
            self.assertEqual(json.loads(body)["state"], "saved")
        [deal] = store.list_deals(self.db, tenant_id=self.tenant("mic@example.com"))
        self.assertEqual((deal["name"], deal["part_base"]), ("T2 Mic", 450000))

    def test_a_correction_and_an_exact_date_over_http(self):
        """Criteria (15) and (16) on the real server, with the requests the script sends."""
        b = self.browser
        self.sign_in("fix@example.com", "en-GB")
        self.save_settings("en-GB")
        extraction = ScriptedExtraction(
            update("new_deal", "en", name="T4 Estrela", stage="confirmado", commission="10000", share="40",
                   escritura_date="2026-12-20", escritura_estimada=True),
            update("new_deal", "en"),
            update("new_deal", "en"),
            update("new_deal", "en", share="30"))
        with stub_clients(extraction):
            status, page = b.get("/", accept_language="en-GB")
            token = token_in(page)

            def send(path, **fields):
                fields.update(csrf_token=token, format="json")
                status, headers, body = b.post(path, fields)
                self.assertEqual(status, 200)
                return json.loads(body)

            first = send("/voice/extract", conversation_id="",
                         text="New deal T4 Estrela, 10000, 40 percent, the escritura is exact, 20 December 2026")
            self.assertEqual(first["state"], "confirm")
            self.assertNotIn("estimated", first["readback"])
            self.assertIn("Dec 20", first["readback"])
            # a correction that extraction returns nothing for is asked again, never read back unchanged
            lost = send("/voice/extract", conversation_id=first["conversation_id"],
                        text="No, my share is minus 40 percent")
            self.assertEqual((lost["state"], lost["question"]), ("ask", "What is your share?"))
            self.assertEqual(store.count_deals(self.db), 0)
            # a spoken yes after an unapplied correction saves nothing
            refused = send("/voice/extract", conversation_id=lost["conversation_id"], text="yes")
            self.assertNotEqual(refused["state"], "saved")
            self.assertEqual(store.count_deals(self.db), 0)
            fixed = send("/voice/extract", conversation_id=lost["conversation_id"], text="30 percent")
            self.assertEqual(fixed["state"], "confirm")
            self.assertIn("30%", fixed["readback"])
            self.assertIn("your share €3,000", fixed["readback"])
            self.assertEqual(store.count_deals(self.db), 0)
            done = send("/voice/extract", conversation_id=fixed["conversation_id"], text="yes")
            self.assertEqual(done["state"], "saved")
        [deal] = store.list_deals(self.db, tenant_id=self.tenant("fix@example.com"))
        self.assertEqual((deal["share_rate_used"], deal["part_base"], deal["escritura_date"],
                          deal["escritura_estimada"]), ("0.3", 300000, "2026-12-20", 0))
        status, forecast = b.get("/?month=2026-12", accept_language="en-GB")
        self.assertIn("T4 Estrela", forecast)
        self.assertNotIn("(estimated)", forecast)

    def test_cancel_over_http_saves_nothing_and_cancel_is_not_a_page_replacement(self):
        b = self.browser
        self.sign_in("cancel@example.com", "pt-PT")
        self.save_settings("pt-PT")
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T3 Cancel", stage="provavel"))
        with stub_clients(extraction):
            status, page = b.get("/")
            token = token_in(page)
            status, headers, body = b.post("/voice/extract", {"csrf_token": token, "format": "json", "text": "novo T3 Cancel"})
            cid = json.loads(body)["conversation_id"]
            status, headers, body = b.post("/voice/cancel", {"csrf_token": token, "format": "json", "conversation_id": cid})
        data = json.loads(body)
        self.assertEqual((data["state"], data["message"]), ("cancelled", "Cancelado. Nada foi guardado."))
        self.assertEqual(store.count_deals(self.db), 0)


class RealServerRefusalDiagnostic(RealServerTestCase):
    """The owner's V3 ruling over real HTTP: a truncated or invalid body is
    unavailable — duration and peak are both null, shown as dashes — while the
    over-limit branch keeps today's behaviour (duration from the header, peak
    null, body not read)."""

    def transcribe(self, wav, lang="en-GB"):
        b = self.browser
        status, page = b.get("/", accept_language=lang)
        url = ("/voice/transcribe?format=json&conversation_id=&csrf_token=%s"
               "&sample_rate=48000" % token_in(page))
        return b.post_wav(url, wav)

    def test_an_invalid_body_over_http_is_refused_with_duration_and_peak_null(self):
        self.sign_in("invalid-body@example.com", "en-GB")
        self.save_settings("en-GB")
        invalid = bytearray(spoken_tone_wav(1, 0.5))
        invalid[0:4] = b"NOPE"
        data = self.transcribe(bytes(invalid))
        self.assertEqual(data["state"], "error")
        self.assertEqual(data["message"], i18n.text("en-GB", "voice_wav_error"))
        self.assertEqual(data["diagnostic"], {"sample_rate": 48000,
                                              "duration_seconds": None,
                                              "peak": None})
        self.assertEqual(store.count_deals(self.db), 0)

    def test_a_truncated_body_over_http_is_refused_with_duration_and_peak_null(self):
        self.sign_in("truncated-body@example.com", "en-GB")
        self.save_settings("en-GB")
        truncated = spoken_tone_wav(1, 0.5)[:-2000]
        # the header still declares a full second of audio
        declared = struct.unpack_from("<I", truncated, 40)[0]
        self.assertEqual(declared, 32000)
        data = self.transcribe(truncated)
        self.assertEqual(data["state"], "error")
        self.assertEqual(data["message"], i18n.text("en-GB", "voice_wav_error"))
        self.assertEqual(data["diagnostic"], {"sample_rate": 48000,
                                              "duration_seconds": None,
                                              "peak": None})
        self.assertEqual(store.count_deals(self.db), 0)

    def test_an_over_limit_body_over_http_keeps_the_header_duration_and_null_peak(self):
        self.sign_in("over-limit@example.com", "en-GB")
        self.save_settings("en-GB")
        data = self.transcribe(spoken_tone_wav(62, 0.5))
        self.assertEqual(data["state"], "error")
        self.assertEqual(data["diagnostic"], {"sample_rate": 48000,
                                              "duration_seconds": 62.0,
                                              "peak": None})


if __name__ == "__main__":
    unittest.main()
