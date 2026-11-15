INSERT INTO loyalty.customers
    (customer_id, age_raw, age, gender, income, member_since, source_record_id)
SELECT
    payload ->> 'id',
    (payload ->> 'age')::INTEGER,
    NULLIF((payload ->> 'age')::INTEGER, 118),
    payload ->> 'gender',
    (payload ->> 'income')::NUMERIC,
    (payload ->> 'became_member_on')::DATE,
    raw_record_id
FROM loyalty.raw_records
WHERE source_file = 'profile.json';

INSERT INTO loyalty.offers
    (offer_id, offer_type, difficulty, reward, duration_days, source_record_id)
SELECT
    payload ->> 'id',
    payload ->> 'offer_type',
    (payload ->> 'difficulty')::NUMERIC,
    (payload ->> 'reward')::NUMERIC,
    (payload ->> 'duration')::NUMERIC,
    raw_record_id
FROM loyalty.raw_records
WHERE source_file = 'portfolio.json';

INSERT INTO loyalty.offer_channels (offer_id, channel)
SELECT r.payload ->> 'id', channels.channel
FROM loyalty.raw_records AS r
CROSS JOIN LATERAL jsonb_array_elements_text(r.payload -> 'channels') AS channels(channel)
WHERE r.source_file = 'portfolio.json';

INSERT INTO loyalty.events
    (customer_id, event_type, time_hours, offer_id, transaction_amount, completion_reward, source_record_id)
SELECT
    payload ->> 'person',
    payload ->> 'event',
    (payload ->> 'time')::INTEGER,
    COALESCE(payload #>> '{value,offer_id}', payload #>> '{value,offer id}'),
    (payload #>> '{value,amount}')::NUMERIC,
    (payload #>> '{value,reward}')::NUMERIC,
    raw_record_id
FROM loyalty.raw_records
WHERE source_file = 'transcript.json'
ORDER BY source_line;
