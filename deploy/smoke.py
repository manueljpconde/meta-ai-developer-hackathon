"""Smoke test for a live Agentimo deployment, standard library only.

The script seeds through the real pages before asserting the
scenario: it loads the move page for a CSRF token, saves example
settings, registers one Benfica deal via the review and confirm
forms (following the 303 redirect), then posts ``Move the Benfica
payment to January`` and asserts the before/after months derived
from the created deal's month and the next-occurrence rule for the
bare month name. Given a base URL, it also checks the first
screens load (``/``, ``/deals/new``, ``/settings``,
``/scenarios/move``). It exits non-zero on any failure and prints
one line per check.

Usage: ``python3 deploy/smoke.py https://agentimo.example.com``
"""

import html.parser
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


SENTENCE = "Move the Benfica payment to January"

TIMEOUT = 30

SETTINGS = {
    "share": "50",
    "iva": "23",
    "retencao": "25",
    "irs": "30",
    "ss": "10",
    "expenses": "350.00",
    "form_locale": "en-GB",
}

DEAL = {
    "name": "Benfica",
    "commission": "10000.00",
    "share": "50",
    "month": "2026-11",
    "stage": "confirmado",
    "agency": "",
    "form_locale": "en-GB",
}


class InputCollector(html.parser.HTMLParser):
    """Collect hidden input values of the first form on the page."""

    def __init__(self):
        super().__init__()
        self.values = {}
        self.in_form = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.in_form = True
        if tag == "input" and self.in_form:
            name = attrs.get("name")
            if name:
                self.values[name] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False


class AllInputs(html.parser.HTMLParser):
    """Collect hidden input values of every form on the page."""

    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"action": attrs.get("action", ""),
                            "values": {}}
            self.forms.append(self.current)
        if tag == "input" and self.current is not None:
            name = attrs.get("name")
            if name:
                self.current["values"][name] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


def split_set_cookie(value):
    pair = value.split(";", 1)[0]
    if "=" in pair:
        name, val = pair.split("=", 1)
        return name.strip(), val.strip()
    return None


def check(name, ok, detail=""):
    print(("PASS" if ok else "FAIL") + " " + name
          + (" (" + detail + ")" if detail else ""))
    return ok


def add_months(year_month, delta):
    """Shift a ``YYYY-MM`` month by delta months."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    index = (year * 12 + (month - 1)) + delta
    return "%04d-%02d" % (index // 12, index % 12 + 1)


def next_occurrence(name, current_month):
    """Next occurrence of a bare English month name from a month."""
    names = ("january", "february", "march", "april", "may", "june",
             "july", "august", "september", "october", "november",
             "december")
    index = names.index(name.lower()) + 1
    year, current = int(current_month[:4]), int(current_month[5:7])
    if index < current:
        year += 1
    return "%04d-%02d" % (year, index)


class Client:
    """HTTP client against the deployment, keeping cookies."""

    def __init__(self, base):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener()
        self.cookies = {}

    def request(self, method, path, params=None):
        headers = {}
        if self.cookies:
            headers["Cookie"] = "; ".join(
                "%s=%s" % item for item in sorted(self.cookies.items()))
        body = None
        if params is not None:
            body = urllib.parse.urlencode(params).encode("utf-8")
        web_request = urllib.request.Request(
            self.base + path, data=body, method=method, headers=headers)
        try:
            reply = self.opener.open(web_request, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            reply = exc
        except urllib.error.URLError as exc:
            return None, "connection failed: %s" % exc.reason
        code = None
        text = ""
        raw = []
        try:
            with reply:
                text = reply.read().decode("utf-8", "replace")
                code = reply.status
                raw = reply.headers.get_all("Set-Cookie", [])
        except (OSError, ValueError) as exc:
            return None, "connection failed: %s" % exc
        for value in raw:
            pair = split_set_cookie(value)
            if pair is not None:
                self.cookies[pair[0]] = pair[1]
        return code, text


def csrf(text):
    """CSRF token of the first form on a page."""
    collector = InputCollector()
    collector.feed(text)
    return collector.values.get("csrf_token", "")


def smoke(base_url):
    client = Client(base_url)
    failures = 0

    screens = [("/", "first screen"),
               ("/deals/new", "new deal form"),
               ("/settings", "settings form"),
               ("/scenarios/move", "move scenario")]
    pages = {}
    for path, label in screens:
        code, text = client.request("GET", path)
        if code is None:
            if not check("GET " + path + " loads (" + label + ")",
                         False, text):
                failures += 1
            continue
        ok = code == 200 and "<main>" in text
        if path == "/scenarios/move":
            pages["move"] = text
            ok = ok and 'name="sentence"' in text
        if not check("GET " + path + " loads (" + label + ")",
                     ok, "HTTP %d" % code):
            failures += 1

    move_body = pages.get("move", "")
    if not move_body:
        if not check("seed deal created", False, "no move page body"):
            failures += 1
        return failures
    token = csrf(move_body)
    if not check("move page carries a CSRF token", bool(token)):
        failures += 1
        return failures

    settings_token = ""
    code, text = client.request("GET", "/settings")
    if code is not None:
        settings_token = csrf(text)
    params = dict(SETTINGS)
    params["csrf_token"] = settings_token
    code, _ = client.request("POST", "/settings", params)
    if code is None:
        if not check("seed settings saved", False, "connection failed"):
            failures += 1
        return failures
    if not check("seed settings saved", code in (200, 303),
                 "HTTP %d" % code):
        failures += 1
        return failures

    code, text = client.request("GET", "/deals/new")
    if code is None:
        if not check("seed deal created", False, "connection failed"):
            failures += 1
        return failures
    params = dict(DEAL)
    params["csrf_token"] = csrf(text)
    code, text = client.request("POST", "/deals/review", params)
    if code is None or code != 200:
        if not check("seed deal created", False,
                     "review HTTP %s" % code):
            failures += 1
        return failures
    collector = AllInputs()
    collector.feed(text)
    confirm = None
    for form in collector.forms:
        if form["action"] == "/deals/confirm":
            confirm = form["values"]
            break
    if confirm is None:
        if not check("seed deal created", False, "no confirm form"):
            failures += 1
        return failures
    code, text = client.request("GET", "/deals/new")
    if code is not None:
        confirm["csrf_token"] = csrf(text)
    code, _ = client.request("POST", "/deals/confirm", confirm)
    if code is None:
        if not check("seed deal created", False, "connection failed"):
            failures += 1
        return failures
    if not check("seed deal created", code in (200, 303),
                 "HTTP %d" % code):
        failures += 1
        return failures
    deal_month = DEAL["month"]
    target = next_occurrence("January", deal_month)

    code, text = client.request("GET", "/scenarios/move")
    if code is None:
        if not check("POST /scenarios/move %r returns before/after"
                     % SENTENCE, False, "connection failed"):
            failures += 1
        return failures
    code, text = client.request(
        "POST", "/scenarios/move",
        {"sentence": SENTENCE, "csrf_token": csrf(text)})
    if code is None:
        if not check("POST /scenarios/move %r returns before/after"
                     % SENTENCE, False, "connection failed"):
            failures += 1
        return failures
    before_numeric = deal_month in text
    after_numeric = target in text
    month_names = {
        "01": "janeiro", "02": "fevereiro", "03": "março",
        "04": "abril", "05": "maio", "06": "junho",
        "07": "julho", "08": "agosto", "09": "setembro",
        "10": "outubro", "11": "novembro", "12": "dezembro",
    }
    before_local = month_names[deal_month[5:7]] in text.lower()
    after_local = month_names[target[5:7]] in text.lower()
    has_benfica = "Benfica" in text
    ok = (code == 200 and has_benfica
          and (before_numeric or before_local)
          and (after_numeric or after_local))
    detail = "HTTP %d" % code
    missing = [label for label, seen in
               (("Benfica", has_benfica),
                ("before month", before_numeric or before_local),
                ("after month", after_numeric or after_local))
               if not seen]
    if missing:
        detail += "; missing " + ", ".join(missing)
    if not check("POST /scenarios/move %r returns before/after"
                 % SENTENCE, ok, detail):
        failures += 1

    return failures


def main(argv):
    if len(argv) != 2:
        print("usage: python3 deploy/smoke.py <base-url>")
        return 2
    failures = smoke(argv[1])
    print("smoke: %s" % ("OK" if failures == 0 else
                         "%d check(s) failed" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
