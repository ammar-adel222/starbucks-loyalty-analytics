SELECT * FROM loyalty.weekly_purchase_retention
ORDER BY cohort_week, weeks_since_first_purchase;

-- Show cohort sizes even when no complete follow-up week is available.
SELECT cohort_week, COUNT(*) AS cohort_customers
FROM loyalty.customer_purchase_cohorts GROUP BY cohort_week ORDER BY cohort_week;

SELECT * FROM loyalty.rfm_segment_summary ORDER BY total_spend DESC;

SELECT DISTINCT as_of_hour, frequent_cutoff, higher_spend_cutoff FROM loyalty.customer_rfm;

-- Snapshot segments describe the whole recorded history; pre-offer segments use seven days.
SELECT received_hour, MAX(frequent_cutoff) AS frequent_cutoff,
    MAX(higher_spend_cutoff) AS higher_spend_cutoff,
    COUNT(*) FILTER (WHERE full_history_observed) AS customers_with_full_history
FROM loyalty.customer_rfm_before_offers GROUP BY received_hour ORDER BY received_hour;

-- Aggregate counts before calculating rates. Customer counts across offers can overlap.
SELECT rfm_segment, offer_type, SUM(deliveries) AS deliveries,
    SUM(eligible_deliveries) AS eligible_deliveries,
    SUM(viewed_deliveries) AS viewed_deliveries,
    SUM(completed_after_view) AS completed_after_view,
    ROUND(100.0 * SUM(viewed_deliveries) / NULLIF(SUM(eligible_deliveries), 0), 2) AS view_rate_pct,
    ROUND(100.0 * SUM(completed_after_view) / NULLIF(SUM(eligible_reward_deliveries), 0), 2) AS completion_after_view_rate_pct
FROM loyalty.offer_funnel_by_rfm
GROUP BY rfm_segment, offer_type ORDER BY rfm_segment, offer_type;

SELECT rfm_segment, offer_id, offer_type, channel_combination,
    deliveries, eligible_deliveries, eligible_customers,
    view_rate_pct, any_completion_rate_pct, completion_after_view_rate_pct
FROM loyalty.offer_funnel_by_rfm
ORDER BY rfm_segment, offer_type, offer_id;
