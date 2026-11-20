"""Check dashboard layout and optional SQL parameter handling."""

import json
from pathlib import Path
import sys
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))
from setup_metabase import compile_query, native_parameters, template_tags


class MetabaseConfigTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((PROJECT_DIR / "metabase" / "dashboard.json").read_text(encoding="utf-8"))

    def test_cards_have_unique_keys_and_fit_the_dashboard_grid(self):
        cards = self.spec["cards"]
        self.assertEqual(len(cards), len({card["key"] for card in cards}))
        for card in cards:
            self.assertIn(card["tab"], self.spec["tabs"])
            self.assertGreaterEqual(card["row"], 2)
            self.assertGreater(card["width"], 0)
            self.assertGreater(card["height"], 0)
            self.assertLessEqual(card["col"] + card["width"], 24)

    def test_cards_do_not_overlap(self):
        cards = self.spec["cards"]
        for index, a in enumerate(cards):
            for b in cards[index + 1:]:
                if a["tab"] == b["tab"]:
                    horizontal = a["col"] < b["col"] + b["width"] and b["col"] < a["col"] + a["width"]
                    vertical = a["row"] < b["row"] + b["height"] and b["row"] < a["row"] + a["height"]
                    self.assertFalse(horizontal and vertical, f"Overlapping cards {a['key']} and {b['key']}")

    def test_unfiltered_queries_remove_all_optional_blocks(self):
        for card in self.spec["cards"]:
            query, parameters = compile_query("\n".join(card["sql"]), {})
            self.assertNotIn("{{", query)
            self.assertNotIn("[[", query)
            self.assertEqual(parameters, [])

    def test_filter_values_are_bound_without_sql_interpolation(self):
        value = "discount'; DROP TABLE loyalty.events; --"
        query, parameters = compile_query("SELECT 1 WHERE TRUE [[AND offer_type={{offer_type}}]]", {"offer_type": value})
        self.assertNotIn(value, query)
        self.assertIn("offer_type=%s", query)
        self.assertEqual(parameters, [value])

    def test_optional_filters_are_independent_and_use_known_tags(self):
        query = "SELECT 1 WHERE TRUE [[AND offer_type={{offer_type}}]] [[AND rfm_segment={{rfm_segment}}]]"
        compiled, parameters = compile_query(query, {"rfm_segment": "Frequent recent"})
        self.assertNotIn("offer_type", compiled)
        self.assertIn("rfm_segment=%s", compiled)
        self.assertEqual(parameters, ["Frequent recent"])
        for card in self.spec["cards"]:
            self.assertLessEqual(set(template_tags("\n".join(card["sql"]))), {"offer_type", "rfm_segment"})

    def test_native_filters_use_the_template_tag_identifier(self):
        parameters = native_parameters({"offer_type": "discount"})
        self.assertEqual(parameters, [{"id": "starbucks-offer_type", "type": "category",
            "target": ["variable", ["template-tag", "offer_type"]], "value": "discount"}])

    def test_percentage_labels_preserve_literal_percent_signs(self):
        query, parameters = compile_query('SELECT 1 AS "Rate (%)" WHERE TRUE [[AND kind={{offer_type}}]]', {"offer_type": "discount"})
        self.assertIn('"Rate (%%)"', query)
        self.assertIn('kind=%s', query)
        self.assertEqual(parameters, ["discount"])


if __name__ == "__main__":
    unittest.main()
