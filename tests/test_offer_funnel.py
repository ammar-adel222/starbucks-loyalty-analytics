"""Integration checks against a disposable database on the configured PostgreSQL server."""

from pathlib import Path
import sys
import unittest
import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))
from import_data import connection_settings


def drop_test_database(settings, name):
    with psycopg.connect(**settings, autocommit=True) as connection:
        connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


class OfferFunnelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = connection_settings(PROJECT_DIR / ".env")
        name = "loyalty_funnel_test_" + uuid.uuid4().hex[:12]
        with psycopg.connect(**settings, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        cls.addClassCleanup(drop_test_database, settings, name)
        cls.connection = psycopg.connect(**dict(settings, dbname=name), row_factory=dict_row)
        cls.addClassCleanup(cls.connection.close)
        for filename in ("001_schema.sql", "005_offer_funnel.sql"):
            cls.connection.execute((PROJECT_DIR / "sql" / filename).read_text(encoding="utf-8"))
        cls.connection.commit()

    def setUp(self):
        self.batch_id = uuid.uuid4()
        self.line = 0
        self.connection.execute(
            "INSERT INTO loyalty.ingestion_batches (batch_id, manifest) VALUES (%s, '{}')", (self.batch_id,)
        )
        source = self.raw("profile.json", {"id": "C"})
        self.connection.execute(
            "INSERT INTO loyalty.customers (customer_id, member_since, source_record_id) VALUES ('C', '2017-01-01', %s)",
            (source,),
        )
        self.offer("O", "discount")
        self.event("transaction", 100)

    def tearDown(self):
        self.connection.rollback()

    def raw(self, filename, payload):
        self.line += 1
        return self.connection.execute(
            "INSERT INTO loyalty.raw_records (batch_id, source_file, source_line, payload) VALUES (%s, %s, %s, %s) RETURNING raw_record_id",
            (self.batch_id, filename, self.line, Jsonb(payload)),
        ).fetchone()["raw_record_id"]

    def offer(self, offer_id, offer_type):
        source = self.raw("portfolio.json", {"id": offer_id})
        self.connection.execute(
            "INSERT INTO loyalty.offers VALUES (%s, %s, 10, 2, 2, %s)", (offer_id, offer_type, source)
        )
        self.connection.execute("INSERT INTO loyalty.offer_channels VALUES (%s, 'email'), (%s, 'mobile')", (offer_id, offer_id))

    def event(self, event_type, hour, offer_id="O"):
        is_purchase = event_type == "transaction"
        source = self.raw("transcript.json", {"event": event_type})
        return self.connection.execute(
            """INSERT INTO loyalty.events
               (customer_id, event_type, time_hours, offer_id, transaction_amount, completion_reward, source_record_id)
               VALUES ('C', %s, %s, %s, %s, %s, %s) RETURNING event_id""",
            (event_type, hour, None if is_purchase else offer_id,
             10 if is_purchase else None, 2 if event_type == "offer completed" else None, source),
        ).fetchone()["event_id"]

    def delivery(self, delivery_id):
        return self.connection.execute("SELECT * FROM loyalty.offer_deliveries WHERE delivery_id = %s", (delivery_id,)).fetchone()

    def test_repeated_completion_counts_as_one_converted_delivery(self):
        receipt = self.event("offer received", 0)
        self.event("offer viewed", 6)
        self.event("offer completed", 12)
        self.event("offer completed", 12)
        delivery = self.delivery(receipt)
        self.assertEqual(delivery["completion_event_count"], 2)
        self.assertEqual(delivery["completion_status"], "view_before_completion")
        summary = self.connection.execute("SELECT * FROM loyalty.offer_funnel_by_offer").fetchone()
        self.assertEqual(summary["completed_after_view"], 1)
        self.assertEqual(summary["deliveries"], 1)

    def test_same_hour_order_is_unknown(self):
        receipt = self.event("offer received", 0)
        self.event("offer completed", 6)
        self.event("offer viewed", 6)
        self.assertEqual(self.delivery(receipt)["completion_status"], "view_same_hour_as_completion")

    def test_view_after_completion_and_missing_view(self):
        receipt = self.event("offer received", 0)
        self.event("offer completed", 6)
        self.assertEqual(self.delivery(receipt)["completion_status"], "no_recorded_view")
        self.event("offer viewed", 12)
        self.assertEqual(self.delivery(receipt)["completion_status"], "view_after_completion")

    def test_expiry_is_inclusive_and_later_events_are_unmatched(self):
        receipt = self.event("offer received", 0)
        boundary_event = self.event("offer completed", 48)
        late_event = self.event("offer viewed", 49)
        self.assertTrue(self.delivery(receipt)["was_completed"])
        boundary = self.connection.execute("SELECT * FROM loyalty.offer_event_matches WHERE event_id = %s", (boundary_event,)).fetchone()
        self.assertEqual(boundary["match_status"], "matched")
        self.assertEqual(boundary["expiry_boundary_count"], 1)
        self.assertEqual(boundary["expiry_exclusive_candidate_count"], 0)
        late = self.connection.execute("SELECT match_status FROM loyalty.offer_event_matches WHERE event_id = %s", (late_event,)).fetchone()
        self.assertEqual(late["match_status"], "unmatched")

    def test_overlap_flags_every_candidate_delivery(self):
        first = self.event("offer received", 0)
        second = self.event("offer received", 24)
        ambiguous = self.event("offer viewed", 30)
        match = self.connection.execute("SELECT * FROM loyalty.offer_event_matches WHERE event_id = %s", (ambiguous,)).fetchone()
        self.assertEqual(match["candidate_count"], 2)
        self.assertIsNone(match["delivery_id"])
        for delivery_id in (first, second):
            delivery = self.delivery(delivery_id)
            self.assertEqual(delivery["ambiguous_event_count"], 1)
            self.assertFalse(delivery["eligible_for_rates"])
        boundary_event = self.event("offer completed", 48)
        boundary = self.connection.execute("SELECT * FROM loyalty.offer_event_matches WHERE event_id = %s", (boundary_event,)).fetchone()
        self.assertEqual(boundary["candidate_count"], 2)
        self.assertEqual(boundary["expiry_boundary_count"], 1)
        self.assertIsNone(boundary["delivery_id"])

    def test_same_hour_receipts_are_excluded(self):
        first = self.event("offer received", 0)
        second = self.event("offer received", 0)
        for delivery_id in (first, second):
            self.assertFalse(self.delivery(delivery_id)["eligible_for_rates"])

    def test_partial_followup_is_excluded(self):
        receipt = self.event("offer received", 96)
        self.assertFalse(self.delivery(receipt)["full_window_observed"])
        self.assertFalse(self.delivery(receipt)["eligible_for_rates"])

    def test_informational_completion_rates_are_null(self):
        self.offer("I", "informational")
        self.event("offer received", 0, "I")
        self.event("offer viewed", 6, "I")
        summary = self.connection.execute("SELECT * FROM loyalty.offer_funnel_by_offer WHERE offer_id = 'I'").fetchone()
        self.assertEqual(summary["view_rate_pct"], 100)
        self.assertIsNone(summary["any_completion_rate_pct"])
        self.assertIsNone(summary["completion_after_view_rate_pct"])


if __name__ == "__main__":
    unittest.main()
