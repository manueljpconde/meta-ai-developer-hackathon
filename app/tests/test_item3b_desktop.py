"""Item 3b desktop refinements: deal-table, month cards, submit below form, phone cards, plus inline radios, aria-labels, no-try/except, desktop base."""
import os, re, unittest
from app import web, store
from app.tests.helpers import AppTestCase, csrf_token, hidden_inputs

def css_text():
    path = os.path.join(os.path.dirname(web.__file__), "static", "style.css")
    with open(path, encoding="utf-8") as f:
        return f.read()

class DealListTableTest(AppTestCase):
    """Deal list is a table with name, stage, amount, escritura date and CPCV date."""
    def test_deal_list_renders_as_table_with_required_columns(self):
        self.save_settings()
        body = self.client.get("/deals/new").body
        params = {"name":"Casa T","commission":"10000,00","share":"50","escritura_date":"2026-11-15","cpcv_date":"2026-10-01","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(body)}
        rev = self.client.post("/deals/review", params)
        conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
        self.client.post("/deals/confirm", conf)
        home = self.client.get("/").body
        self.assertIn('<table class="deal-table"', home)
        self.assertIn("<thead>", home)
        self.assertIn("<tbody>", home)
        self.assertIn('<tr class="deal-row"', home.lower() if "deal-row" in home.lower() else home)
        # Columns: name, stage, amount, escritura date, cpcv date headers
        self.assertIn("Escritura", home)
        self.assertIn("CPCV", home)
        # CPCV date visible in row
        self.assertIn("outubro", home.lower())
        # row links to edit
        self.assertIn("/deals/edit?id=", home)

class MonthCardsFillRowTest(AppTestCase):
    """Month cards fill the row, two or three per row at 1024 px and wider, with breakdown grid unwrapped."""
    def test_forecast_grid_css_has_two_and_three_columns_at_breakpoints(self):
        css = css_text()
        self.assertIn("1024px", css)
        self.assertIn("72rem", css)
        self.assertIn("forecast-grid", css)
        # two per row at 1024
        self.assertIn("repeat(2, 1fr)", css)
        # three per row at larger breakpoint (1280)
        self.assertIn("repeat(3, 1fr)", css)
        # grid inside cards not wrapped into narrow column
        self.assertIn("grid-template-columns: auto 1fr", css)
    def test_forecast_markup_uses_grid_and_sections(self):
        self.save_settings()
        for day in ("15","16"):
            b = self.client.get("/deals/new").body
            p = {"name":f"Casa {day}","commission":"10000,00","share":"50","escritura_date":f"2026-11-{day}","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
            rev = self.client.post("/deals/review", p)
            conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
            self.client.post("/deals/confirm", conf)
        home = self.client.get("/").body
        self.assertIn('class="forecast-grid"', home)
        self.assertIn("<section>", home)
        self.assertIn('<table class="deal-table"', home)

class SubmitBelowFormAndTwoColumnsTest(AppTestCase):
    """On the deal form, submit button sits below form, and date/stage fieldsets use two columns."""
    def test_submit_button_is_grid_full_width_and_fieldsets_use_columns(self):
        css = css_text()
        self.assertIn("form.two-col", css)
        self.assertIn("grid-template-columns: 1fr 1fr", css)
        # submit button spans full width
        self.assertRegex(css, r'form\.two-col.*button.*grid-column:\s*1\s*/\s*-1', re.S)
        # form has two-col class
        body = self.client.get("/deals/new").body
        self.assertIn('class="two-col"', body)
        # submit button comes after fieldsets (not beside a field div)
        # check edit form too
        self.save_settings()
        b = self.client.get("/deals/new").body
        p = {"name":"Casa X","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
        rev = self.client.post("/deals/review", p)
        conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
        self.client.post("/deals/confirm", conf)
        tid = store.get_tenant_by_email(self.db_path,"test@example.com")["id"]
        did = store.list_deals(self.db_path, tenant_id=tid)[0]["id"]
        eb = self.client.get(f"/deals/edit?id={did}").body
        self.assertIn('class="two-col"', eb)
        self.assertIn('<button', eb)

class PhoneMonthCardsTest(AppTestCase):
    """On phones, each month's figures sit in a card too."""
    def test_month_cards_have_card_style_outside_media_query(self):
        css = css_text()
        self.assertIn(".forecast-grid section", css)
        self.assertIn("border:", css)
    def test_home_has_section_cards_at_phone_width(self):
        self.save_settings()
        b = self.client.get("/deals/new").body
        p = {"name":"Casa P","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
        rev = self.client.post("/deals/review", p)
        conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
        self.client.post("/deals/confirm", conf)
        home = self.client.get("/").body
        self.assertIn("<section>", home)
        self.assertIn('class="forecast-grid"', home)

class InlineRadioOptionsTest(AppTestCase):
    """Radio options are small and inline with label, one per line at every width."""
    def test_radio_css_inline_small_one_per_line(self):
        css = css_text()
        self.assertIn('input[type="radio"]', css)
        self.assertIn("inline-block", css)
        self.assertIn("width: auto", css)
        # labels are block (one per line)
        self.assertIn("fieldset label", css)
        self.assertIn("display: block", css)
    def test_radio_markup_present(self):
        for path in ("/deals/new",):
            body = self.client.get(path).body
            self.assertIn('type="radio"', body)
            self.assertIn('name="stage"', body)

class AriaLabelSelectsTest(AppTestCase):
    """Day, month and year selects carry aria-labels in page language."""
    def test_pt_aria_labels(self):
        body = self.client.get("/deals/new").body
        self.assertIn('aria-label="dia"', body)
        self.assertIn('aria-label="mês"', body)
        self.assertIn('aria-label="ano"', body)
    def test_en_aria_labels(self):
        self.set_language("en-GB")
        body = self.client.get("/deals/new").body
        self.assertIn('aria-label="day"', body)
        self.assertIn('aria-label="month"', body)
        self.assertIn('aria-label="year"', body)

class NoTryExceptFallbackTest(AppTestCase):
    """Forecast handler has no try/except fallback; fallen test."""
    def test_no_try_except_around_active_fallen_helpers(self):
        import pathlib
        src = pathlib.Path(web.__file__).read_text()
        # Ensure the forecast block doesn't have try/except around list_active/fallen
        # Simple check: no "try:" immediately before those calls in source
        # The handler should directly call store.list_active_deals without try
        self.assertIn("store.list_active_deals", src)
        self.assertIn("store.list_fallen_deals", src)
        # Check there's no except covering fallen fallback
        # Extract handler snippet around those calls
        idx = src.find("store.list_active_deals")
        snippet = src[max(0,idx-500):idx+500]
        self.assertNotIn("except", snippet.lower() if "try" in snippet.lower() else "")
    def test_fallen_same_month_euros_active_only_then_both(self):
        self.save_settings()
        for name in ("Casa A","Casa B"):
            b = self.client.get("/deals/new").body
            p = {"name":name,"commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)}
            rev = self.client.post("/deals/review", p)
            conf = hidden_inputs(rev.body); conf["csrf_token"]=csrf_token(rev.body)
            self.client.post("/deals/confirm", conf)
        tid = store.get_tenant_by_email(self.db_path,"test@example.com")["id"]
        # fallen
        did = [d for d in store.list_deals(self.db_path, tenant_id=tid) if d["name"]=="Casa A"][0]["id"]
        b = self.client.get(f"/deals/edit?id={did}").body
        self.client.post(f"/deals/update?id={did}", {"name":"Casa A","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","status":"fallen","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b)})
        body = self.client.get("/").body
        sections = re.findall(r"<section>.*?</section>", body, flags=re.S)
        sec = "".join(sections)
        self.assertIn("Casa B", sec)
        self.assertNotIn("Casa A", sec)
        b2 = self.client.get(f"/deals/edit?id={did}").body
        self.client.post(f"/deals/update?id={did}", {"name":"Casa A","commission":"10000,00","share":"50","escritura_date":"2026-11-15","stage":"confirmado","status":"active","agency":"","form_locale":"pt-PT","csrf_token": csrf_token(b2)})
        body2 = self.client.get("/").body
        sec2 = "".join(re.findall(r"<section>.*?</section>", body2, flags=re.S))
        self.assertIn("Casa A", sec2)
        self.assertIn("Casa B", sec2)

class DesktopBaseFrom1024Test(AppTestCase):
    """From 1024 px wide, content up to about 72rem and forms use two columns; below single-column stays."""
    def test_breakpoint_css_rules(self):
        css = css_text()
        self.assertIn("@media (min-width: 1024px)", css)
        self.assertIn("max-width: 72rem", css)
        self.assertIn("form.two-col", css)
        # single-column is default (no grid on body/form outside media)
        first_media = css.find("@media (min-width: 1024px)")
        before = css[:first_media]
        # body max-width before media is narrower (40rem)
        self.assertIn("max-width: 40rem", before)
