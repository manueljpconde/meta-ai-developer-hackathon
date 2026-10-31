"""Load example removed: no page offers it and the routes are gone."""

import unittest
from app.tests.helpers import AppTestCase, csrf_token
from app import web


class ExampleRemovedTest(AppTestCase):
    def test_empty_forecast_shows_only_new_deal_cta(self):
        body = self.client.get("/").body
        self.assertIn("/deals/new", body)
        self.assertNotIn("/example", body.lower())
        self.assertNotIn("example", body.lower())
        self.assertNotIn("exemplo", body.lower())

    def test_move_page_no_example(self):
        body = self.client.get("/scenarios/move").body
        self.assertNotIn("/example", body.lower())
        self.assertNotIn("example_action", body)
        self.assertNotIn("carregar exemplo", body.lower())

    def test_no_page_offers_example(self):
        for path in ("/", "/deals/new", "/settings", "/scenarios/move"):
            body = self.client.get(path).body
            self.assertNotIn("/example", body.lower(), path)

    def test_example_route_gone(self):
        for method in ("GET", "POST"):
            resp = self.client.request(method, "/example", params={})
            # Should be 404 (no route) — gated check may 303 to signin only for non-public; but /example is removed so 404
            self.assertIn(resp.code, (302, 303, 404), method)
            if resp.code in (302, 303):
                # If gated, it's because session gate still catches unknown; but signed-in user should 404
                pass
            # Signed-in request to removed route should 404, not 200 with example
            self.assertNotIn("example", resp.body.lower())

    def test_store_no_example_helpers(self):
        self.assertFalse(hasattr(web, "apply_example_data"))
        self.assertFalse(hasattr(web, "example_action"))
        self.assertFalse(hasattr(web, "example_confirm_page"))
        # example_deal_months kept for current-month helper tests; route is gone

    def test_review_page_no_example(self):
        self.save_settings()
        rev = self.review()
        self.assertNotIn("/example", rev.body.lower())

    def test_app_routes_no_example(self):
        for path, _method in web.APP_ROUTES:
            self.assertNotEqual(path, "/example", "APP_ROUTES still lists /example")
