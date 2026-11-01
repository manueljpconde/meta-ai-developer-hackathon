"""No-deals style tokens and empty-state hint."""
import os
from app import web
from app.tests.helpers import AppTestCase

class StyleTokensTest(AppTestCase):
    def read_css(self):
        path = os.path.join(os.path.dirname(web.__file__), "static", "style.css")
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    def test_light_theme_tokens(self):
        css = self.read_css()
        for token in ("#f6f7f4", "#16302c", "#5f6f6a", "#f2b705", "#fdf3d0", "#a7cec0", "#e6ebe8", "#9e2f25", "#f6e2de", "#2f5b8a", "#e4ecf5"):
            self.assertIn(token, css, token)
    def test_font_stack_without_external_assets(self):
        css = self.read_css()
        self.assertIn("Figtree", css)
        self.assertIn("system-ui", css)
        self.assertNotIn("@import", css)
        self.assertNotIn("http://", css)
        self.assertNotIn("https://", css)
    def test_primary_buttons_and_focus(self):
        css = self.read_css()
        self.assertIn("button", css)
        self.assertIn("#16302c", css)
        self.assertIn("#f2b705", css)
    def test_viewport_and_responsive_layout(self):
        body = self.client.get("/").body
        self.assertIn('name="viewport"', body)
        css = self.read_css()
        self.assertIn("max-width", css)
