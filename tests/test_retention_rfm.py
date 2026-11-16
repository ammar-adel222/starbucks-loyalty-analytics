"""Regression checks for cohort boundaries, RFM membership, and pre-offer leakage."""

import unittest

from test_offer_funnel import DatabaseTestCase


class RetentionRfmTests(DatabaseTestCase):
    horizon_hour = None

    def features(self, customer_id="C", hour=168):
        return self.connection.execute(
            "SELECT * FROM loyalty.customer_rfm_before_offers WHERE customer_id = %s AND received_hour = %s",
            (customer_id, hour),
        ).fetchone()

    def test_retention_deduplicates_customers_and_keeps_zero_cells(self):
        self.customer("D")
        self.customer("N")
        for hour in (0, 10, 20, 200, 504):
            self.event("transaction", hour)
        for hour in (168, 337):
            self.event("transaction", hour, customer_id="D")
        rows = self.connection.execute(
            "SELECT * FROM loyalty.weekly_purchase_retention ORDER BY cohort_week, purchase_week"
        ).fetchall()
        self.assertEqual([(r["cohort_week"], r["purchase_week"], r["active_customers"]) for r in rows],
                         [(0, 0, 1), (0, 1, 1), (0, 2, 0), (1, 1, 1), (1, 2, 1)])
        self.assertTrue(all(r["cohort_customers"] == 1 for r in rows))
        self.assertEqual(rows[2]["retention_rate_pct"], 0)

    def test_partial_latest_cohort_is_preserved_without_retention_cells(self):
        self.customer("Late")
        self.event("transaction", 0)
        self.event("transaction", 714)
        self.event("transaction", 700, customer_id="Late")
        cohort = self.connection.execute(
            "SELECT cohort_week FROM loyalty.customer_purchase_cohorts WHERE customer_id = 'Late'"
        ).fetchone()
        self.assertEqual(cohort["cohort_week"], 4)
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) AS cells FROM loyalty.weekly_purchase_retention WHERE cohort_week = 4"
        ).fetchone()["cells"], 0)

    def test_snapshot_preserves_nonbuyers_and_reconciles_spend(self):
        self.customer("N")
        self.event("transaction", 0, amount=10)
        self.event("transaction", 714, amount=20)
        snapshot = self.connection.execute(
            "SELECT * FROM loyalty.customer_rfm WHERE customer_id = 'C'"
        ).fetchone()
        self.assertEqual(snapshot["purchase_count"], 2)
        self.assertEqual(snapshot["total_spend"], 30)
        self.assertEqual(snapshot["recency_hours"], 0)
        nonbuyer = self.connection.execute(
            "SELECT * FROM loyalty.customer_rfm WHERE customer_id = 'N'"
        ).fetchone()
        self.assertEqual(nonbuyer["rfm_segment"], "No purchases in window")
        self.assertIsNone(nonbuyer["recency_hours"])
        self.assertEqual(nonbuyer["total_spend"], 0)

    def test_preoffer_history_includes_start_and_excludes_same_hour_and_future(self):
        self.event("offer received", 0)
        self.event("offer received", 168)
        for hour, amount in ((0, 10), (167, 20), (168, 100), (169, 1000)):
            self.event("transaction", hour, amount=amount)
        before = self.features()
        self.assertEqual(before["purchase_count"], 2)
        self.assertEqual(before["total_spend"], 30)
        self.assertEqual(before["last_purchase_hour"], 167)
        self.assertTrue(before["full_history_observed"])
        self.assertEqual(self.features(hour=0)["rfm_segment"], "Insufficient history")

    def test_preoffer_lookback_excludes_older_purchases(self):
        self.event("offer received", 336)
        for hour, amount in ((167, 100), (168, 5), (335, 15), (336, 1000)):
            self.event("transaction", hour, amount=amount)
        before = self.features(hour=336)
        self.assertEqual(before["purchase_count"], 2)
        self.assertEqual(before["total_spend"], 20)

    def test_future_purchases_cannot_change_earlier_segment(self):
        self.event("offer received", 168)
        self.event("transaction", 160)
        before = self.features()
        self.event("transaction", 169, amount=1000)
        self.assertEqual(self.features(), before)

    def test_equal_metrics_receive_equal_segments(self):
        self.customer("D")
        self.event("transaction", 100)
        self.event("transaction", 100, customer_id="D")
        rows = self.connection.execute("SELECT * FROM loyalty.customer_rfm ORDER BY customer_id").fetchall()
        self.assertEqual(rows[0]["rfm_segment"], rows[1]["rfm_segment"])
        self.assertEqual(rows[0]["frequent_cutoff"], rows[1]["frequent_cutoff"])

    def test_segment_boundaries_are_explicit(self):
        cases = [
            (0, 0, None, "No purchases in window"),
            (3, 50, 72, "Frequent, higher-spend recent"),
            (3, 10, 73, "Previously active, less recent"),
            (1, 10, 73, "Occasional, less recent"),
            (3, 10, 72, "Frequent recent"),
            (1, 50, 72, "Higher-spend recent"),
            (1, 10, 72, "Other recent"),
        ]
        for count, spend, recency, expected in cases:
            with self.subTest(expected=expected):
                result = self.connection.execute(
                    "SELECT loyalty.classify_rfm(%s::BIGINT, %s::NUMERIC, %s::NUMERIC, 3, 50) AS segment",
                    (count, spend, recency),
                ).fetchone()
                self.assertEqual(result["segment"], expected)

    def test_insufficient_history_has_no_campaign_denominator(self):
        self.event("offer received", 0)
        self.event("offer viewed", 1)
        self.event("offer completed", 2)
        self.event("transaction", 100)
        row = self.connection.execute("SELECT * FROM loyalty.offer_funnel_by_rfm").fetchone()
        self.assertEqual(row["rfm_segment"], "Insufficient history")
        self.assertEqual(row["deliveries"], 1)
        self.assertEqual(row["eligible_deliveries"], 0)
        self.assertIsNone(row["completion_after_view_rate_pct"])


if __name__ == "__main__":
    unittest.main()
