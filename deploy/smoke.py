"""Smoke test for a live Agentimo deployment, standard library only.

Given a base URL, the script checks the first screens load
(``/``, ``/deals/new``, ``/settings``, ``/scenarios/move``) and that
a natural-language move (``Move the Benfica payment to January``)
returns a before/after forecast: the posted page must name Benfica,
the source month (``2026-11`` or ``novembro de 2026``) and the target
month (``2027-01`` or ``janeiro de 2027``). It exits non-zero on any
failure and prints one line per check.

Usage: ``python3 deploy/smoke.py https://agentimo.example.com``
"""

import html.parser
import sys
import urllib.error
import urllib.parse
import urllib.request


SENTENCE = "Move the Benfica payment to January"

TIMEOUT = 30


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


def smoke(base_url):
    base = base_url.rstrip("/")
    opener = urllib.request.build_opener()
    cookies = {}
    failures = 0

    def request(method, path, params=None):
        headers = {}
        if cookies:
            headers["Cookie"] = "; ".join(
                "%s=%s" % item for item in sorted(cookies.items()))
        body = None
        if params is not None:
            body = urllib.parse.urlencode(params).encode("utf-8")
        web_request = urllib.request.Request(
            base + path, data=body, method=method, headers=headers)
        try:
            reply = opener.open(web_request, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            reply = exc
        except urllib.error.URLError as exc:
            return None, "connection failed: %s" % exc.reason
        with reply:
            text = reply.read().decode("utf-8", "replace")
            code = reply.status
            raw = reply.headers.get_all("Set-Cookie", [])
        for value in raw:
            pair = split_set_cookie(value)
            if pair is not None:
                cookies[pair[0]] = pair[1]
        return code, text

    screens = [("/", "first screen"),
               ("/deals/new", "new deal form"),
               ("/settings", "settings form"),
               ("/scenarios/move", "move scenario")]
    move_body = ""
    for path, label in screens:
        code, text = request("GET", path)
        if code is None:
            if not check("GET " + path + " loads (" + label + ")",
                         False, text):
                failures += 1
            continue
        ok = code == 200 and "<main>" in text
        if path == "/scenarios/move":
            move_body = text
            ok = ok and 'name="sentence"' in text
        if not check("GET " + path + " loads (" + label + ")",
                     ok, "HTTP %d" % code):
            failures += 1

    if move_body:
        collector = InputCollector()
        collector.feed(move_body)
        csrf = collector.values.get("csrf_token", "")
        if not check("move page carries a CSRF token", bool(csrf)):
            failures += 1
        if csrf:
            code, text = request(
                "POST", "/scenarios/move",
                {"sentence": SENTENCE, "csrf_token": csrf})
            if code is None:
                if not check("POST /scenarios/move %r returns before/after"
                             % SENTENCE, False, text):
                    failures += 1
                return failures
            has_benfica = "Benfica" in text
            has_before = ("2026-11" in text
                          or "novembro de 2026" in text)
            has_after = ("2027-01" in text
                         or "janeiro de 2027" in text)
            ok = code == 200 and has_benfica and has_before and has_after
            detail = "HTTP %d" % code
            missing = [label for label, seen in
                       (("Benfica", has_benfica),
                        ("before month", has_before),
                        ("after month", has_after)) if not seen]
            if missing:
                detail += "; missing " + ", ".join(missing)
            if not check("POST /scenarios/move %r returns before/after"
                         % SENTENCE, ok, detail):
                failures += 1
    else:
        if not check("move sentence posted", False, "no move page body"):
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
