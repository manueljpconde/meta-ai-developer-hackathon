"""The criteria map and the decision documents (criteria 14, 16 and the map rule).

Reads docs/decisions/voice-criteria-map.md and fails if a test it names
does not exist, so the map cannot drift from the code.
"""
import importlib
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
MAP = REPO / "docs" / "decisions" / "voice-criteria-map.md"

FILES = {
    "C": "app.tests.test_voice_conversation",
    "P": "app.tests.test_voice_page",
    "H": "app.tests.test_voice_http",
    "K": "app.tests.test_voice_clients",
    "E": "engine.tests.test_voice_item4",
    "J": "app.tests.test_item2c_journey",
    "S": "app.tests.test_item3c_deal_table",
    "M": "app.tests.test_voice_map",
}


def map_lines():
    lines = []
    for line in MAP.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) == 3 and re.fullmatch(r"[A-Za-z0-9-]+", parts[0]):
            lines.append(parts)
    return lines


class CriteriaMapTest(unittest.TestCase):
    def test_the_map_has_a_line_for_every_criterion(self):
        ids = {line[0] for line in map_lines()}
        expected = {"A0", "A1", "1a", "2", "3", "4", "5", "6", "7", "7a", "7b", "7c", "7d", "8", "9", "10", "11",
                    "12", "13", "14", "15", "16", "17", "S1", "S2", "S4", "7p", "8p", "10p", "11p", "12p", "13p",
                    "14p", "M2", "M3"}
        self.assertEqual(expected - ids, set())
        self.assertEqual(len(map_lines()), len({line[0] for line in map_lines()}), "one line per criterion")

    def test_every_test_named_in_the_map_exists(self):
        checked = 0
        for criterion, tests, asserts in map_lines():
            self.assertTrue(asserts.strip(), criterion)
            for ref in re.findall(r"\b([CPHKEJSM])::(\w+)::(\w+)", tests + " " + asserts):
                prefix, cls, name = ref
                module = importlib.import_module(FILES[prefix])
                case = getattr(module, cls, None)
                self.assertIsNotNone(case, "%s: no class %s::%s" % (criterion, prefix, cls))
                self.assertTrue(hasattr(case, name), "%s: no test %s::%s::%s" % (criterion, prefix, cls, name))
                self.assertTrue(name.startswith("test_"), name)
                checked += 1
        self.assertGreater(checked, 60)

    def test_no_old_test_file_is_named_in_the_map(self):
        text = MAP.read_text(encoding="utf-8")
        for old in ("test_voice_guarantees", "test_voice_wiring", "OneQuestionRuleTest", "voice_conversation.py::"):
            self.assertNotIn(old, text)


class DecisionDocumentsTest(unittest.TestCase):
    def setUp(self):
        self.func = (REPO / "docs/decisions/accounts-voice-functional.md").read_text(encoding="utf-8")
        self.tech = (REPO / "docs/decisions/accounts-voice-technical.md").read_text(encoding="utf-8")

    def section(self, text, heading):
        start = text.index(heading)
        end = text.find("\n## ", start + 4)
        return text[start:end if end != -1 else None]

    def test_documents_state_the_voice_design(self):
        d5 = self.section(self.func, "## D5. ")
        for fact in ("Falar", "bottom", "Nothing is stored before", "6\nquestions", "30 conversations",
                     "Confirmas?", "language the agent speaks", "never speaks first"):
            self.assertIn(fact, d5)
        t5 = self.section(self.tech, "## T5. ")
        for fact in ("/static/voice.js", "16 kHz", "WAV", "speechSynthesis", "60 s", "hidden", "format=json"):
            self.assertIn(fact, t5)
        t6 = self.section(self.tech, "## T6. ")
        for fact in ("/asr/transcribe", "muse-voice-transcribe-1.0", "audioEncoding", "exactly two parts",
                     "muse-spark-1.3", "/chat/completions", "30 s", "LINEAR16"):
            self.assertIn(fact, t6)
        t7 = self.section(self.tech, "## T7. ")
        for fact in ("30\nconversations", "6\nquestions", "no model call"):
            self.assertIn(fact, t7)

    def test_documents_state_the_estimated_escritura_date(self):
        a2 = self.func[self.func.index("- A2. "):]
        a2 = a2[:a2.index("- A3. ")]
        for fact in ("estimated", "15th", "escritura estimada", "(estimada)", "meados de março", "mid-March",
                     "Data estimada", "Estimated date", "forecast like any other"):
            self.assertIn(fact, a2)
        t8 = self.section(self.tech, "## T8. ")
        for fact in ("escritura_estimada", "15th", "(estimada)", "mid-March"):
            self.assertIn(fact, t8)

    def test_old_design_is_gone(self):
        for stale in ("one box on the main page", "update box"):
            self.assertNotIn(stale, self.section(self.func, "## D5. "))
        self.assertNotIn("built-in recorder with a plain form upload", self.tech)
        self.assertNotIn("Item 4 voice (Nov 2026", self.func + self.tech)


if __name__ == "__main__":
    unittest.main()
