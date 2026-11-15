-- Offer comparison, with explicit denominators and excluded delivery counts.
SELECT offer_id, offer_type, channel_combination,
    deliveries, full_window_deliveries, ambiguous_deliveries, eligible_deliveries,
    viewed_deliveries, completed_deliveries, completed_after_view,
    view_rate_pct, any_completion_rate_pct, completion_after_view_rate_pct
FROM loyalty.offer_funnel_by_offer
ORDER BY offer_type, offer_id;

-- All viewed/completed events are accounted for, including unmatched activity.
SELECT event_type, match_status, COUNT(*) AS event_count,
    COUNT(*) FILTER (WHERE expiry_boundary_count > 0) AS events_at_an_expiry
FROM loyalty.offer_event_matches
GROUP BY event_type, match_status
ORDER BY event_type, match_status;

-- Sensitivity audit: count events whose candidates change if expiry is excluded.
SELECT event_type,
    COUNT(*) FILTER (WHERE candidate_count <> expiry_exclusive_candidate_count) AS events_affected_by_expiry_rule
FROM loyalty.offer_event_matches
GROUP BY event_type
ORDER BY event_type;

-- Inspect completion timing for eligible reward-bearing deliveries.
SELECT completion_status, COUNT(*) AS deliveries
FROM loyalty.offer_deliveries
WHERE eligible_for_rates AND offer_type <> 'informational'
GROUP BY completion_status
ORDER BY completion_status;

-- Channel combinations are offer attributes. Keep offer type in the grouping.
SELECT channel_combination, offer_type, SUM(eligible_deliveries) AS eligible_deliveries,
    ROUND(100.0 * SUM(viewed_deliveries) / NULLIF(SUM(eligible_deliveries), 0), 2) AS view_rate_pct,
    ROUND(100.0 * SUM(completed_after_view) / NULLIF(SUM(eligible_reward_deliveries), 0), 2) AS completion_after_view_rate_pct
FROM loyalty.offer_funnel_by_offer
GROUP BY channel_combination, offer_type
ORDER BY channel_combination, offer_type;

-- A first demographic comparison; RFM segments will follow in the next stage.
WITH segments AS (
    SELECT d.*,
        CASE
            WHEN c.age IS NULL THEN 'Unknown'
            WHEN c.age < 30 THEN 'Under 30'
            WHEN c.age < 45 THEN '30-44'
            WHEN c.age < 60 THEN '45-59'
            ELSE '60+'
        END AS age_group
    FROM loyalty.offer_deliveries AS d
    JOIN loyalty.customers AS c USING (customer_id)
    WHERE d.eligible_for_rates
)
SELECT age_group, offer_type, COUNT(*) AS eligible_deliveries,
    ROUND(100.0 * COUNT(*) FILTER (WHERE was_viewed) / COUNT(*), 2) AS view_rate_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE completion_status = 'view_before_completion')
        / NULLIF(COUNT(*) FILTER (WHERE offer_type <> 'informational'), 0), 2) AS completion_after_view_rate_pct
FROM segments
GROUP BY age_group, offer_type
ORDER BY age_group, offer_type;
