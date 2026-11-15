-- One receipt is one delivery. Event IDs locate source records, not within-hour order.
CREATE OR REPLACE VIEW loyalty.offer_receipts AS
WITH receipts AS (
    SELECT
        e.event_id AS delivery_id, e.customer_id, e.offer_id,
        e.time_hours AS received_hour, o.offer_type,
        o.difficulty, o.reward, o.duration_days,
        e.time_hours + o.duration_days * 24 AS expiry_hour,
        COUNT(*) OVER (
            PARTITION BY e.customer_id, e.offer_id, e.time_hours
        ) AS same_hour_receipt_count,
        LEAD(e.time_hours) OVER (
            PARTITION BY e.customer_id, e.offer_id ORDER BY e.time_hours, e.event_id
        ) AS next_received_hour
    FROM loyalty.events AS e
    JOIN loyalty.offers AS o USING (offer_id)
    WHERE e.event_type = 'offer received'
)
SELECT r.*, b.last_observed_hour,
    r.expiry_hour <= b.last_observed_hour AS full_window_observed,
    COALESCE(r.next_received_hour <= r.expiry_hour, FALSE) AS overlaps_next_delivery
FROM receipts AS r
CROSS JOIN (SELECT MAX(time_hours) AS last_observed_hour FROM loyalty.events) AS b;

-- Use an inclusive [receipt, expiry] window. Keep the boundary visible for auditing.
CREATE OR REPLACE VIEW loyalty.offer_event_candidates AS
SELECT
    e.event_id, e.event_type, e.time_hours, r.delivery_id,
    e.time_hours = r.expiry_hour AS at_expiry_boundary
FROM loyalty.events AS e
JOIN loyalty.offer_receipts AS r
    ON r.customer_id = e.customer_id
    AND r.offer_id = e.offer_id
    AND e.time_hours >= r.received_hour
    AND e.time_hours <= r.expiry_hour
WHERE e.event_type IN ('offer viewed', 'offer completed');

CREATE OR REPLACE VIEW loyalty.offer_event_matches AS
WITH candidates AS (
    SELECT event_id,
        COUNT(*) AS candidate_count,
        COUNT(*) FILTER (WHERE at_expiry_boundary) AS expiry_boundary_count,
        COUNT(*) FILTER (WHERE NOT at_expiry_boundary) AS expiry_exclusive_candidate_count,
        CASE WHEN COUNT(*) = 1
            THEN MAX(delivery_id)
        END AS delivery_id
    FROM loyalty.offer_event_candidates
    GROUP BY event_id
)
SELECT
    e.event_id, e.customer_id, e.offer_id, e.event_type, e.time_hours,
    c.delivery_id,
    COALESCE(c.candidate_count, 0) AS candidate_count,
    COALESCE(c.expiry_boundary_count, 0) AS expiry_boundary_count,
    CASE
        WHEN c.candidate_count = 1 THEN 'matched'
        WHEN c.candidate_count > 1 THEN 'ambiguous'
        ELSE 'unmatched'
    END AS match_status,
    COALESCE(c.expiry_exclusive_candidate_count, 0) AS expiry_exclusive_candidate_count
FROM loyalty.events AS e
LEFT JOIN candidates AS c USING (event_id)
WHERE e.event_type IN ('offer viewed', 'offer completed');

CREATE OR REPLACE VIEW loyalty.offer_deliveries AS
WITH matched_activity AS (
    SELECT delivery_id,
        MIN(time_hours) FILTER (WHERE event_type = 'offer viewed') AS first_view_hour,
        MIN(time_hours) FILTER (WHERE event_type = 'offer completed') AS first_completion_hour,
        COUNT(*) FILTER (WHERE event_type = 'offer viewed') AS view_event_count,
        COUNT(*) FILTER (WHERE event_type = 'offer completed') AS completion_event_count
    FROM loyalty.offer_event_matches
    WHERE match_status = 'matched'
    GROUP BY delivery_id
), ambiguous_activity AS (
    -- Flag every possible delivery for an ambiguous event, preserving its candidates.
    SELECT c.delivery_id, COUNT(*) AS ambiguous_event_count
    FROM loyalty.offer_event_candidates AS c
    JOIN loyalty.offer_event_matches AS m USING (event_id)
    WHERE m.match_status = 'ambiguous'
    GROUP BY c.delivery_id
), deliveries AS (
    SELECT r.*, a.first_view_hour, a.first_completion_hour,
        COALESCE(a.view_event_count, 0) AS view_event_count,
        COALESCE(a.completion_event_count, 0) AS completion_event_count,
        COALESCE(b.ambiguous_event_count, 0) AS ambiguous_event_count
    FROM loyalty.offer_receipts AS r
    LEFT JOIN matched_activity AS a USING (delivery_id)
    LEFT JOIN ambiguous_activity AS b USING (delivery_id)
)
SELECT d.*,
    full_window_observed AND ambiguous_event_count = 0
        AND same_hour_receipt_count = 1 AS eligible_for_rates,
    first_view_hour IS NOT NULL AS was_viewed,
    first_completion_hour IS NOT NULL AS was_completed,
    CASE
        WHEN offer_type = 'informational' THEN 'not_applicable'
        WHEN first_completion_hour IS NULL THEN 'not_completed'
        WHEN first_view_hour < first_completion_hour THEN 'view_before_completion'
        WHEN first_view_hour = first_completion_hour THEN 'view_same_hour_as_completion'
        WHEN first_view_hour > first_completion_hour THEN 'view_after_completion'
        ELSE 'no_recorded_view'
    END AS completion_status
FROM deliveries AS d;

CREATE OR REPLACE VIEW loyalty.offer_funnel_by_offer AS
WITH counts AS (
    SELECT offer_id, offer_type,
        COUNT(*) AS deliveries,
        COUNT(*) FILTER (WHERE full_window_observed) AS full_window_deliveries,
        COUNT(*) FILTER (WHERE ambiguous_event_count > 0 OR same_hour_receipt_count > 1) AS ambiguous_deliveries,
        COUNT(*) FILTER (WHERE eligible_for_rates) AS eligible_deliveries,
        COUNT(*) FILTER (WHERE eligible_for_rates AND was_viewed) AS viewed_deliveries,
        COUNT(*) FILTER (WHERE eligible_for_rates AND offer_type <> 'informational') AS eligible_reward_deliveries,
        COUNT(*) FILTER (WHERE eligible_for_rates AND offer_type <> 'informational' AND was_completed) AS completed_deliveries,
        COUNT(*) FILTER (WHERE eligible_for_rates AND completion_status = 'view_before_completion') AS completed_after_view,
        COUNT(*) FILTER (WHERE eligible_for_rates AND completion_status = 'view_same_hour_as_completion') AS completed_same_hour_as_view,
        COUNT(*) FILTER (WHERE eligible_for_rates AND completion_status = 'view_after_completion') AS completed_before_view,
        COUNT(*) FILTER (WHERE eligible_for_rates AND completion_status = 'no_recorded_view') AS completed_without_view
    FROM loyalty.offer_deliveries
    GROUP BY offer_id, offer_type
), channels AS (
    SELECT offer_id, STRING_AGG(channel, ', ' ORDER BY channel) AS channel_combination
    FROM loyalty.offer_channels
    GROUP BY offer_id
)
SELECT c.*, o.difficulty, o.reward, o.duration_days, ch.channel_combination,
    ROUND(100.0 * viewed_deliveries / NULLIF(eligible_deliveries, 0), 2) AS view_rate_pct,
    ROUND(100.0 * completed_deliveries / NULLIF(eligible_reward_deliveries, 0), 2) AS any_completion_rate_pct,
    ROUND(100.0 * completed_after_view / NULLIF(eligible_reward_deliveries, 0), 2) AS completion_after_view_rate_pct
FROM counts AS c
JOIN loyalty.offers AS o USING (offer_id)
LEFT JOIN channels AS ch USING (offer_id);
