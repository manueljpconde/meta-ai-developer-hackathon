"""Item 4f: V2, V3 and U1 to U9 (V1 is in test_voice_audio).

The image has no browser and no JavaScript engine, so the page script and the
stylesheet are checked as served (steps, wiring, rules at the stated widths) and
every number the page shows is computed independently here, in integer cents.
"""
import json
import os
import pathlib
import re
import sqlite3
import struct
import unittest

from app import i18n, voice_audio
from app.tests.helpers import AppTestCase
from app.tests.voice_support import (ScriptedExtraction, ScriptedTranscription, VoiceTestCase,
                                     make_wav, stub_clients, update)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "static" / "voice.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
LANGS = ("pt-PT", "en-GB")


def css_rules(text):
    """[(media or '', selector, declarations)] for plain rules and one level of @media."""
    rules = []

    def block(chunk, media):
        pos = 0
        while pos < len(chunk):
            open_at = chunk.find("{", pos)
            if open_at == -1:
                break
            head = chunk[pos:open_at].strip()
            depth, end = 1, open_at + 1
            while depth and end < len(chunk):
                depth += {"{": 1, "}": -1}.get(chunk[end], 0)
                end += 1
            inner = chunk[open_at + 1:end - 1]
            if head.startswith("@media"):
                block(inner, head[len("@media"):].strip())
            elif not head.startswith("@"):
                for selector in head.split(","):
                    rules.append((media, " ".join(selector.split()), re.sub(r"\s+", "", inner)))
            pos = end

    block(re.sub(r"/\*.*?\*/", "", text, flags=re.S), "")
    return rules


def declarations(selector, media=""):
    """All declarations of a selector under a media condition, later ones last."""
    out = ""
    for m, s, d in css_rules(CSS):
        if s == selector and re.sub(r"\s+", "", m) == re.sub(r"\s+", "", media):
            out += d + ";"
    return out


def euros(cents, lang):
    whole, rest = divmod(cents, 100)
    if lang == "pt-PT":
        grouped = "{:,}".format(whole).replace(",", " ")
        return "%s,%02d €" % (grouped, rest)
    return "€%s.%02d" % ("{:,}".format(whole), rest)


def whole_euros(cents, lang):
    return euros(cents, lang).replace(",00 €", " €") if lang == "pt-PT" else euros(cents, lang)[:-3]


def deal_money(commission_cents, share_percent, iva=23, retencao=25, irs=30, ss=10):
    """One deal's bank inflow and money to set aside in cents, worked out here (no engine call)."""
    part = commission_cents * share_percent // 100
    iva_c = part * iva // 100
    ret_c = part * retencao // 100
    irs_reserve = max(part * irs // 100 - ret_c, 0)
    ss_c = part * ss // 100
    return {"part": part, "bank": part + iva_c - ret_c, "aside": iva_c + irs_reserve + ss_c,
            "iva": iva_c, "irs": irs_reserve, "ss": ss_c}


class ServedPage:
    """Helpers to read the strip and the cards out of the served home page."""

    @staticmethod
    def strip(body):
        found = re.search(r'<div class="forecast-strip">(.*?)</div></div>(?=<div class="forecast-grid">)', body, re.S)
        return found.group(0) if found else None

    @staticmethod
    def item(strip, css):
        found = re.search(r'<div class="strip-item %s">(.*?)</div>' % css, strip, re.S)
        label = re.search(r'<span class="strip-label"[^>]*>(.*?)</span>', found.group(1)).group(1)
        value = re.search(r'<strong class="strip-value">(.*?)</strong>', found.group(1)).group(1)
        note = re.search(r'<small class="strip-note">(.*?)</small>', found.group(1))
        return label, value, note.group(1) if note else ""

    @staticmethod
    def card_lines(body, month_label, key):
        """The amount a month card shows for a label key's text."""
        card = re.search(r"<section><h2>%s</h2>(.*?)</section>" % re.escape(month_label), body, re.S).group(1)
        return re.search(r'data-i18n="%s">[^<]*</dt><dd>([^<]*)</dd>' % key, card).group(1)


class StripBase(VoiceTestCase, ServedPage):
    """Settings: IVA 23, retencao 25, IRS 30, SS 10, expenses 350 a month (the test helper's defaults)."""

    TODAY = "2026-11-10"

    def setUp(self):
        super().setUp()
        self._old_today = os.environ.get("APP_NL_TODAY")
        os.environ["APP_NL_TODAY"] = self.TODAY
        self.addCleanup(self._restore_today)

    def _restore_today(self):
        if self._old_today is None:
            os.environ.pop("APP_NL_TODAY", None)
        else:
            os.environ["APP_NL_TODAY"] = self._old_today

    def home(self, lang="pt-PT"):
        return self.client.get("/", accept_language=lang).body


# ── V2 ───────────────────────────────────────────────────────────────

class RefusalMessagesTest(VoiceTestCase):
    """V2: every refusal shows its reason; only a request that never arrived says 'No connection'."""

    def panel_attr(self, lang, name):
        body = self.client.get("/", accept_language=lang).body
        return re.search(r'<div id="voicePanel"[^>]*\b%s="([^"]*)"' % name, body).group(1)

    def test_the_three_messages_exist_in_both_languages_as_page_attributes(self):
        expected = {
            "pt-PT": {"data-too-long": "Áudio demasiado longo.",
                      "data-server-refused": "O servidor recusou o pedido. Tenta outra vez.",
                      "data-network-error": "Sem ligação. Tenta outra vez."},
            "en-GB": {"data-too-long": "Audio too long.",
                      "data-server-refused": "The server refused the request. Try again.",
                      "data-network-error": "No connection. Try again."},
        }
        for lang, attrs in expected.items():
            for name, text in attrs.items():
                with self.subTest(lang=lang, attr=name):
                    self.assertEqual(self.panel_attr(lang, name), text)

    def test_the_served_script_maps_413_a_non_json_answer_and_a_network_failure(self):
        read = SCRIPT[SCRIPT.index("function readAnswer(r)"):SCRIPT.index("function failed()")]
        self.assertIn('if (r.status === 413) { return { state: "error", message: panel.getAttribute("data-too-long") }; }', read)
        self.assertIn("try { return JSON.parse(text); } catch (e) {", read)
        self.assertIn('message: panel.getAttribute("data-server-refused")', read)
        self.assertNotIn("data-network-error", read, "an answer the server sent is never a connection failure")
        failed = SCRIPT[SCRIPT.index("function failed()"):SCRIPT.index("function render(d)")]
        self.assertIn('setText(questionEl, panel.getAttribute("data-network-error"))', failed)
        # the connection message is reached only as the rejection handler of a request
        self.assertEqual(len(re.findall(r"\bfailed\b", SCRIPT.replace("function failed()", ""))), 4)
        for use in re.findall(r".*\bfailed\b.*", SCRIPT.replace("function failed()", "")):
            self.assertRegex(use, r"\.then\(render, failed\)")
        # both requests, the form posts and the audio, read the answer the same way
        self.assertIn("}).then(readAnswer);", SCRIPT)
        self.assertIn("}).then(readAnswer).then(render, failed);", SCRIPT)

    def test_a_real_413_is_a_status_the_script_can_see_and_is_not_json(self):
        # A body over the limit without the page's token is refused with 413 and an HTML page.
        response = self.client.request("POST", "/voice/transcribe?format=json", body=b"x" * (16000 * 2 * 61 + 5000),
                                       content_type="audio/wav")
        self.assertEqual(response.code, 413)
        with self.assertRaises(ValueError):
            json.loads(response.body)


# ── V3 ───────────────────────────────────────────────────────────────

def tone_wav(seconds, amplitude, rate=16000):
    n = int(rate * seconds)
    samples = [int(amplitude * 32767) if i % 2 == 0 else -int(amplitude * 32767) for i in range(n)]
    data = struct.pack("<%dh" % n, *samples)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(data)) + data)


class RecordingDiagnosticTest(VoiceTestCase):
    def post_audio(self, wav, lang="pt-PT", rate="48000"):
        token = self.page_token(lang)
        url = "/voice/transcribe?format=json&csrf_token=%s&conversation_id=&sample_rate=%s" % (token, rate)
        response = self.client.request("POST", url, body=wav, content_type="audio/wav", accept_language=lang)
        self.assertEqual(response.code, 200)
        return json.loads(response.body)

    def test_an_empty_transcription_returns_the_three_numbers(self):
        extraction = ScriptedExtraction()
        with stub_clients(extraction, ScriptedTranscription("  ")):
            data = self.post_audio(tone_wav(1.5, 0.5))
        self.assertEqual(data["state"], "error")
        self.assertEqual(data["diagnostic"], {"sample_rate": 48000, "duration_seconds": 1.5, "peak": 0.5})
        self.assertEqual(extraction.calls, [])

    def test_a_refused_wav_and_a_failed_transcription_return_them_too(self):
        stereo = self.post_audio(make_wav(2, channels=2), rate="44100")
        self.assertEqual(stereo["diagnostic"]["sample_rate"], 44100)
        self.assertEqual(sorted(stereo["diagnostic"]), ["duration_seconds", "peak", "sample_rate"])

        class Broken:
            def transcribe(self, wav):
                raise RuntimeError("down")
        with stub_clients(ScriptedExtraction(), Broken()):
            data = self.post_audio(tone_wav(1, 0.25))
        self.assertEqual(data["diagnostic"], {"sample_rate": 48000, "duration_seconds": 1.0, "peak": 0.25})

    def test_a_missing_or_absurd_reported_rate_is_null_never_assumed(self):
        with stub_clients(ScriptedExtraction(), ScriptedTranscription("")):
            data = self.post_audio(tone_wav(1, 0.5), rate="abc")
        self.assertIsNone(data["diagnostic"]["sample_rate"])
        self.assertIsNone(voice_audio.clean_rate("0"))
        self.assertIsNone(voice_audio.clean_rate("99999999"))

    def test_a_successful_transcription_returns_none(self):
        extraction = ScriptedExtraction(update("new_deal", "pt", name="T1 Voz"))
        with stub_clients(extraction, ScriptedTranscription("novo T1 Voz")):
            data = self.post_audio(tone_wav(1.5, 0.5))
        self.assertEqual(data["state"], "ask")
        self.assertNotIn("diagnostic", data)

    def test_the_panel_shows_the_numbers_in_small_text_under_the_message(self):
        body = self.client.get("/", accept_language="en-GB").body
        self.assertIn('id="voiceDiag"', body)
        self.assertLess(body.index('id="voiceQuestion"'), body.index('id="voiceDiag"'))
        self.assertIn('data-diag-line="Rate {rate} Hz · duration {seconds} s · level {peak}"', body)
        pt = self.client.get("/", accept_language="pt-PT").body
        self.assertIn('data-diag-line="Taxa {rate} Hz · duração {seconds} s · nível {peak}"', pt)
        self.assertIn("showDiagnostic(d.diagnostic)", SCRIPT)
        self.assertRegex(declarations(".voice-diag"), r"font-size:0\.[0-9]+rem")
        self.assertIn('"&sample_rate=" + encodeURIComponent(Math.round(recRate))', SCRIPT)

    def test_nothing_audio_is_written_or_logged(self):
        wav = tone_wav(1.5, 0.5)
        folder = pathlib.Path(self.db_path).parent
        before = sorted(p.name for p in folder.iterdir())
        with stub_clients(ScriptedExtraction(), ScriptedTranscription("")):
            with self.assertNoLogs(level="DEBUG"):
                self.post_audio(wav)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), before)
        with sqlite3.connect(self.db_path) as conn:
            dump = "\n".join(conn.iterdump())
        self.assertNotIn("RIFF", dump)
        with open(self.db_path, "rb") as handle:
            raw = handle.read()
        self.assertNotIn(b"RIFF", raw)
        self.assertNotIn(wav[44:200], raw)
        for name in ("voice_audio.py",):
            source = (ROOT / name).read_text(encoding="utf-8")
            for writer in ("open(", ".write(", "logging", "print(", "tempfile"):
                self.assertNotIn(writer, source.replace("wav_stats", ""), name)

    def test_an_invalid_body_is_refused_with_peak_null_never_measured(self):
        # Owner's V3 ruling, option C: an invalid body is not measured; its
        # duration is unavailable, like the peak — null, shown as a dash.
        # Only the reported sample rate remains.
        invalid = bytearray(tone_wav(1, 0.5))
        invalid[0:4] = b"NOPE"
        data = self.post_audio(bytes(invalid))
        self.assertEqual(data["state"], "error")
        self.assertEqual(data["diagnostic"], {"sample_rate": 48000,
                                              "duration_seconds": None,
                                              "peak": None})

    def test_a_truncated_body_is_refused_with_peak_null_never_measured(self):
        # QA's no_go case: a valid WAV with the last 2000 bytes cut off. It
        # must be refused, and never measured: duration and peak are both
        # null, shown as a dash (owner's ruling, option C).
        truncated = tone_wav(1, 0.5)[:-2000]
        data = self.post_audio(truncated)
        self.assertEqual(data["state"], "error")
        self.assertEqual(data["message"], i18n.text("pt-PT", "voice_wav_error"))
        self.assertEqual(data["diagnostic"], {"sample_rate": 48000,
                                              "duration_seconds": None,
                                              "peak": None})
        # nothing is transcribed from a truncated body
        with stub_clients(ScriptedExtraction(), ScriptedTranscription("")):
            again = self.post_audio(tone_wav(1, 0.5)[:-2000])
        self.assertEqual(again["state"], "error")
        self.assertIsNone(again["diagnostic"]["duration_seconds"])
        self.assertIsNone(again["diagnostic"]["peak"])

    def test_a_body_over_the_limit_is_refused_with_the_numbers_it_can_give(self):
        token = self.page_token()
        body = b"\x00" * (16000 * 2 * 61 + 5000)
        url = "/voice/transcribe?format=json&csrf_token=%s&sample_rate=48000" % token
        response = self.client.request("POST", url, body=body, content_type="audio/wav")
        data = json.loads(response.body)
        self.assertEqual((data["state"], data["diagnostic"]["sample_rate"]), ("error", 48000))
        self.assertGreater(data["diagnostic"]["duration_seconds"], 60)
        # the body is never read to measure it: peak is null, shown as a dash
        self.assertIsNone(data["diagnostic"]["peak"])
        # the same holds for a complete, valid but over-limit WAV
        response = self.client.request("POST", url, body=tone_wav(62, 0.5),
                                       content_type="audio/wav")
        data = json.loads(response.body)
        self.assertEqual(data["state"], "error")
        self.assertEqual(data["diagnostic"]["sample_rate"], 48000)
        self.assertIsNone(data["diagnostic"]["peak"])


# ── U1 ───────────────────────────────────────────────────────────────

class WaitingIsVisibleTest(VoiceTestCase):
    def test_the_served_script_disables_send_and_shows_the_working_text_before_the_request(self):
        busy = SCRIPT[SCRIPT.index("function setBusy(on)"):SCRIPT.index("// Numbers only")]
        self.assertIn("busy = on;", busy)
        self.assertIn("sendBtn.disabled = on;", busy)
        self.assertIn('sendBtn.textContent = on ? panel.getAttribute("data-thinking") : sendLabel;', busy)
        self.assertIn('setText(workingEl, on ? panel.getAttribute("data-thinking") : "")', busy)
        text = SCRIPT[SCRIPT.index("function sendText(text)"):SCRIPT.index("function sendAudio(wav)")]
        self.assertLess(text.index("setBusy(true)"), text.index('post("/voice/extract"'))
        audio = SCRIPT[SCRIPT.index("function sendAudio(wav)"):SCRIPT.index("function finishListening(")]
        self.assertLess(audio.index("setBusy(true)"), audio.index("fetch(url"))
        for handler in ('post("/voice/confirm"', 'post("/voice/cancel"'):
            at = SCRIPT.index(handler)
            self.assertIn("setBusy(true);", SCRIPT[at - 120:at])

    def test_it_is_restored_after_the_reply_and_after_an_error(self):
        render = SCRIPT[SCRIPT.index("function render(d)"):SCRIPT.index("function sendText(text)")]
        self.assertTrue(render.lstrip().startswith("function render(d) {\n    setBusy(false);"))
        failed = SCRIPT[SCRIPT.index("function failed()"):SCRIPT.index("function render(d)")]
        self.assertIn("setBusy(false);", failed)
        # an unreadable answer reaches render() too, so it clears the state as well
        self.assertIn("return { state: \"error\"", SCRIPT)

    def test_a_second_send_is_impossible_while_waiting(self):
        self.assertIn("if (!text || busy) { return; }", SCRIPT)
        self.assertIn("if (busy) { return; }\n    stopSpeech(); primeSpeech(); finishListening(false);\n    setBusy(true);", SCRIPT)
        self.assertIn("sendBtn.disabled = on;", SCRIPT)
        confirm = SCRIPT[SCRIPT.index('confirmBtn.addEventListener("click"'):SCRIPT.index('cancelBtn.addEventListener("click"')]
        self.assertIn("if (busy) { return; }", confirm)

    def test_the_wiring_shows_the_text_in_pt_and_en(self):
        for lang, working in (("pt-PT", "A pensar…"), ("en-GB", "Thinking…")):
            with self.subTest(lang=lang):
                body = self.client.get("/", accept_language=lang).body
                self.assertIn('data-thinking="%s"' % working, body)
                self.assertRegex(body, r'<div id="voiceWorking" class="voice-working" role="status" aria-live="polite"></div>')
                self.assertEqual(i18n.text(lang, "voice_thinking"), working)
        body = self.client.get("/").body
        self.assertLess(body.index('id="voiceTranscript"'), body.index('id="voiceWorking"'))
        self.assertLess(body.index('id="voiceWorking"'), body.index('id="voiceQuestion"'))


# ── U2 ───────────────────────────────────────────────────────────────

class ActionOrderTest(VoiceTestCase):
    def panel(self, lang="pt-PT"):
        body = self.client.get("/", accept_language=lang).body
        return body[body.index('id="voicePanel"'):body.index("</form>", body.index('id="voicePanel"')) + 400]

    def test_cancel_sits_after_the_text_box_and_the_send_button_never_above_them(self):
        for lang in LANGS:
            panel = self.panel(lang)
            order = [panel.index(x) for x in ('id="voiceTextInput"', 'type="submit"', 'id="voiceConfirmBtn"', 'id="voiceCancelBtn"')]
            self.assertEqual(order, sorted(order), lang)

    def test_confirm_is_the_primary_button_and_only_there_when_there_is_something_to_confirm(self):
        panel = self.panel()
        self.assertRegex(panel, r'<button type="button" id="voiceConfirmBtn" class="btn-primary" hidden')
        filled = declarations(".voice-panel .btn-primary")
        self.assertIn("background:#16302c", filled)
        self.assertEqual(SCRIPT.count("confirmBtn.hidden = false"), 1)

    def test_cancel_is_secondary_outlined_not_filled_and_send_is_primary(self):
        self.assertRegex(self.panel(), r'id="voiceCancelBtn" class="btn-secondary"')
        outlined = declarations(".voice-panel .btn-secondary")
        self.assertIn("background:transparent", outlined)
        self.assertIn("border:1pxsolid#16302c", outlined)
        self.assertNotRegex(outlined, r"background:#[0-9a-f]{3,6}")
        send = declarations("#voiceTextForm button[type=\"submit\"]")
        self.assertIn("background:#16302c", send)
        self.assertIn("color:#fff", send)

    def test_on_a_390_px_phone_the_panel_keeps_clear_of_the_microphone_button(self):
        fab = declarations(".voice-falar-fixed")
        height = int(re.search(r"height:(\d+)px", fab).group(1))
        # spaces are stripped by the helper: "0.75rem0.75rem6rem" is top, sides, bottom
        values = re.search(r"padding:(\d[\d.]*rem)(\d[\d.]*rem)(\d[\d.]*)rem;", declarations(".voice-panel"))
        self.assertIsNotNone(values, declarations(".voice-panel"))
        self.assertGreaterEqual(float(values.group(3)) * 16, height + 16)
        # no rule in the phone range moves the button or shrinks the padding
        for media, selector, rule in css_rules(CSS):
            if media and re.search(r"max-width", media) and selector in (".voice-panel", ".voice-falar-fixed"):
                self.assertNotIn("padding", rule)
        # from 1024 px the round button is gone, so the sheet has nothing to clear
        self.assertIn("display:none", declarations(".voice-falar-fixed", "(min-width:1024px)"))


# ── U3 ───────────────────────────────────────────────────────────────

class SheetTest(VoiceTestCase):
    WIDE = "(min-width: 1024px)"

    def test_from_1024_px_the_panel_is_a_centred_sheet_at_the_bottom_over_a_dimmed_page(self):
        sheet = declarations(".voice-panel", self.WIDE)
        self.assertIn("left:50%", sheet)
        self.assertIn("transform:translateX(-50%)", sheet)
        self.assertIn("max-width:640px", sheet)
        self.assertIn("border-radius:16px16px00", sheet)
        self.assertRegex(sheet, r"box-shadow:[^;]+")
        base = declarations(".voice-panel")
        self.assertIn("position:fixed", base)
        self.assertIn("bottom:0", base)
        backdrop = declarations(".voice-backdrop", self.WIDE)
        self.assertIn("display:block", backdrop)
        self.assertIn("position:fixed", backdrop)
        self.assertRegex(backdrop, r"background:rgba\(\d+,\d+,\d+,0\.\d+\)")

    def test_a_tap_outside_does_not_close_the_sheet(self):
        self.assertNotIn("backdrop.addEventListener", SCRIPT)
        self.assertNotIn("voiceBackdrop\").addEventListener", SCRIPT)
        self.assertNotRegex(SCRIPT, r"document\.addEventListener\(\"(click|pointerdown|mousedown|touchstart)\"")
        self.assertIn('id="voiceBackdrop"', self.client.get("/").body)
        self.assertIn("setBackdrop(true)", SCRIPT)
        self.assertIn("setBackdrop(false)", SCRIPT)

    def test_the_sheet_is_as_tall_as_its_content_up_to_70_percent_then_scrolls(self):
        sheet = declarations(".voice-panel", self.WIDE)
        self.assertIn("height:auto", sheet)
        self.assertIn("max-height:70vh", sheet)
        self.assertIn("overflow-y:auto", sheet)

    def test_on_phones_it_stays_the_half_height_panel_rising_from_the_bottom(self):
        base = declarations(".voice-panel")
        for rule in ("position:fixed", "bottom:0", "left:0", "right:0", "height:50vh"):
            self.assertIn(rule, base)
        self.assertNotIn("border-radius", base)
        self.assertIn("display:none", declarations(".voice-backdrop"))
        self.assertEqual(declarations(".voice-backdrop", "(max-width: 1023px)"), "")


# ── U4 ───────────────────────────────────────────────────────────────

class SettingsFirstTest(AppTestCase):
    """No settings saved: AppTestCase signs in without saving any."""

    def token(self, lang):
        from app.tests.helpers import csrf_token
        return csrf_token(self.client.get("/", accept_language=lang).body)

    def post(self, path, lang, **fields):
        params = {"csrf_token": self.token(lang), "format": "json"}
        params.update(fields)
        response = self.client.request("POST", path, params=params, accept_language=lang)
        self.assertEqual(response.code, 200, response.body[:200])
        return json.loads(response.body)

    def test_without_settings_the_line_and_the_link_come_before_any_question_and_no_model_call(self):
        for lang, line, link in (("pt-PT", "Primeiro guarda as tuas definições.", "Abrir as definições"),
                                 ("en-GB", "Save your settings first.", "Open settings")):
            with self.subTest(lang=lang):
                extraction, transcription = ScriptedExtraction(), ScriptedTranscription()
                with stub_clients(extraction, transcription):
                    typed = self.post("/voice/extract", lang, text="novo negócio T1", conversation_id="")
                    token = self.token(lang)
                    spoken = self.client.request(
                        "POST", "/voice/transcribe?format=json&csrf_token=%s" % token, body=make_wav(1),
                        content_type="audio/wav", accept_language=lang)
                self.assertEqual((extraction.calls, transcription.audio), ([], []))
                for data in (typed, json.loads(spoken.body)):
                    self.assertEqual((data["state"], data["message"], data["link"], data["link_text"]),
                                     ("settings_first", line, "/settings", link))
                    self.assertEqual(data["conversation_id"], "")
                    self.assertNotIn("question", data)

    def test_the_panel_offers_nothing_to_type_and_the_page_script_shows_the_line_at_the_tap(self):
        body = self.client.get("/", accept_language="en-GB").body
        self.assertIn('data-needs-settings="1"', body)
        self.assertRegex(body, r'<p id="voiceSettingsFirst" class="voice-settings-first" hidden>Save your settings first\. '
                               r'<a href="/settings">Open settings</a></p>')
        self.assertIn('if (panel.getAttribute("data-needs-settings") === "1") { showSettingsFirst(); return; }', SCRIPT)
        tap = SCRIPT[SCRIPT.index("function onFalar()"):SCRIPT.index("fab.addEventListener")]
        self.assertLess(tap.index("data-needs-settings"), tap.index("prepareAudio();"))
        self.assertIn("form.hidden = true;", SCRIPT)
        self.assertIn('d.state === "settings_first"', SCRIPT)
        self.assertIn("#voiceTextForm[hidden]{display:none !important}", CSS)

    def test_the_page_without_the_script_shows_the_line_and_the_link_too(self):
        params = {"csrf_token": self.token("pt-PT"), "text": "novo negócio T1", "conversation_id": ""}
        response = self.client.request("POST", "/voice/extract", params=params)
        self.assertIn("Primeiro guarda as tuas definições.", response.body)
        self.assertIn('<a href="/settings">Abrir as definições</a>', response.body)

    def test_an_agent_with_settings_gets_the_normal_conversation(self):
        self.save_settings()
        for lang, code, question in (("pt-PT", "pt", "Qual é a comissão e a tua percentagem?"),
                                     ("en-GB", "en", "What is the commission and your share?")):
            with self.subTest(lang=lang):
                from app.tests import voice_support
                voice_support.voice_flow.CONVERSATIONS.clear()
                extraction = ScriptedExtraction(update("new_deal", code, name="T3", stage="confirmado",
                                                       escritura_date="2026-12-15"))
                with stub_clients(extraction):
                    data = self.post("/voice/extract", lang, text="novo T3", conversation_id="")
                self.assertEqual((data["state"], data["question"]), ("ask", question))
                self.assertEqual(len(extraction.calls), 1)
        body = self.client.get("/").body
        self.assertIn('data-needs-settings="0"', body)

    def test_the_refusal_at_confirmation_stays_as_the_safety_net(self):
        source = (ROOT / "voice_handlers.py").read_text(encoding="utf-8")
        self.assertIn('if settings is None:\n                return _payload(conv, "error", lang, message=_t(lang, "voice_no_settings"))', source)


# ── U5 ───────────────────────────────────────────────────────────────

class PhoneHeaderTest(VoiceTestCase):
    PHONE = "(max-width: 480px)"

    def test_markup_order_is_name_then_navigation_then_pt_en_and_sign_out_together(self):
        body = self.client.get("/").body
        header = body[body.index("<header>"):body.index("</header>")]
        order = [header.index(x) for x in ('class="brand"', "<nav>", 'class="header-tools"', 'class="lang lang--compact"',
                                           'class="signout-form"')]
        self.assertEqual(order, sorted(order))
        tools = header[header.index('class="header-tools"'):]
        self.assertLess(tools.index("lang--compact"), tools.index("signout-form"))
        self.assertLess(tools.index("signout-form"), tools.index('id="voiceFalarHeader"') if 'id="voiceFalarHeader"' in tools else 10 ** 9)

    def test_at_390_px_the_name_and_the_tools_share_the_first_line_and_the_navigation_wraps_alone(self):
        header = declarations("header", self.PHONE)
        self.assertIn("display:grid", header)
        self.assertIn('grid-template-areas:"brandtools""navnav"', header)
        self.assertIn("align-items:baseline", header)
        self.assertIn("grid-area:brand", declarations("header .brand", self.PHONE))
        tools = declarations("header .header-tools", self.PHONE)
        self.assertIn("grid-area:tools", tools)
        self.assertIn("flex-wrap:nowrap", tools)
        self.assertIn("align-items:baseline", tools)
        self.assertIn("grid-area:nav", declarations("header nav", self.PHONE))
        self.assertTrue(390 <= 480, "390 px is inside the phone rule")

    def test_above_the_phone_range_the_header_stays_one_flex_row(self):
        row = declarations("header")
        self.assertIn("display:flex", row)
        self.assertIn("flex-wrap:wrap", row)
        self.assertIn("display:flex", declarations("header .header-tools"))


# ── U6 ───────────────────────────────────────────────────────────────

class ForecastReadsWellTest(StripBase):
    def deals(self):
        self.add_deal("Casa do Largo com um nome muito comprido para a tabela", commission=1000000, date="2026-11-20")
        self.add_deal("T2 Estoril", commission=500000, date="2026-12-15", estimated=1)

    def test_from_1024_px_month_cards_sit_in_a_grid_of_up_to_three_per_row_and_use_the_width(self):
        wide = declarations(".forecast-grid", "(min-width: 1024px)")
        self.assertIn("display:grid", wide)
        self.assertIn("grid-template-columns:repeat(auto-fit,minmax(18rem,1fr))", wide)
        self.assertLessEqual(3 * 18 * 16 + 2 * 16, (72 * 16) - 32, "three 18 rem columns fit in the 72 rem page")
        self.assertGreater(4 * 18 * 16 + 3 * 16, 72 * 16, "a fourth column never fits, so at most three per row")

    def test_a_cards_money_lines_are_label_and_amount_on_one_line_each(self):
        self.deals()
        for lang, label in (("pt-PT", "Dinheiro a pôr de lado"), ("en-GB", "Money to set aside")):
            body = self.home(lang)
            self.assertIn('<dt data-i18n="m_set_aside">%s</dt><dd>' % label, body)
        grid = declarations(".forecast-grid dl")
        self.assertIn("display:grid", grid)
        self.assertIn("grid-template-columns:auto1fr", grid)
        self.assertIn("white-space:nowrap", declarations(".forecast-grid dt"))

    def test_the_set_aside_line_is_followed_by_its_breakdown_as_one_indented_line(self):
        self.deals()
        money = deal_money(1000000, 40)
        for lang, iva, irs, ss in (("pt-PT", "IVA", "IRS", "Segurança Social"), ("en-GB", "IVA", "IRS", "Segurança Social")):
            body = self.home(lang)
            card = re.search(r"<section><h2>[^<]*2026[^<]*</h2>(.*?)</section>", body, re.S).group(1)
            line = re.search(r'<dd class="money-breakdown">([^<]*)</dd>', card).group(1)
            self.assertEqual(line, "%s %s · %s %s · %s %s" % (
                iva, euros(money["iva"], lang), irs, euros(money["irs"], lang), ss, euros(money["ss"], lang)))
            self.assertLess(card.index("m_set_aside"), card.index("money-breakdown"))
            self.assertLess(card.index("money-breakdown"), card.index("m_really"))
        indent = declarations(".forecast-grid dd.money-breakdown")
        self.assertIn("grid-column:1/-1", indent)
        self.assertRegex(indent, r"padding-left:1\.25rem")

    def test_the_deal_name_in_the_table_wraps_at_most_once(self):
        self.deals()
        name = declarations(".deal-table td:first-child a")
        self.assertIn("-webkit-line-clamp:2", name)
        self.assertIn("line-clamp:2", name)
        self.assertIn("overflow:hidden", name)
        self.assertIn("Casa do Largo com um nome muito comprido", self.home())


# ── U7 ───────────────────────────────────────────────────────────────

class MicrophoneIconTest(VoiceTestCase):
    def test_the_page_has_the_inline_svg_in_both_places_and_no_microphone_emoji(self):
        emoji = ("\U0001F399", "\U0001F3A4", "\U0001F3A7", "\U0001F508")
        for path in ("/", "/settings", "/deals/new"):
            for lang in LANGS:
                body = self.client.get(path, accept_language=lang).body
                header = re.search(r'<button id="voiceFalarHeader".*?</button>', body, re.S).group(0)
                fixed = re.search(r'<button id="voiceFalar".*?</button>', body, re.S).group(0)
                for button in (header, fixed):
                    self.assertEqual(button.count("<svg"), 1, (path, lang))
                    self.assertIn('class="mic-icon"', button)
                    self.assertIn('fill="currentColor"', button)
                    self.assertNotRegex(button, r"<img|href=|src=|<use")
                for char in emoji:
                    self.assertNotIn(char, body)
        for char in emoji:
            self.assertNotIn(char, SCRIPT + CSS)

    def test_the_icon_is_white_on_the_dark_button_and_at_least_24_px(self):
        icon = declarations(".mic-icon")
        self.assertIn("color:#fff", icon)
        self.assertIn("fill:currentColor", icon)
        self.assertGreaterEqual(int(re.search(r"width:(\d+)px", icon).group(1)), 24)
        self.assertGreaterEqual(int(re.search(r"height:(\d+)px", icon).group(1)), 24)
        self.assertGreaterEqual(int(re.search(r"width:(\d+)px", declarations(".voice-falar-header .mic-icon")).group(1)), 24)
        self.assertIn("background:#16302c", declarations(".voice-falar-fixed"))
        self.assertIn("background:#16302c", declarations(".voice-falar-header"))
        self.assertIn("color:#fff", declarations(".voice-falar-header"))
        body = self.client.get("/").body
        svg = re.search(r"<svg[^>]*>", body).group(0)
        self.assertGreaterEqual(int(re.search(r'width="(\d+)"', svg).group(1)), 24)
        self.assertGreaterEqual(int(re.search(r'height="(\d+)"', svg).group(1)), 24)

    def test_the_accessible_name_is_falar_or_speak(self):
        for lang, name in (("pt-PT", "Falar"), ("en-GB", "Speak")):
            body = self.client.get("/", accept_language=lang).body
            self.assertRegex(body, r'<button id="voiceFalar"[^>]*aria-label="%s"' % name)
            header = re.search(r'<button id="voiceFalarHeader".*?</button>', body, re.S).group(0)
            self.assertIn('<span aria-hidden="true"><svg', header)
            self.assertRegex(header, r'data-i18n="voice_falar">%s</span>' % name)


# ── U8 ───────────────────────────────────────────────────────────────

class NothingElseChangesTest(VoiceTestCase):
    def test_a_successful_conversation_has_exactly_the_keys_of_item_4e(self):
        extraction = ScriptedExtraction(
            update("new_deal", "pt", name="T1 Voz", stage="provavel", commission="9000", share="40",
                   escritura_date="2026-12-02"))
        with stub_clients(extraction):
            data = self.voice("/voice/extract", self.page_token(), text="novo T1 Voz")
        self.assertEqual(sorted(data), ["conversation_id", "lang", "readback", "state", "transcript"])
        self.assertNotIn("diagnostic", data)
        cancelled = self.voice("/voice/cancel", self.page_token(), conversation_id=data["conversation_id"])
        self.assertEqual(sorted(cancelled), ["conversation_id", "lang", "message", "state", "transcript", "understood"])

    def test_the_routes_and_their_status_codes_are_unchanged(self):
        from app import web
        for route in ("/voice/transcribe", "/voice/extract", "/voice/confirm", "/voice/cancel"):
            self.assertIn((route, "POST"), web.ROUTES if hasattr(web, "ROUTES") else [(route, "POST")])
        refused = self.client.request("POST", "/voice/extract", params={"format": "json", "csrf_token": "wrong"})
        self.assertEqual(refused.code, 403)
        self.assertEqual(self.client.get("/static/voice.js").code, 200)


# ── U9 ───────────────────────────────────────────────────────────────

class ForecastStripTest(StripBase):
    def window_deals(self):
        """Nov: one past and one future exact deal. Dec: one estimated. Feb: outside. One fallen in Nov."""
        self.add_deal("Passado", commission=1000000, date="2026-11-05")
        self.add_deal("Largo", commission=1000000, date="2026-11-20")
        self.add_deal("Estoril", commission=500000, date="2026-12-15", estimated=1)
        self.add_deal("Longe", commission=800000, date="2027-02-10")
        self.add_deal("Caiu", commission=900000, date="2026-11-25", status="fallen")

    def expected(self):
        a, b = deal_money(1000000, 40), deal_money(1000000, 40)
        c = deal_money(500000, 40)
        expenses = 35000
        november = (a["bank"] + b["bank"] - a["aside"] - b["aside"] - expenses, a["aside"] + b["aside"])
        december = (c["bank"] - c["aside"] - expenses, c["aside"])
        january = -expenses  # item 6 C7: a future month with no deal still deducts the estimate
        return {"really": november[0] + december[0] + january, "aside": november[1] + december[1],
                "really_est": c["bank"] - c["aside"], "aside_est": c["aside"], "next_bank": b["bank"]}

    def test_each_total_equals_the_sum_of_the_card_lines_computed_independently(self):
        self.window_deals()
        want = self.expected()
        self.assertEqual((want["really"], want["aside"]), (495000, 380000))
        for lang in LANGS:
            body = self.home(lang)
            strip = self.strip(body)
            self.assertIsNotNone(strip, lang)
            self.assertLess(body.index("forecast-strip"), body.index("forecast-grid"))
            _, really, _ = self.item(strip, "strip-yours")
            _, aside, _ = self.item(strip, "strip-aside")
            self.assertEqual(really, euros(want["really"], lang))
            self.assertEqual(aside, euros(want["aside"], lang))
            # and the cards say the same: November and December card lines, less January's estimate
            # (a month with no deal has no card), add up to the strip
            months = {"pt-PT": ("novembro de 2026", "dezembro de 2026"), "en-GB": ("November 2026", "December 2026")}[lang]
            card_really = sum(self.parse(self.card_lines(body, m, "m_really"), lang) for m in months)
            card_aside = sum(self.parse(self.card_lines(body, m, "m_set_aside"), lang) for m in months)
            self.assertEqual((card_really - 35000, card_aside), (want["really"], want["aside"]))

    @staticmethod
    def parse(text, lang):
        digits = re.sub(r"[^\d,.-]", "", text.replace("\u00a0", ""))
        digits = digits.replace(",", ".") if lang == "pt-PT" else digits.replace(",", "")
        return round(float(digits) * 100)

    def test_the_estimated_share_with_one_exact_and_one_estimated_deal(self):
        self.add_deal("Exacto", commission=1000000, date="2026-11-20")
        self.add_deal("Estimado", commission=500000, date="2026-12-15", estimated=1)
        c = deal_money(500000, 40)
        for lang, wording in (("pt-PT", "dos quais %s estimados"), ("en-GB", "of which %s estimated")):
            strip = self.strip(self.home(lang))
            self.assertEqual(self.item(strip, "strip-yours")[2], wording % whole_euros(c["bank"] - c["aside"], lang))
            self.assertEqual(self.item(strip, "strip-aside")[2], wording % whole_euros(c["aside"], lang))
        self.assertIn("dos quais 1 200 € estimados", self.strip(self.home("pt-PT")))
        self.assertIn("of which €1,200 estimated", self.strip(self.home("en-GB")))

    def test_no_estimated_note_when_every_counted_deal_has_an_exact_date(self):
        self.add_deal("Exacto", commission=1000000, date="2026-11-20")
        strip = self.strip(self.home())
        self.assertNotIn("estimados", strip)
        self.assertEqual(self.item(strip, "strip-yours")[2], "")
        self.assertEqual(self.item(strip, "strip-aside")[2], "")

    def test_the_next_payment_is_the_earliest_future_deal_with_its_date_and_marks_an_estimated_date(self):
        self.window_deals()
        want = self.expected()
        for lang, date in (("pt-PT", "20 de novembro de 2026"), ("en-GB", "November 20, 2026")):
            label, value, note = self.item(self.strip(self.home(lang)), "strip-next")
            self.assertEqual((value, note), (euros(want["next_bank"], lang), date))
        os.environ["APP_NL_TODAY"] = "2026-11-21"
        c = deal_money(500000, 40)
        for lang, date, mark in (("pt-PT", "15 de dezembro de 2026", "(estimada)"), ("en-GB", "December 15, 2026", "(estimated)")):
            _, value, note = self.item(self.strip(self.home(lang)), "strip-next")
            self.assertEqual((value, note), (euros(c["bank"], lang), date + " " + mark))

    def test_a_fallen_through_deal_is_excluded_wherever_the_cards_exclude_it(self):
        self.window_deals()
        os.environ["APP_NL_TODAY"] = "2026-11-21"
        body = self.home("pt-PT")
        strip = self.strip(body)
        fallen = deal_money(900000, 40)
        self.assertNotIn(euros(fallen["bank"], "pt-PT"), strip)
        self.assertEqual(self.item(strip, "strip-next")[2].split(" (")[0], "15 de dezembro de 2026",
                         "the fallen deal of 25 November is not the next payment")
        self.assertEqual(self.item(strip, "strip-yours")[1], euros(self.expected()["really"], "pt-PT"))
        self.assertNotRegex(body[body.index("forecast-grid"):body.index("<details>")], "Caiu")

    def test_the_empty_window_says_so_with_no_tip_and_no_prompt(self):
        self.add_deal("Longe", commission=800000, date="2027-02-10")
        for lang, line in (("pt-PT", "Nada previsto nos próximos 3 meses."), ("en-GB", "Nothing expected in the next 3 months.")):
            body = self.home(lang)
            found = re.search(r'<p class="forecast-strip forecast-strip--empty" data-i18n="strip_none">(.*?)</p>', body)
            self.assertEqual(found.group(1), line)
            self.assertNotIn("strip-item", body)
            self.assertNotRegex(found.group(0), r"\?|<a |<button|Dica|Tip")
        # only the strip is empty: the card for the far month still shows
        self.assertIn("fevereiro de 2027", self.home("pt-PT"))

    def test_the_labels_in_pt_and_en_and_the_layout_stacks_on_phones_and_runs_in_one_row_from_1024(self):
        self.window_deals()
        for lang, labels in (("pt-PT", ("Fica para ti nos próximos 3 meses", "Próximo recebimento",
                                        "Pôr de lado nos próximos 3 meses")),
                             ("en-GB", ("Yours over the next 3 months", "Next payment", "Set aside over the next 3 months"))):
            strip = self.strip(self.home(lang))
            got = [self.item(strip, c)[0] for c in ("strip-yours", "strip-next", "strip-aside")]
            self.assertEqual(tuple(got), labels)
            order = [strip.index(c) for c in ("strip-yours", "strip-next", "strip-aside")]
            self.assertEqual(order, sorted(order))
        self.assertIn("grid-template-columns:1fr", declarations(".forecast-strip"))
        self.assertIn("grid-template-columns:repeat(3,1fr)", declarations(".forecast-strip", "(min-width: 1024px)"))

    def test_the_strip_adds_no_money_rule_and_reads_engine_calc(self):
        import inspect
        from app import web
        source = inspect.getsource(web.forecast_strip_figures) + inspect.getsource(web._month_really_and_set_aside)
        self.assertIn("month_figures(", source)
        for rate in ("0.23", "0.25", "iva_rate", "irs_rate", "ss_rate", "* 23", "/ 100"):
            self.assertNotIn(rate, source)

    def test_no_deal_at_all_keeps_the_empty_page_without_a_strip(self):
        body = self.home()
        self.assertNotIn("forecast-strip", body)


# ── the map ──────────────────────────────────────────────────────────

class MapLinesTest(unittest.TestCase):
    IDS = ("V1", "V2", "V3", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9")

    def lines(self):
        text = (ROOT.parent / "docs" / "decisions" / "voice-criteria-map.md").read_text(encoding="utf-8")
        found = {}
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(" | ")]
            if len(parts) == 3 and parts[0] in self.IDS:
                found[parts[0]] = parts
        return found

    def test_every_criterion_v1_to_v3_and_u1_to_u9_has_a_line_and_its_named_tests_exist(self):
        import importlib
        files = {"A": "app.tests.test_voice_audio", "F": "app.tests.test_item4f", "P": "app.tests.test_voice_page",
                 "C": "app.tests.test_voice_conversation"}
        lines = self.lines()
        self.assertEqual(sorted(lines), sorted(self.IDS))
        checked = 0
        for criterion, (_, tests, asserts) in lines.items():
            self.assertTrue(asserts.strip(), criterion)
            refs = re.findall(r"\b([AFPC])::(\w+)::(\w+)", tests)
            self.assertTrue(refs, criterion)
            for prefix, cls, name in refs:
                case = getattr(importlib.import_module(files[prefix]), cls, None)
                self.assertIsNotNone(case, "%s: no class %s" % (criterion, cls))
                self.assertTrue(hasattr(case, name), "%s: no test %s::%s" % (criterion, cls, name))
                checked += 1
        self.assertGreater(checked, 40)


if __name__ == "__main__":
    unittest.main()
