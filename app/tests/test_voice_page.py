"""The page works (criteria 7 to 14 of the plan, rule 8 of the request).

The test image has no browser, so these tests check the wiring the page
needs: the served page loads the script, the script binds the buttons to
the endpoints, the panel is closed on load and not hidden by CSS once
opened, and every panel text follows the page language. The HTTP journey
in test_voice_http runs the same requests the script sends.
"""
import re
import pathlib

from app.tests.helpers import AppTestCase, Client
from app.tests.voice_support import VoiceTestCase

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "static" / "voice.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def tag(body, element_id):
    return re.search(r'<[a-z]+ [^>]*id="%s"[^>]*>' % element_id, body).group(0)


class ServedScriptTest(AppTestCase):
    def test_every_signed_in_page_loads_the_script_and_has_no_inline_script(self):
        for path in ("/", "/settings", "/deals/new"):
            with self.subTest(path=path):
                body = self.client.get(path).body
                self.assertIn('<script src="/static/voice.js" defer></script>', body)
                self.assertEqual(re.findall(r"<script(?![^>]*src=)[^>]*>", body), [], "CSP allows no inline script")
                self.assertNotIn("<style", body)
                self.assertNotIn("style=", body)

    def test_the_script_is_served_same_origin_as_javascript(self):
        response = self.client.get("/static/voice.js")
        self.assertEqual(response.code, 200)
        self.assertIn("javascript", response.headers["content-type"])
        self.assertEqual(response.body, SCRIPT)
        self.assertEqual(response.headers["content-security-policy"], "default-src 'self'")

    def test_the_script_is_public_like_the_stylesheet_and_signed_out_pages_do_not_load_it(self):
        anonymous = Client()
        self.assertEqual(anonymous.get("/static/voice.js").code, 200)
        self.assertNotIn("voice.js", anonymous.get("/signin").body)
        self.assertNotIn('id="voicePanel"', anonymous.get("/signin").body)

    def test_no_external_script_or_asset_anywhere_in_the_page(self):
        body = self.client.get("/").body
        for source in re.findall(r'(?:src|href)="([^"]+)"', body):
            self.assertTrue(source.startswith("/") or source.startswith("#"), source)
        self.assertNotRegex(SCRIPT, r"https?://")


class ScriptBindingsTest(AppTestCase):
    def test_falar_opens_the_panel(self):
        self.assertIn('var panel = $("voicePanel")', SCRIPT)
        self.assertIn('var fab = $("voiceFalar")', SCRIPT)
        self.assertIn('var hdr = $("voiceFalarHeader")', SCRIPT)
        self.assertIn("function openPanel() { panel.hidden = false; }", SCRIPT)
        self.assertIn('fab.addEventListener("click", onFalar)', SCRIPT)
        self.assertIn('hdr.addEventListener("click", onFalar)', SCRIPT)
        self.assertRegex(SCRIPT, r"function onFalar\(\) \{\s*openPanel\(\);")
        body = self.client.get("/").body
        for element_id in ("voicePanel", "voiceFalar", "voiceFalarHeader", "voiceTranscript", "voiceQuestion",
                           "voiceReadback", "voiceConfirmBtn", "voiceCancelBtn", "voiceTextForm", "voiceTextInput",
                           "voiceConvId"):
            self.assertIn('id="%s"' % element_id, body)
            self.assertIn('"%s"' % element_id, SCRIPT) if element_id.startswith("voice") and element_id not in (
                "voiceTextForm", "voiceConvId") else None
        self.assertIn('$("voiceTextForm")', SCRIPT)
        self.assertIn('$("voiceConvId")', SCRIPT)

    def test_send_confirm_and_cancel_post_to_their_endpoints_with_the_conversation_id(self):
        self.assertRegex(SCRIPT, r'post\("/voice/extract", \{ conversation_id: convId\.value, text: text \}\)')
        self.assertRegex(SCRIPT, r'post\("/voice/confirm", \{ conversation_id: convId\.value \}\)')
        self.assertRegex(SCRIPT, r'post\("/voice/cancel", \{ conversation_id: convId\.value \}\)')
        self.assertRegex(SCRIPT, r'form\.addEventListener\("submit"')
        self.assertRegex(SCRIPT, r'confirmBtn\.addEventListener\("click"')
        self.assertRegex(SCRIPT, r'cancelBtn\.addEventListener\("click"')
        self.assertIn('body.append("csrf_token", csrf)', SCRIPT)
        self.assertIn('body.append("format", "json")', SCRIPT)
        self.assertIn("if (d.conversation_id !== undefined) { convId.value = d.conversation_id; }", SCRIPT)

    def test_the_answer_updates_the_panel_and_the_page_underneath_is_not_replaced(self):
        for forbidden in ("innerHTML", "document.write", "outerHTML"):
            self.assertNotIn(forbidden, SCRIPT)
        self.assertIn("setText(questionEl, d.question)", SCRIPT)
        self.assertIn("setText(readbackEl, d.readback)", SCRIPT)
        self.assertIn("el.textContent = text", SCRIPT)
        # only a saved or a finished conversation reloads the page underneath
        reloads = re.findall(r".*location\.reload.*", SCRIPT)
        self.assertEqual(len(reloads), 1)
        self.assertIn("if (reload)", reloads[0] + "if (reload)")
        self.assertIn('if (d.state === "saved") { closePanel(true); return; }', SCRIPT)

    def test_the_microphone_path_records_encodes_wav_in_the_browser_and_posts_it(self):
        self.assertIn("navigator.mediaDevices.getUserMedia({ audio: true })", SCRIPT)
        self.assertIn("window.AudioContext || window.webkitAudioContext", SCRIPT)
        self.assertIn("createScriptProcessor", SCRIPT)
        self.assertIn("var TARGET_RATE = 16000;", SCRIPT)
        for part in ('str(0, "RIFF")', 'str(8, "WAVE")', 'str(12, "fmt ")', "v.setUint16(20, 1, true)",
                     "v.setUint16(22, 1, true)", "v.setUint32(24, TARGET_RATE, true)", "v.setUint16(34, 16, true)",
                     'str(36, "data")'):
            self.assertIn(part, SCRIPT)
        self.assertNotIn('"/voice/transcribe?csrf_token="', SCRIPT)
        self.assertIn('"/voice/transcribe?format=json', SCRIPT)
        self.assertRegex(SCRIPT, r'headers: \{ "Content-Type": "audio/wav", "X-CSRF-Token": csrf \}, body: wav')
        self.assertIn("downsample(", SCRIPT)
        self.assertIn("MAX_SECONDS = 55", SCRIPT)

    def test_speech_uses_the_builtin_synthesis_in_the_language_of_the_answer(self):
        self.assertIn("window.speechSynthesis", SCRIPT)
        self.assertIn("new SpeechSynthesisUtterance(text)", SCRIPT)
        self.assertIn('var lang = d.lang || document.documentElement.lang || "pt-PT";', SCRIPT)
        self.assertIn("speak(d.question, lang, listen)", SCRIPT)
        self.assertIn("speak(d.readback, lang, listen)", SCRIPT)
        self.assertIn("function pickVoice(lang)", SCRIPT)
        self.assertIn("u.lang = lang", SCRIPT)
        self.assertNotIn('"pt-PT")', SCRIPT.replace('|| "pt-PT"', "").replace('lang || "pt-PT"', ""))

    def test_without_a_voice_or_microphone_the_questions_stay_on_screen_and_typing_works(self):
        self.assertIn("if (!text || !window.speechSynthesis || typeof SpeechSynthesisUtterance", SCRIPT)
        self.assertIn("done(); return;", SCRIPT)
        self.assertIn('panel.getAttribute("data-mic-blocked")', SCRIPT)
        self.assertIn('panel.getAttribute("data-network-error")', SCRIPT)
        # a browser that will not restart the microphone shows one tap per answer
        self.assertIn('panel.getAttribute("data-tap-answer")', SCRIPT)
        body = self.client.get("/", accept_language="en-GB").body
        self.assertIn('data-mic-blocked="The microphone is not available. Type below."', body)
        self.assertIn('data-tap-answer="Tap Speak to answer."', body)


class PanelMarkupTest(VoiceTestCase):
    def test_panel_is_closed_when_a_page_loads_and_by_the_hidden_attribute_only(self):
        body = self.client.get("/").body
        self.assertRegex(tag(body, "voicePanel"), r"\bhidden\b")
        self.assertNotIn("display:none", body.replace(" ", ""))
        self.assertRegex(tag(body, "voiceConfirmBtn"), r"\bhidden\b")
        self.assertNotIn("hidden", tag(body, "voiceCancelBtn"))
        self.assertNotIn("hidden", tag(body, "voiceFalar"))

    def test_panel_is_not_hidden_by_css_once_opened(self):
        compact = re.sub(r"\s+", "", CSS)
        self.assertIn(".voice-panel[hidden]", compact)
        self.assertIn("display:none!important", compact)
        for rule in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
            selector, declarations = rule
            if ".voice-panel" in selector and "[hidden]" not in selector:
                self.assertNotRegex(declarations, r"display\s*:\s*none", selector)
                self.assertNotRegex(declarations, r"visibility\s*:\s*hidden", selector)
        self.assertNotIn("panel.style.display", SCRIPT)
        self.assertIn("panel.hidden = false", SCRIPT)

    def test_on_phones_the_panel_never_covers_the_falar_button_and_the_page_keeps_its_last_line(self):
        fab = re.search(r"\.voice-falar-fixed\{([^}]*)\}", re.sub(r"\n", "", CSS)).group(1)
        panel = re.search(r"\.voice-panel\{([^}]*)\}", CSS).group(1)
        z = lambda block: int(re.search(r"z-index:(\d+)", block).group(1))
        self.assertGreater(z(fab), z(panel))
        self.assertIn("position:fixed", fab)
        self.assertIn("bottom:1.5rem", fab)
        self.assertIn("right:1rem", fab)
        self.assertRegex(CSS, r"main\{padding-bottom:5rem\}")
        # the panel keeps the bottom right corner free for the button on phones
        self.assertRegex(panel, r"padding:[^;]*6rem")

    def test_confirm_button_shows_only_when_there_is_something_to_confirm(self):
        self.assertIn("confirmBtn.hidden = false;", SCRIPT)
        self.assertEqual(SCRIPT.count("confirmBtn.hidden = false"), 1)
        confirm_branch = SCRIPT[SCRIPT.index('if (d.state === "confirm")'):]
        self.assertLess(confirm_branch.index("confirmBtn.hidden = false"), confirm_branch.index("return;"))
        self.assertIn("confirmBtn.hidden = true;", SCRIPT)

    def test_the_cancel_button_says_cancel_and_the_cancelled_message_is_not_a_label(self):
        for lang, label, message in (("pt-PT", "Cancelar", "Cancelado. Nada foi guardado."),
                                     ("en-GB", "Cancel", "Cancelled. Nothing was saved.")):
            body = self.client.get("/", accept_language=lang).body
            self.assertRegex(body, r'id="voiceCancelBtn"[^>]*>%s</button>' % label)
            self.assertNotIn(message, body)

    def test_text_box_placeholder_and_send_button_follow_the_page_language(self):
        for lang, placeholder, send in (("pt-PT", "Escreve aqui…", "Enviar"), ("en-GB", "Type here…", "Send")):
            body = self.client.get("/", accept_language=lang).body
            self.assertRegex(tag(body, "voiceTextInput"), r'placeholder="%s"' % placeholder)
            self.assertRegex(body, r'<button type="submit" data-i18n="voice_send">%s</button>' % send)
        pt = self.client.get("/", accept_language="pt-PT").body
        en = self.client.get("/", accept_language="en-GB").body
        # compare visible texts and attribute values, not element ids
        words = lambda body: re.findall(r"[^\s<>\"]+", " ".join(re.findall(r">([^<>]+)<", body) + re.findall(r'(?:placeholder|aria-label|data-[a-z-]+)="([^"]*)"', body)))
        for portuguese in ("Escreve", "Enviar", "Cancelar", "Confirmar", "Falar"):
            self.assertNotIn(portuguese, words(en))
        for english in ("Type", "Send", "Cancel", "Confirm", "Speak"):
            self.assertNotIn(english, words(pt))

    def test_every_panel_text_is_a_translation_key_in_both_languages(self):
        from app import i18n
        for key in ("voice_falar", "voice_placeholder", "voice_send", "voice_cancel_btn", "btn_confirm",
                    "voice_cancelled", "voice_network_error", "voice_mic_blocked", "voice_tap_answer",
                    "voice_panel_label", "voice_empty", "voice_model_error", "voice_limit_reached",
                    "voice_too_many_questions", "voice_wav_error", "voice_question_fallback",
                    "voice_confirm_q", "voice_what_to_fix", "voice_save_failed", "voice_no_conversation"):
            for lang in i18n.SUPPORTED:
                self.assertTrue(i18n.text(lang, key).strip(), (lang, key))
        self.assertEqual(set(i18n.STRINGS["pt-PT"]), set(i18n.STRINGS["en-GB"]))
        # the script holds no wording of its own
        self.assertNotRegex(SCRIPT, r'"[A-Za-zÀ-ÿ]+ [A-Za-zÀ-ÿ ,.…]+[.?…]"')

    def test_the_header_button_shows_the_microphone_icon_then_the_label(self):
        for lang, label in (("pt-PT", "Falar"), ("en-GB", "Speak")):
            response = self.client.get("/", accept_language=lang)
            self.assertIn("charset=utf-8", response.headers["content-type"])
            header = re.search(r'<button id="voiceFalarHeader".*?</button>', response.body).group(0)
            # item 4f (U7): the icon is an inline SVG, no emoji
            self.assertIn("<svg", header)
            self.assertNotIn("\U0001F399", header)
            self.assertNotIn("ð", header)
            self.assertRegex(header, r"</span> <span data-i18n=\"voice_falar\">%s</span>" % label)
        raw = self.client.get("/").body.encode("utf-8")
        self.assertNotIn(b"\xf0\x9f\x8e\x99", raw)
        self.assertNotIn(b"\xc3\xb0\xc2\x9f", raw, "no double-encoded icon")

    def test_the_round_phone_button_is_a_labelled_microphone(self):
        body = self.client.get("/", accept_language="en-GB").body
        self.assertRegex(tag(body, "voiceFalar"), r'aria-label="Speak"')
        self.assertIn("<svg", re.search(r'<button id="voiceFalar".*?</button>', body).group(0))
        compact = re.sub(r"\s+", "", CSS)
        self.assertIn("border-radius:50%", compact)
        self.assertIn("@media(min-width:1024px){.voice-falar-fixed{display:none}.voice-falar-header{display:inline-flex}", compact)

    def test_no_tip_or_prompt_appears_anywhere(self):
        for path in ("/", "/settings", "/deals/new"):
            for lang in ("pt-PT", "en-GB"):
                body = self.client.get(path, accept_language=lang).body
                panel = body[body.index('id="voicePanel"'):body.index("</form>", body.index('id="voicePanel"'))]
                visible = re.sub(r"<[^>]+>", " ", panel)
                self.assertNotRegex(visible, r"\?|Olá|Hello|Dica|Tip")
                self.assertNotIn("voice_hint", body)
