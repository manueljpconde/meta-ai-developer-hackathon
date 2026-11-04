"""The two model clients as they leave the box (criteria 9, 11, 12), with urlopen stubbed.

Nothing here reaches the network: urllib.request.urlopen is replaced by a
recorder that returns a canned answer.
"""
import email
import email.policy
import io
import json
import unittest
from unittest import mock

from app import voice as voice_mod
from app import voice_flow as vf
from app.tests.voice_support import make_wav


def setUpModule():
    global _old_month
    import os
    _old_month = os.environ.get("APP_NL_CURRENT_MONTH")
    os.environ["APP_NL_CURRENT_MONTH"] = "2026-11"


def tearDownModule():
    import os
    if _old_month is None:
        os.environ.pop("APP_NL_CURRENT_MONTH", None)
    else:
        os.environ["APP_NL_CURRENT_MONTH"] = _old_month


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        return FakeResponse(self.payload)


def parse_multipart(request):
    content_type = request.get_header("Content-type")
    raw = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + request.data
    return email.message_from_bytes(raw, policy=email.policy.HTTP)


class TranscriptionRequestTest(unittest.TestCase):
    def send(self, base=None):
        recorder = Recorder({"sessionId": "s-1", "transcript": "um CPCV foi assinado", "audioDurationMs": 1000,
                             "turns": []})
        client = voice_mod.TranscriptionClient(api_key="secret-key", api_base=base)
        with mock.patch("urllib.request.urlopen", recorder):
            transcript, raw = client.transcribe(make_wav(1))
        [(request, timeout)] = recorder.requests
        return request, timeout, transcript, raw

    def test_posts_to_asr_transcribe_with_a_bearer_key_and_never_audio_transcriptions(self):
        request, timeout, transcript, raw = self.send("https://api.meta.ai/v1")
        self.assertEqual(request.full_url, "https://api.meta.ai/v1/asr/transcribe")
        self.assertNotIn("audio/transcriptions", request.full_url)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")
        self.assertEqual((transcript, raw["audioDurationMs"], raw["turns"]), ("um CPCV foi assinado", 1000, []))

    def test_the_base_url_comes_from_the_environment_or_defaults(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("META_API_BASE_URL", None)
            request, *_ = self.send()
            self.assertEqual(request.full_url, "https://api.meta.ai/v1/asr/transcribe")
            os.environ["META_API_BASE_URL"] = "https://example.invalid/v9/"
            request, *_ = self.send()
            self.assertEqual(request.full_url, "https://example.invalid/v9/asr/transcribe")

    def test_the_body_is_multipart_form_data_of_exactly_two_parts(self):
        request, *_ = self.send("https://api.meta.ai/v1")
        self.assertTrue(request.get_header("Content-type").startswith("multipart/form-data; boundary="))
        message = parse_multipart(request)
        parts = list(message.iter_parts())
        self.assertEqual([p.get_param("name", header="content-disposition") for p in parts], ["request", "audio"])
        self.assertEqual([p.get_content_type() for p in parts], ["application/json", "audio/wav"])

    def test_the_request_part_is_the_model_and_audio_encoding_wav_and_nothing_else(self):
        request, *_ = self.send("https://api.meta.ai/v1")
        part = list(parse_multipart(request).iter_parts())[0]
        body = json.loads(part.get_payload(decode=True))
        self.assertEqual(body, {"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV"})
        self.assertNotIn("LINEAR16", request.data.decode("latin-1"))
        self.assertNotIn("sampleRateHertz", request.data.decode("latin-1"))

    def test_the_audio_part_is_the_wav_bytes_unchanged(self):
        request, *_ = self.send("https://api.meta.ai/v1")
        part = list(parse_multipart(request).iter_parts())[1]
        self.assertEqual(part.get_payload(decode=True), make_wav(1))

    def test_a_failure_is_a_model_error_not_a_guess(self):
        import urllib.error
        client = voice_mod.TranscriptionClient(api_key="k", api_base="https://api.meta.ai/v1")
        for failure in (urllib.error.HTTPError("u", 404, "no", {}, io.BytesIO(b"")), OSError("down")):
            with mock.patch("urllib.request.urlopen", side_effect=failure):
                with self.assertRaises(voice_mod.ModelError):
                    client.transcribe(make_wav(1))
        with mock.patch("urllib.request.urlopen", Recorder(b"not json")):
            with self.assertRaises(voice_mod.ModelError):
                client.transcribe(make_wav(1))


class ExtractionRequestTest(unittest.TestCase):
    def extract(self, content, text="Un CPCV do T3 em Benfica foi assinado hoje."):
        recorder = Recorder({"choices": [{"message": {"content": content}}]})
        client = voice_mod.ExtractionClient(api_key="secret-key", api_base="https://api.meta.ai/v1")
        with mock.patch("urllib.request.urlopen", recorder):
            result = client.extract(text)
        return recorder.requests[0], result

    def test_posts_chat_completions_with_model_muse_spark_and_a_timeout_of_at_least_30_seconds(self):
        (request, timeout), result = self.extract(
            '{"kind": "cpcv_signed", "deal": "T3 Benfica", "date": "2026-11-01"}')
        self.assertEqual(request.full_url, "https://api.meta.ai/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")
        self.assertGreaterEqual(timeout, 30)
        body = json.loads(request.data)
        self.assertEqual(body["model"], "muse-spark-1.3")
        self.assertEqual(body["messages"][-1], {"role": "user", "content": "Un CPCV do T3 em Benfica foi assinado hoje."})
        self.assertEqual(result, {"kind": "cpcv_signed", "deal": "T3 Benfica", "date": "2026-11-01"})

    def test_the_prompt_names_every_field_the_flow_reads(self):
        for word in ("intent", "language", "new_deal", "cpcv_signed", "escritura_date", "fell_through",
                     "commission_received", "change_stage", "change_commission", "change_percentage", "reopen",
                     "commission", "share", "percentage", "amount", "stage", "deal", "name", "YYYY-MM"):
            self.assertIn(word, voice_mod.EXTRACTION_PROMPT)

    def test_anything_but_one_json_object_is_a_model_error_with_the_manual_path_open(self):
        client = voice_mod.ExtractionClient(api_key="k", api_base="https://api.meta.ai/v1")
        for content in ("sure! here you go", "```json\n{}\n```", "", "{broken"):
            with self.subTest(content=content):
                with mock.patch("urllib.request.urlopen",
                                Recorder({"choices": [{"message": {"content": content}}]})):
                    with self.assertRaises(voice_mod.ModelError):
                        client.extract("x")
        with mock.patch("urllib.request.urlopen", Recorder({"unexpected": True})):
            with self.assertRaises(voice_mod.ModelError):
                client.extract("x")

    def test_small_transcription_errors_are_tolerated_by_deal_matching(self):
        deals = [{"id": 1, "name": "T3 Benfica"}, {"id": 2, "name": "T2 Estrela"}]
        self.assertEqual([d["id"] for d in vf.match_deals("t3 benfica", deals)], [1])
        self.assertEqual([d["id"] for d in vf.match_deals("o T3 em Benfica", deals)], [1])
        self.assertEqual([d["id"] for d in vf.match_deals("Benfica", deals)], [1])


class MoneyPathTest(unittest.TestCase):
    def test_every_euro_in_the_read_back_comes_from_engine_calc(self):
        from engine.calc import agent_share
        for commission, share in ((1000000, "0.4"), (123457, "0.35"), (99999, "0.5")):
            conv = {"kind": "new_deal", "lang": "pt-PT", "deal_id": None,
                    "extracted": {"name": "T", "commission": commission, "share": share,
                                  "escritura_date": "2026-12-15", "stage": "confirmado"}}
            line, mine = vf.readback(conv, None, "en-GB")
            self.assertEqual(mine, agent_share(commission, share))
            self.assertIn(vf.format_euros(mine, "en-GB"), line)

    def test_model_supplied_euro_fields_are_never_used_as_the_share(self):
        conv = {"kind": "new_deal", "lang": "pt-PT", "deal_id": None, "extracted": {}}
        vf.merge_extraction(conv, {"name": "T", "commission": "10000", "share": "40",
                                   "part_base": 999999, "agent_share": 999999, "mine": 999999,
                                   "escritura_date": "2026-12-15", "stage": "confirmado"})
        self.assertNotIn("part_base", conv["extracted"])
        self.assertNotIn("mine", conv["extracted"])
        _, mine = vf.readback(conv, None, "pt-PT")
        self.assertEqual(mine, 400000)

    def test_money_and_rates_are_parsed_exactly(self):
        self.assertEqual(vf.parse_money("10 000 euros"), 1000000)
        self.assertEqual(vf.parse_money("10.000,50 €"), 1000050)
        self.assertEqual(vf.parse_money("€10,000.50"), 1000050)
        self.assertEqual(vf.parse_money(10000), 1000000)
        self.assertIsNone(vf.parse_money("muito"))
        self.assertIsNone(vf.parse_money(-5))
        self.assertEqual(vf.parse_rate("40 %"), "0.4")
        self.assertEqual(vf.parse_rate("0,35"), "0.35")
        self.assertEqual(vf.parse_rate("12,5 por cento"), "0.125")
        self.assertIsNone(vf.parse_rate("sem percentagem"))

    def test_dates(self):
        self.assertEqual(vf.parse_date("2026-12-15"), ("2026-12-15", False))
        self.assertEqual(vf.parse_date("2027-03"), ("2027-03-15", True))
        self.assertEqual(vf.parse_date("ainda não está marcada, mas deve ser em março"), ("2027-03-15", True))
        self.assertEqual(vf.parse_date("sometime in December"), ("2026-12-15", True))
        self.assertEqual(vf.parse_date("2026-02-31"), (None, False))
        self.assertEqual(vf.parse_date("em breve"), (None, False))

    def test_a_cpcv_or_receipt_needs_the_exact_day(self):
        conv = {"kind": "cpcv_signed", "extracted": {}}
        vf.merge_extraction(conv, {"deal": "T3", "date": "março"})
        self.assertEqual(vf.missing_for("cpcv_signed", conv["extracted"]), ["date"])


if __name__ == "__main__":
    unittest.main()
