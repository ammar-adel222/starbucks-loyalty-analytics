WITH checks AS (
    SELECT 'one snapshot per customer' AS check_name,
        (SELECT COUNT(*)::NUMERIC FROM loyalty.customer_rfm) AS actual,
        (SELECT COUNT(*)::NUMERIC FROM loyalty.customers) AS expected
    UNION ALL
    SELECT 'unique customer snapshots',
        (SELECT COUNT(DISTINCT customer_id) FROM loyalty.customer_rfm),
        (SELECT COUNT(*) FROM loyalty.customers)
    UNION ALL
    SELECT 'snapshot purchase count',
        (SELECT COALESCE(SUM(purchase_count), 0) FROM loyalty.customer_rfm),
        (SELECT COUNT(*) FROM loyalty.transactions)
    UNION ALL
    SELECT 'snapshot spend',
        (SELECT COALESCE(SUM(total_spend), 0) FROM loyalty.customer_rfm),
        (SELECT COALESCE(SUM(transaction_amount), 0) FROM loyalty.transactions)
    UNION ALL
    SELECT 'all purchase customers assigned a cohort',
        (SELECT COUNT(*) FROM loyalty.customer_purchase_cohorts),
        (SELECT COUNT(DISTINCT customer_id) FROM loyalty.transactions)
    UNION ALL
    SELECT 'retention week zero equals cohort size',
        (SELECT COUNT(*) FROM loyalty.weekly_purchase_retention WHERE weeks_since_first_purchase = 0 AND active_customers <> cohort_customers), 0
    UNION ALL
    SELECT 'retention only complete observable weeks',
        (SELECT COUNT(*) FROM loyalty.weekly_purchase_retention
         WHERE (purchase_week + 1) * 168 > (SELECT MAX(time_hours) FROM loyalty.events)), 0
    UNION ALL
    SELECT 'retention counts within bounds',
        (SELECT COUNT(*) FROM loyalty.weekly_purchase_retention
         WHERE active_customers < 0 OR active_customers > cohort_customers), 0
    UNION ALL
    SELECT 'unique cohort week cells',
        (SELECT COUNT(DISTINCT (cohort_week, purchase_week)) FROM loyalty.weekly_purchase_retention),
        (SELECT COUNT(*) FROM loyalty.weekly_purchase_retention)
    UNION ALL
    SELECT 'segment customer counts',
        (SELECT COALESCE(SUM(customers), 0) FROM loyalty.rfm_segment_summary),
        (SELECT COUNT(*) FROM loyalty.customers)
    UNION ALL
    SELECT 'pre-offer features use earlier purchases',
        (SELECT COUNT(*) FROM loyalty.customer_rfm_before_offers
         WHERE last_purchase_hour >= received_hour OR last_purchase_hour < received_hour - 168), 0
    UNION ALL
    SELECT 'pre-offer insufficient-history label',
        (SELECT COUNT(*) FROM loyalty.customer_rfm_before_offers
         WHERE (rfm_segment = 'Insufficient history') IS DISTINCT FROM (NOT full_history_observed)), 0
    UNION ALL
    SELECT 'pre-offer unique customer-hour rows',
        (SELECT COUNT(DISTINCT (customer_id, received_hour)) FROM loyalty.customer_rfm_before_offers),
        (SELECT COUNT(*) FROM loyalty.customer_rfm_before_offers)
    UNION ALL
    SELECT 'pre-offer population coverage',
        (SELECT COUNT(*) FROM loyalty.customer_rfm_before_offers),
        (SELECT COUNT(*) FROM loyalty.customers)
            * (SELECT COUNT(DISTINCT received_hour) FROM loyalty.offer_receipts)
    UNION ALL
    SELECT 'all deliveries retain an RFM group',
        (SELECT COALESCE(SUM(deliveries), 0) FROM loyalty.offer_funnel_by_rfm),
        (SELECT COUNT(*) FROM loyalty.offer_deliveries)
    UNION ALL
    SELECT 'insufficient history excluded from campaign rates',
        (SELECT COALESCE(SUM(eligible_deliveries), 0) FROM loyalty.offer_funnel_by_rfm
         WHERE rfm_segment = 'Insufficient history'), 0
    UNION ALL
    SELECT 'RFM campaign denominators reconcile',
        (SELECT COALESCE(SUM(eligible_deliveries), 0) FROM loyalty.offer_funnel_by_rfm),
        (SELECT COUNT(*) FROM loyalty.offer_deliveries WHERE eligible_for_rates AND received_hour >= 168)
)
SELECT check_name, actual, expected, actual = expected AS passed FROM checks ORDER BY check_name;
