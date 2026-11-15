-- Connect a customer's events to their profile and the offer definition.
SELECT
    event_id, customer_id, age, gender, income,
    event_type, time_hours, offer_id, offer_type,
    offer_required_spend, offer_reward, transaction_amount
FROM loyalty.event_details
ORDER BY time_hours, event_id
LIMIT 25;

-- Count each event once. Purchase rows have a NULL offer type.
SELECT event_type, offer_type, COUNT(*) AS event_count
FROM loyalty.event_details
GROUP BY event_type, offer_type
ORDER BY event_type, offer_type;

-- Preserve one row per offer when showing its multiple channels.
SELECT o.offer_id, o.offer_type, o.difficulty, o.reward, o.duration_days,
    STRING_AGG(c.channel, ', ' ORDER BY c.channel) AS channels
FROM loyalty.offers AS o
LEFT JOIN loyalty.offer_channels AS c ON c.offer_id = o.offer_id
GROUP BY o.offer_id
ORDER BY o.offer_type, o.offer_id;
