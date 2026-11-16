-- Weeks are anchored at hour zero. Only complete calendar weeks enter retention.
CREATE OR REPLACE VIEW loyalty.customer_purchase_cohorts AS
SELECT customer_id, MIN(time_hours) AS first_purchase_hour,
    FLOOR(MIN(time_hours) / 168.0)::INTEGER AS cohort_week
FROM loyalty.transactions
GROUP BY customer_id;

CREATE OR REPLACE VIEW loyalty.weekly_purchase_retention AS
WITH cohort_sizes AS (
    SELECT cohort_week, COUNT(*) AS cohort_customers
    FROM loyalty.customer_purchase_cohorts
    GROUP BY cohort_week
), customer_weeks AS (
    SELECT DISTINCT customer_id, FLOOR(time_hours / 168.0)::INTEGER AS purchase_week
    FROM loyalty.transactions
), complete_weeks AS (
    SELECT GENERATE_SERIES(0, FLOOR(MAX(time_hours) / 168.0)::INTEGER - 1) AS purchase_week
    FROM loyalty.events
), activity AS (
    SELECT c.cohort_week, w.purchase_week, COUNT(*) AS active_customers
    FROM loyalty.customer_purchase_cohorts AS c
    JOIN customer_weeks AS w USING (customer_id)
    GROUP BY c.cohort_week, w.purchase_week
)
SELECT c.cohort_week, w.purchase_week, w.purchase_week - c.cohort_week AS weeks_since_first_purchase,
    c.cohort_customers, COALESCE(a.active_customers, 0) AS active_customers,
    ROUND(100.0 * COALESCE(a.active_customers, 0) / c.cohort_customers, 2) AS retention_rate_pct
FROM cohort_sizes AS c
JOIN complete_weeks AS w ON w.purchase_week >= c.cohort_week
LEFT JOIN activity AS a ON a.cohort_week = c.cohort_week AND a.purchase_week = w.purchase_week;

-- A shared rule keeps snapshot and pre-offer segment labels consistent.
-- Cutoffs are empirical within each observation window. Equal values stay together.
CREATE OR REPLACE FUNCTION loyalty.classify_rfm(
    purchase_count BIGINT, total_spend NUMERIC, recency_hours NUMERIC,
    frequent_cutoff NUMERIC, higher_spend_cutoff NUMERIC
) RETURNS TEXT LANGUAGE SQL IMMUTABLE AS $$
    SELECT CASE
        WHEN purchase_count = 0 THEN 'No purchases in window'
        WHEN recency_hours > 72 AND (purchase_count >= frequent_cutoff OR total_spend >= higher_spend_cutoff)
            THEN 'Previously active, less recent'
        WHEN recency_hours > 72 THEN 'Occasional, less recent'
        WHEN purchase_count >= frequent_cutoff AND total_spend >= higher_spend_cutoff
            THEN 'Frequent, higher-spend recent'
        WHEN purchase_count >= frequent_cutoff THEN 'Frequent recent'
        WHEN total_spend >= higher_spend_cutoff THEN 'Higher-spend recent'
        ELSE 'Other recent'
    END;
$$;

CREATE OR REPLACE VIEW loyalty.customer_rfm AS
WITH boundary AS (
    SELECT MAX(time_hours) AS as_of_hour FROM loyalty.events
), metrics AS (
    SELECT c.customer_id, b.as_of_hour,
        COUNT(t.event_id) AS purchase_count,
        COALESCE(SUM(t.transaction_amount), 0) AS total_spend,
        MIN(t.time_hours) AS first_purchase_hour,
        MAX(t.time_hours) AS last_purchase_hour,
        b.as_of_hour - MAX(t.time_hours) AS recency_hours
    FROM loyalty.customers AS c
    CROSS JOIN boundary AS b
    LEFT JOIN loyalty.transactions AS t ON t.customer_id = c.customer_id AND t.time_hours <= b.as_of_hour
    GROUP BY c.customer_id, b.as_of_hour
), cutoffs AS (
    SELECT PERCENTILE_DISC(0.75) WITHIN GROUP (ORDER BY purchase_count) AS frequent_cutoff,
        PERCENTILE_DISC(0.75) WITHIN GROUP (ORDER BY total_spend) AS higher_spend_cutoff
    FROM metrics WHERE purchase_count > 0
)
SELECT m.*, ROUND(m.recency_hours / 24.0, 2) AS recency_days,
    c.frequent_cutoff, c.higher_spend_cutoff,
    loyalty.classify_rfm(m.purchase_count, m.total_spend, m.recency_hours,
        c.frequent_cutoff, c.higher_spend_cutoff) AS rfm_segment
FROM metrics AS m CROSS JOIN cutoffs AS c;

CREATE OR REPLACE VIEW loyalty.rfm_segment_summary AS
SELECT rfm_segment, COUNT(*) AS customers,
    SUM(purchase_count) AS purchases, SUM(total_spend) AS total_spend,
    ROUND(100.0 * SUM(total_spend) / NULLIF(SUM(SUM(total_spend)) OVER (), 0), 2) AS spend_share_pct,
    ROUND(AVG(total_spend), 2) AS spend_per_customer,
    ROUND(AVG(recency_hours) / 24.0, 2) AS avg_recency_days
FROM loyalty.customer_rfm
GROUP BY rfm_segment;

CREATE INDEX IF NOT EXISTS events_purchase_customer_time_idx
    ON loyalty.events (customer_id, time_hours) INCLUDE (transaction_amount)
    WHERE event_type = 'transaction';

-- Compute features once per customer and delivery hour, before attaching offers.
-- All customers establish each hour's cutoffs, avoiding weighting multi-offer recipients twice.
CREATE OR REPLACE VIEW loyalty.customer_rfm_before_offers AS
WITH delivery_hours AS (
    SELECT DISTINCT received_hour FROM loyalty.offer_receipts
), metrics AS (
    SELECT c.customer_id, h.received_hour,
        h.received_hour >= 168 AS full_history_observed,
        COUNT(t.event_id) AS purchase_count,
        COALESCE(SUM(t.transaction_amount), 0) AS total_spend,
        MAX(t.time_hours) AS last_purchase_hour,
        h.received_hour - MAX(t.time_hours) AS recency_hours
    FROM loyalty.customers AS c
    CROSS JOIN delivery_hours AS h
    LEFT JOIN loyalty.transactions AS t
        ON t.customer_id = c.customer_id
        AND t.time_hours >= h.received_hour - 168
        AND t.time_hours < h.received_hour
    GROUP BY c.customer_id, h.received_hour
), cutoffs AS (
    SELECT received_hour,
        PERCENTILE_DISC(0.75) WITHIN GROUP (ORDER BY purchase_count) AS frequent_cutoff,
        PERCENTILE_DISC(0.75) WITHIN GROUP (ORDER BY total_spend) AS higher_spend_cutoff
    FROM metrics
    WHERE full_history_observed AND purchase_count > 0
    GROUP BY received_hour
)
SELECT m.*, c.frequent_cutoff, c.higher_spend_cutoff,
    CASE WHEN NOT m.full_history_observed THEN 'Insufficient history'
        ELSE loyalty.classify_rfm(m.purchase_count, m.total_spend, m.recency_hours,
            c.frequent_cutoff, c.higher_spend_cutoff)
    END AS rfm_segment
FROM metrics AS m LEFT JOIN cutoffs AS c USING (received_hour);

CREATE OR REPLACE VIEW loyalty.offer_funnel_by_rfm AS
WITH channels AS (
    SELECT offer_id, STRING_AGG(channel, ', ' ORDER BY channel) AS channel_combination
    FROM loyalty.offer_channels GROUP BY offer_id
), counts AS (
    SELECT r.rfm_segment, d.offer_id, d.offer_type,
        COUNT(*) AS deliveries,
        COUNT(DISTINCT d.customer_id) AS customers,
        COUNT(*) FILTER (WHERE d.eligible_for_rates AND r.full_history_observed) AS eligible_deliveries,
        COUNT(DISTINCT d.customer_id) FILTER (WHERE d.eligible_for_rates AND r.full_history_observed) AS eligible_customers,
        COUNT(*) FILTER (WHERE d.eligible_for_rates AND r.full_history_observed AND d.was_viewed) AS viewed_deliveries,
        COUNT(*) FILTER (WHERE d.eligible_for_rates AND r.full_history_observed AND d.offer_type <> 'informational') AS eligible_reward_deliveries,
        COUNT(*) FILTER (WHERE d.eligible_for_rates AND r.full_history_observed AND d.offer_type <> 'informational' AND d.was_completed) AS completed_deliveries,
        COUNT(*) FILTER (WHERE d.eligible_for_rates AND r.full_history_observed AND d.completion_status = 'view_before_completion') AS completed_after_view
    FROM loyalty.offer_deliveries AS d
    JOIN loyalty.customer_rfm_before_offers AS r
        ON r.customer_id = d.customer_id AND r.received_hour = d.received_hour
    GROUP BY r.rfm_segment, d.offer_id, d.offer_type
)
SELECT c.*, ch.channel_combination,
    ROUND(100.0 * c.viewed_deliveries / NULLIF(c.eligible_deliveries, 0), 2) AS view_rate_pct,
    ROUND(100.0 * c.completed_deliveries / NULLIF(c.eligible_reward_deliveries, 0), 2) AS any_completion_rate_pct,
    ROUND(100.0 * c.completed_after_view / NULLIF(c.eligible_reward_deliveries, 0), 2) AS completion_after_view_rate_pct
FROM counts AS c LEFT JOIN channels AS ch USING (offer_id);
