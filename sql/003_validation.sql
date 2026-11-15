-- Every row should have actual = expected. Also run automatically by the importer.
WITH checks AS (
    SELECT 'customers' AS check_name,
        (SELECT COUNT(*) FROM loyalty.customers)::NUMERIC AS actual,
        (SELECT COUNT(*) FROM loyalty.raw_records WHERE source_file = 'profile.json')::NUMERIC AS expected
    UNION ALL
    SELECT 'offers',
        (SELECT COUNT(*) FROM loyalty.offers),
        (SELECT COUNT(*) FROM loyalty.raw_records WHERE source_file = 'portfolio.json')
    UNION ALL
    SELECT 'events',
        (SELECT COUNT(*) FROM loyalty.events),
        (SELECT COUNT(*) FROM loyalty.raw_records WHERE source_file = 'transcript.json')
    UNION ALL
    SELECT 'raw customer records',
        (SELECT COUNT(*) FROM loyalty.raw_records WHERE source_file = 'profile.json'),
        (SELECT COALESCE(SUM((manifest #>> '{profile.json,rows}')::NUMERIC), 0) FROM loyalty.ingestion_batches)
    UNION ALL
    SELECT 'raw offer records',
        (SELECT COUNT(*) FROM loyalty.raw_records WHERE source_file = 'portfolio.json'),
        (SELECT COALESCE(SUM((manifest #>> '{portfolio.json,rows}')::NUMERIC), 0) FROM loyalty.ingestion_batches)
    UNION ALL
    SELECT 'raw event records',
        (SELECT COUNT(*) FROM loyalty.raw_records WHERE source_file = 'transcript.json'),
        (SELECT COALESCE(SUM((manifest #>> '{transcript.json,rows}')::NUMERIC), 0) FROM loyalty.ingestion_batches)
    UNION ALL
    SELECT 'joined event rows',
        (SELECT COUNT(*) FROM loyalty.event_details),
        (SELECT COUNT(*) FROM loyalty.events)
    UNION ALL
    SELECT 'purchase count',
        (SELECT COUNT(*) FROM loyalty.transactions),
        (SELECT COUNT(*) FROM loyalty.raw_records
         WHERE source_file = 'transcript.json' AND payload ->> 'event' = 'transaction')
    UNION ALL
    SELECT 'purchase amount total',
        (SELECT COALESCE(SUM(transaction_amount), 0) FROM loyalty.transactions),
        (SELECT COALESCE(SUM((payload #>> '{value,amount}')::NUMERIC), 0)
         FROM loyalty.raw_records
         WHERE source_file = 'transcript.json' AND payload ->> 'event' = 'transaction')
    UNION ALL
    SELECT 'completion reward total',
        (SELECT COALESCE(SUM(completion_reward), 0) FROM loyalty.events),
        (SELECT COALESCE(SUM((payload #>> '{value,reward}')::NUMERIC), 0)
         FROM loyalty.raw_records
         WHERE source_file = 'transcript.json' AND payload ->> 'event' = 'offer completed')
    UNION ALL
    SELECT 'unknown age treatment',
        (SELECT COUNT(*) FROM loyalty.customers WHERE age_raw = 118 AND age IS NULL),
        (SELECT COUNT(*) FROM loyalty.raw_records
         WHERE source_file = 'profile.json' AND (payload ->> 'age')::INTEGER = 118)
    UNION ALL
    SELECT 'offer channels',
        (SELECT COUNT(*) FROM loyalty.offer_channels),
        (SELECT COALESCE(SUM(jsonb_array_length(payload -> 'channels')), 0)
         FROM loyalty.raw_records WHERE source_file = 'portfolio.json')
)
SELECT check_name, actual, expected, actual = expected AS passed
FROM checks
ORDER BY check_name;
