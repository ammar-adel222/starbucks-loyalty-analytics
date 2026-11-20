-- One eligible reward-bearing delivery, with features observed before receipt.
CREATE OR REPLACE VIEW loyalty.campaign_comparison_inputs AS
SELECT d.delivery_id, d.customer_id, d.offer_id, d.offer_type,
    d.difficulty, d.reward, d.duration_days, d.received_hour,
    r.rfm_segment,
    (d.completion_status = 'view_before_completion')::INTEGER AS completed_after_view
FROM loyalty.offer_deliveries AS d
JOIN loyalty.customer_rfm_before_offers AS r
    ON r.customer_id = d.customer_id AND r.received_hour = d.received_hour
WHERE d.eligible_for_rates AND r.full_history_observed
    AND d.offer_type <> 'informational';
