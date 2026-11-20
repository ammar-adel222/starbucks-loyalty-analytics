WITH checks AS (
    SELECT 'campaign input delivery coverage' AS check_name,
        (SELECT COUNT(*) FROM loyalty.campaign_comparison_inputs) AS actual,
        (SELECT COUNT(*) FROM loyalty.offer_deliveries
         WHERE eligible_for_rates AND received_hour >= 168 AND offer_type <> 'informational') AS expected
    UNION ALL
    SELECT 'campaign input unique deliveries',
        (SELECT COUNT(DISTINCT delivery_id) FROM loyalty.campaign_comparison_inputs),
        (SELECT COUNT(*) FROM loyalty.campaign_comparison_inputs)
    UNION ALL
    SELECT 'campaign input full-history segments',
        (SELECT COUNT(*) FROM loyalty.campaign_comparison_inputs
         WHERE rfm_segment IS NULL OR rfm_segment = 'Insufficient history'), 0
    UNION ALL
    SELECT 'campaign outcomes are binary',
        (SELECT COUNT(*) FROM loyalty.campaign_comparison_inputs
         WHERE completed_after_view IS NULL OR completed_after_view NOT IN (0, 1)), 0
)
SELECT check_name, actual, expected, actual = expected AS passed FROM checks ORDER BY check_name;
