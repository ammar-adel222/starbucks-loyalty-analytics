WITH checks AS (
    SELECT 'one row per receipt' AS check_name,
        (SELECT COUNT(*) FROM loyalty.offer_deliveries) AS actual,
        (SELECT COUNT(*) FROM loyalty.events WHERE event_type = 'offer received') AS expected
    UNION ALL
    SELECT 'all interaction events audited',
        (SELECT COUNT(*) FROM loyalty.offer_event_matches),
        (SELECT COUNT(*) FROM loyalty.events WHERE event_type IN ('offer viewed', 'offer completed'))
    UNION ALL
    SELECT 'unique delivery identifiers',
        (SELECT COUNT(DISTINCT delivery_id) FROM loyalty.offer_deliveries),
        (SELECT COUNT(*) FROM loyalty.offer_deliveries)
    UNION ALL
    SELECT 'unique interaction audit identifiers',
        (SELECT COUNT(DISTINCT event_id) FROM loyalty.offer_event_matches),
        (SELECT COUNT(*) FROM loyalty.offer_event_matches)
    UNION ALL
    SELECT 'matched view reconciliation',
        (SELECT COALESCE(SUM(view_event_count), 0)::BIGINT FROM loyalty.offer_deliveries),
        (SELECT COUNT(*) FROM loyalty.offer_event_matches WHERE match_status = 'matched' AND event_type = 'offer viewed')
    UNION ALL
    SELECT 'matched completion reconciliation',
        (SELECT COALESCE(SUM(completion_event_count), 0)::BIGINT FROM loyalty.offer_deliveries),
        (SELECT COUNT(*) FROM loyalty.offer_event_matches WHERE match_status = 'matched' AND event_type = 'offer completed')
    UNION ALL
    SELECT 'ambiguous events unassigned',
        (SELECT COUNT(*) FROM loyalty.offer_event_matches WHERE match_status <> 'matched' AND delivery_id IS NOT NULL), 0
    UNION ALL
    SELECT 'eligible deliveries have full unambiguous windows',
        (SELECT COUNT(*) FROM loyalty.offer_deliveries WHERE eligible_for_rates
            AND (NOT full_window_observed OR ambiguous_event_count <> 0 OR same_hour_receipt_count <> 1)), 0
    UNION ALL
    SELECT 'completion categories reconcile',
        (SELECT COALESCE(SUM(completed_after_view + completed_same_hour_as_view + completed_before_view + completed_without_view), 0)::BIGINT FROM loyalty.offer_funnel_by_offer),
        (SELECT COALESCE(SUM(completed_deliveries), 0)::BIGINT FROM loyalty.offer_funnel_by_offer)
    UNION ALL
    SELECT 'offer totals reconcile',
        (SELECT COALESCE(SUM(deliveries), 0)::BIGINT FROM loyalty.offer_funnel_by_offer),
        (SELECT COUNT(*) FROM loyalty.offer_deliveries)
    UNION ALL
    SELECT 'informational completion rates are null',
        (SELECT COUNT(*) FROM loyalty.offer_funnel_by_offer WHERE offer_type = 'informational'
            AND (any_completion_rate_pct IS NOT NULL OR completion_after_view_rate_pct IS NOT NULL)), 0
)
SELECT check_name, actual, expected, actual = expected AS passed
FROM checks
ORDER BY check_name;
