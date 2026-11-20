"""Check clustered inference against a direct sandwich calculation and edge cases."""

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compare_campaigns import adjust_family, analyze, catalog_pairs, compare_rates
from test_offer_funnel import DatabaseTestCase


def example_data():
    rows = []
    for customer in range(12):
        for arm in ("A", "B"):
            outcome = int(customer % (3 if arm == "A" else 2) == 0)
            for _ in range(2):
                rows.append({
                    "delivery_id": len(rows) + 1, "customer_id": f'C{customer}',
                    "offer_id": arm, "received_hour": 168,
                    "completed_after_view": outcome, "rfm_segment": "Other recent",
                })
    return pd.DataFrame(rows)


class CampaignComparisonTests(unittest.TestCase):
    def test_cluster_variance_matches_direct_calculation(self):
        data = example_data()
        result = compare_rates(data, "A", "B")
        a, b = data.loc[data.offer_id.eq("A")], data.loc[data.offer_id.eq("B")]
        rate_a, rate_b = a.completed_after_view.mean(), b.completed_after_view.mean()
        contribution_a = (a.completed_after_view - rate_a).groupby(a.customer_id).sum() / len(a)
        contribution_b = (b.completed_after_view - rate_b).groupby(b.customer_id).sum() / len(b)
        clusters, observations = data.customer_id.nunique(), len(data)
        correction = clusters / (clusters - 1) * (observations - 1) / (observations - 2)
        standard_error = np.sqrt(correction * ((contribution_b - contribution_a) ** 2).sum())
        self.assertAlmostEqual(result["difference_pp"], 100 * (rate_b - rate_a))
        self.assertAlmostEqual(result["std_error_pp"], 100 * standard_error)
        expected_p = 2 * stats.t.sf(abs((rate_b - rate_a) / standard_error), df=clusters - 1)
        self.assertAlmostEqual(result["p_value"], expected_p)
        critical = stats.t.ppf(.975, clusters - 1)
        self.assertAlmostEqual(result["ci95_low_pp"], 100 * (rate_b - rate_a - critical * standard_error))

    def test_reversing_arms_reverses_effect_and_interval(self):
        data = example_data()
        forward, reverse = compare_rates(data, "A", "B"), compare_rates(data, "B", "A")
        self.assertAlmostEqual(forward["difference_pp"], -reverse["difference_pp"])
        self.assertAlmostEqual(forward["ci95_low_pp"], -reverse["ci95_high_pp"])
        self.assertAlmostEqual(forward["p_value"], reverse["p_value"])

    def test_repeated_rows_do_not_create_independent_customers(self):
        data = example_data()
        baseline = compare_rates(data, "A", "B")
        repeated = compare_rates(pd.concat([data] * 10, ignore_index=True), "A", "B")
        self.assertEqual(repeated["customer_clusters"], baseline["customer_clusters"])
        self.assertAlmostEqual(repeated["difference_pp"], baseline["difference_pp"])
        self.assertGreater(repeated["std_error_pp"], .95 * baseline["std_error_pp"])

    def test_waves_with_one_arm_are_excluded(self):
        data = example_data()
        extra = data.loc[data.offer_id.eq("A")].assign(received_hour=336)
        result = compare_rates(pd.concat([data, extra]), "A", "B")
        self.assertEqual(result["common_waves"], [168])
        self.assertEqual(result["excluded_for_wave_support"], len(extra))
        self.assertEqual(result["deliveries_a"], 24)

    def test_missing_arm_and_degenerate_outcomes_remain_unestimated(self):
        data = example_data()
        missing = compare_rates(data.loc[data.offer_id.eq("A")], "A", "B")
        self.assertEqual(missing["status"], "no_common_waves")
        self.assertIsNone(missing["p_value"])
        degenerate = compare_rates(data.assign(completed_after_view=0), "A", "B")
        self.assertEqual(degenerate["status"], "degenerate_variance")
        self.assertIsNone(degenerate["p_value"])

    def test_holm_preserves_the_planned_family(self):
        results = [{"p_value": value} for value in (.01, .04, None)]
        adjust_family(results)
        self.assertAlmostEqual(results[0]["p_holm"], .03)
        self.assertAlmostEqual(results[1]["p_holm"], .08)
        self.assertIsNone(results[2]["p_holm"])
        self.assertTrue(results[0]["reject_holm_05"])
        self.assertFalse(results[1]["reject_holm_05"])

    def test_catalog_pairing_uses_terms_and_orders_by_duration(self):
        catalog = pd.DataFrame([
            {"offer_id": "A", "offer_type": "discount", "difficulty": 10, "reward": 2, "duration_days": 10},
            {"offer_id": "B", "offer_type": "discount", "difficulty": 10, "reward": 2, "duration_days": 7},
            {"offer_id": "C", "offer_type": "discount", "difficulty": 20, "reward": 5, "duration_days": 10},
        ])
        pairs = catalog_pairs(catalog)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["offer_a"]["offer_id"], "B")
        self.assertEqual(pairs[0]["offer_b"]["offer_id"], "A")

    def test_invalid_inputs_are_rejected(self):
        data = example_data()
        with self.assertRaises(ValueError):
            compare_rates(data.assign(completed_after_view=2), "A", "B")
        with self.assertRaises(ValueError):
            analyze(pd.concat([data, data]), pd.DataFrame())


class CampaignInputTests(DatabaseTestCase):
    horizon_hour = 504

    def test_input_keeps_eligible_delivery_and_preoffer_segment(self):
        self.event("transaction", 160)
        receipt = self.event("offer received", 168)
        self.event("offer viewed", 174)
        self.event("offer completed", 180)
        row = self.connection.execute("SELECT * FROM loyalty.campaign_comparison_inputs").fetchone()
        self.assertEqual(row["delivery_id"], receipt)
        self.assertEqual(row["completed_after_view"], 1)
        self.assertNotEqual(row["rfm_segment"], "Insufficient history")

    def test_early_history_and_same_hour_completion_are_handled(self):
        self.event("offer received", 0)
        self.event("offer viewed", 1)
        self.event("offer completed", 2)
        receipt = self.event("offer received", 168)
        self.event("offer viewed", 174)
        self.event("offer completed", 174)
        rows = self.connection.execute("SELECT * FROM loyalty.campaign_comparison_inputs").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["delivery_id"], receipt)
        self.assertEqual(rows[0]["completed_after_view"], 0)


if __name__ == "__main__":
    unittest.main()
