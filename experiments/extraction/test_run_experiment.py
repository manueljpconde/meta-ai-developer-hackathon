import itertools
import json
import unittest
from pathlib import Path

import run_experiment as rx

SAMPLES = [json.loads(line) for line in Path(__file__).with_name("samples.jsonl").read_text().splitlines() if line.strip()]


class Amounts(unittest.TestCase):
    def test_pt_pt_format(self):
        self.assertEqual(rx.cents("16.995 €"), 1699500)
        self.assertEqual(rx.cents("16.995,50 €"), 1699550)
        self.assertEqual(rx.cents("12 000 €"), 1200000)
        self.assertEqual(rx.cents("12 500 €"), 1250000)
        self.assertEqual(rx.cents("12,50 €"), 1250)
        self.assertEqual(rx.cents("31.500 EUR"), 3150000)
        self.assertEqual(rx.cents("13.000 euros"), 1300000)

    def test_en_format(self):
        self.assertEqual(rx.cents("€31,500"), 3150000)
        self.assertEqual(rx.cents("EUR 16,995"), 1699500)
        self.assertEqual(rx.cents("€16,995.50"), 1699550)
        self.assertEqual(rx.cents("12.50 €"), 1250)

    def test_no_separator_reads_the_same_in_both(self):
        self.assertEqual(rx.cents("31500 €"), 3150000)

    def test_refused(self):
        for text in ("8k", "8k €", "31,5 €", "220 mil", "6,25 mil €", "1.5k", "12.5 €", "1.234 567 €", "-500 €",
                     "1,23,456 €", "€ 31.500 EUR", "16.995 € + IVA", "", "€", "12.000,5 €", "1.000.00 €"):
            self.assertIsNone(rx.cents(text), text)

    def test_no_string_is_read_two_ways(self):
        for n in range(1, 8):
            for chars in itertools.product("15., ", repeat=n):
                s = "".join(chars)
                pt, en = rx.parse_amount(rx.PT, s), rx.parse_amount(rx.EN, s)
                if pt is not None and en is not None:
                    self.assertEqual(pt, en, s)


class Shares(unittest.TestCase):
    def test_accepted(self):
        self.assertEqual(rx.share("50%"), "50")
        self.assertEqual(rx.share("50,5%"), "50.5")
        self.assertEqual(rx.share("50.5 %"), "50.5")
        self.assertEqual(rx.share("100%"), "100")

    def test_refused(self):
        for text in ("120%", "0%", "metade", "50% ou 55%", "50", "half"):
            self.assertIsNone(rx.share(text), text)


def out(**kw):
    base = dict.fromkeys(rx.KEYS)
    base.update(kw)
    return base


class Validation(unittest.TestCase):
    NOTE = "Agência Lumen, comissão 12 500 € + IVA, a minha parte 50%, dezembro, confirmado."

    def test_stated_values_pass_with_whitespace_normalised(self):
        got, invented = rx.validate(self.NOTE, out(agency_name="Agência Lumen", agency_commission_text="12 500 €",
                                                   agent_share_text="50%", expected_month="2026-12", stage="confirmado"))
        self.assertEqual(invented, [])
        self.assertEqual(got, {"agency": "Agência Lumen", "commission_cents": 1250000, "share": "50",
                               "month": "2026-12", "stage": "confirmado"})

    def test_value_not_in_note_is_invented(self):
        got, invented = rx.validate(self.NOTE, out(agency_commission_text="13.000 €", agent_share_text="45%"))
        self.assertEqual(sorted(invented), ["commission_cents", "share"])
        self.assertIsNone(got["commission_cents"])

    def test_month_and_stage_rules(self):
        got, _ = rx.validate(self.NOTE, out(expected_month="2026-09", stage="Confirmado"))
        self.assertIsNone(got["month"])
        self.assertIsNone(got["stage"])
        got, _ = rx.validate(self.NOTE, out(expected_month="2026-10", stage="provavel"))
        self.assertEqual((got["month"], got["stage"]), ("2026-10", "provavel"))

    def test_non_string_value_is_invented(self):
        _, invented = rx.validate(self.NOTE, out(agency_commission_text=12500))
        self.assertEqual(invented, ["commission_cents"])


class Scoring(unittest.TestCase):
    EXPECTED = {"agency": "Agência Lumen", "commission_cents": 1250000, "share": None, "month": "2026-12",
                "stage": "confirmado"}

    def test_null_is_safe_but_not_covered(self):
        s = rx.score(dict.fromkeys(rx.FIELDS), [], self.EXPECTED)
        self.assertEqual(s, {"unsafe": [], "correct": 0, "to_fill": 4})

    def test_wrong_value_and_invented_value_are_unsafe(self):
        got = dict(self.EXPECTED, commission_cents=1300000, share=None)
        s = rx.score(got, ["share"], self.EXPECTED)
        self.assertEqual(s, {"unsafe": ["commission_cents", "share"], "correct": 3, "to_fill": 4})

    def test_agency_matches_without_its_generic_word(self):
        for name in ("Lumen", "lumen", "Agência Lumen", "Agencia Lumen", "Lumen Agency"):
            s = rx.score(dict(self.EXPECTED, agency=name), [], self.EXPECTED)
            self.assertEqual((s["unsafe"], s["correct"]), ([], 4), name)
        self.assertEqual(rx.score({**dict.fromkeys(rx.FIELDS), "agency": "Douro Lar"}, [],
                                  dict(self.EXPECTED, agency="Imobiliária Douro Lar"))["unsafe"], [])

    def test_a_different_agency_is_still_unsafe(self):
        for name in ("Casa Norte", "Agência", "Lumen Norte"):
            self.assertEqual(rx.score(dict(self.EXPECTED, agency=name), [], self.EXPECTED)["unsafe"], ["agency"], name)

    def test_filling_an_expected_null_is_unsafe(self):
        s = rx.score(dict(self.EXPECTED, share="50"), [], self.EXPECTED)
        self.assertEqual(s["unsafe"], ["share"])


class Requests(unittest.TestCase):
    def test_plain_variant_has_no_schema(self):
        body = rx.request_body("plain", "m", "nota")
        self.assertNotIn("response_format", body)
        self.assertEqual(body["messages"][-1], {"role": "user", "content": "nota"})
        self.assertEqual(body["temperature"], 0)

    def test_reasoning_has_room_and_a_set_effort(self):
        body = rx.request_body("schema", "m", "nota", effort="minimal")
        self.assertEqual((body["max_completion_tokens"], body["reasoning_effort"]), (4096, "minimal"))
        self.assertNotIn("max_tokens", body)
        self.assertEqual(rx.request_body("schema", "m", "nota")["reasoning_effort"], "low")

    def test_schema_variant_is_strict_and_closed(self):
        rf = rx.request_body("schema", "m", "nota")["response_format"]
        self.assertEqual(rf["type"], "json_schema")
        self.assertTrue(rf["json_schema"]["strict"])
        schema = rf["json_schema"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(sorted(schema["required"]), sorted(rx.KEYS))
        self.assertEqual(sorted(schema["properties"]["stage"]["anyOf"][0]["enum"]), sorted(rx.STAGES))

    def test_fewshot_examples_are_not_samples(self):
        msgs = rx.request_body("schema_fewshot", "m", "nota")["messages"]
        self.assertEqual(len(msgs), 2 + 2 * len(rx.EXAMPLES))
        texts = {s["text"] for s in SAMPLES}
        for note, answer in rx.EXAMPLES:
            self.assertNotIn(note, texts)
            self.assertEqual(sorted(answer), sorted(rx.KEYS))

    def test_pt_variant_uses_the_portuguese_prompt(self):
        self.assertEqual(rx.request_body("schema_pt", "m", "nota")["messages"][0]["content"], rx.SYSTEM_PT)

    def test_every_variant_builds(self):
        for v in rx.VARIANTS:
            rx.request_body(v, "m", "nota")


def perfect(samples):
    """A fake endpoint answering each note with its expected outcome, in model terms."""
    answers = {}
    for s in samples:
        e = s["expected"]
        answers[s["text"]] = json.dumps(out(agency_name=e["agency"], agency_commission_text=s.get("commission_text"),
                                            agent_share_text=s.get("share_text"), expected_month=e["month"],
                                            stage=e["stage"]))
    return lambda body: (answers[body["messages"][-1]["content"]], {"prompt_tokens": 10, "completion_tokens": 5})


class Runs(unittest.TestCase):
    def test_perfect_answers_are_safe_and_fully_covered(self):
        summary, rows = rx.run_variant(SAMPLES, "schema", 2, perfect(SAMPLES), workers=4)
        self.assertEqual(summary["unsafe"], 0, [r for r in rows if r["unsafe"]])
        self.assertEqual(summary["coverage"], 1.0)
        self.assertEqual(len(rows), 2 * len(SAMPLES))

    def test_one_invented_value_in_one_repeat_is_unsafe(self):
        good = perfect(SAMPLES)
        calls = []

        def flaky(body):
            calls.append(1)
            raw, usage = good(body)
            if len(calls) == 3:
                raw = json.dumps(dict(json.loads(raw), agency_commission_text="99.999 €"))
            return raw, usage
        summary, _ = rx.run_variant(SAMPLES[:5], "schema", 1, flaky, workers=1)
        self.assertEqual(summary["unsafe"], 1)

    def test_endpoint_error_is_safe_and_counted(self):
        def down(body):
            raise OSError("down")
        summary, _ = rx.run_variant(SAMPLES[:3], "schema", 1, down, workers=1, backoff=0)
        self.assertEqual((summary["unsafe"], summary["failed_calls"], summary["coverage"]), (0, 3, 0.0))

    def test_a_transient_endpoint_error_is_retried(self):
        good, calls = perfect(SAMPLES), []

        def blip(body):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("reset")
            return good(body)
        summary, _ = rx.run_variant(SAMPLES[:1], "schema", 1, blip, workers=1, backoff=0)
        self.assertEqual((summary["failed_calls"], summary["coverage"], len(calls)), (0, 1.0, 2))

    def test_a_truncated_reply_is_a_failed_call_and_not_retried(self):
        calls = []

        def cut(body):
            calls.append(1)
            raise rx.Truncated("finish_reason=length")
        summary, rows = rx.run_variant(SAMPLES[:1], "schema", 1, cut, workers=1, backoff=0)
        self.assertEqual((summary["failed_calls"], len(calls)), (1, 1))
        self.assertIn("Truncated", rows[0]["error"])

    def test_winner_is_the_safe_variant_with_most_coverage(self):
        summaries = {"plain": {"unsafe": 0, "coverage": 0.7}, "schema": {"unsafe": 1, "coverage": 0.99},
                     "schema_pt": {"unsafe": 0, "coverage": 0.9}}
        self.assertEqual(rx.select(summaries, 0.9), "schema_pt")
        self.assertIsNone(rx.select({"plain": {"unsafe": 2, "coverage": 1.0}}, 0.9))

    def test_no_winner_below_the_coverage_bar(self):
        self.assertIsNone(rx.select({"plain": {"unsafe": 0, "coverage": 0.0}}, 0.9))


class SampleSet(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(len(SAMPLES), 60)
        self.assertEqual(len({s["id"] for s in SAMPLES}), 60)
        self.assertEqual(sum(s["split"] == "tune" for s in SAMPLES), 20)
        self.assertEqual({s["lang"] for s in SAMPLES}, {"pt", "en"})
        for s in SAMPLES:
            self.assertEqual(sorted(s["expected"]), sorted(rx.FIELDS), s["id"])

    def test_every_mode_has_three_notes_one_tuned_both_languages(self):
        modes = {}
        for s in SAMPLES:
            modes.setdefault(s["mode"], []).append(s)
        self.assertEqual(len(modes), 20)
        for mode, notes in modes.items():
            self.assertEqual(len(notes), 3, mode)
            self.assertEqual(sum(n["split"] == "tune" for n in notes), 1, mode)
            self.assertEqual({n["lang"] for n in notes}, {"pt", "en"}, mode)

    def test_expected_values_follow_from_the_stated_text(self):
        for s in SAMPLES:
            e = s["expected"]
            if e["agency"]:
                self.assertIn(e["agency"].lower(), s["text"].lower(), s["id"])
            if e["commission_cents"] is not None:
                self.assertIn(s["commission_text"], s["text"], s["id"])
                self.assertEqual(rx.cents(s["commission_text"]), e["commission_cents"], s["id"])
            if e["share"] is not None:
                self.assertIn(s["share_text"], s["text"], s["id"])
                self.assertEqual(rx.share(s["share_text"]), e["share"], s["id"])


if __name__ == "__main__":
    unittest.main()
