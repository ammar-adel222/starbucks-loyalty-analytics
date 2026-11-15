CREATE SCHEMA IF NOT EXISTS loyalty;

CREATE TABLE IF NOT EXISTS loyalty.ingestion_batches (
    batch_id UUID PRIMARY KEY,
    manifest JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loyalty.raw_records (
    raw_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES loyalty.ingestion_batches,
    source_file TEXT NOT NULL CHECK (source_file IN ('profile.json', 'portfolio.json', 'transcript.json')),
    source_line INTEGER NOT NULL CHECK (source_line > 0),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (batch_id, source_file, source_line)
);

CREATE TABLE IF NOT EXISTS loyalty.customers (
    customer_id TEXT PRIMARY KEY CHECK (customer_id <> ''),
    age_raw INTEGER,
    age INTEGER CHECK (age >= 0),
    gender TEXT,
    income NUMERIC,
    member_since DATE NOT NULL,
    source_record_id BIGINT NOT NULL UNIQUE REFERENCES loyalty.raw_records (raw_record_id)
);

CREATE TABLE IF NOT EXISTS loyalty.offers (
    offer_id TEXT PRIMARY KEY CHECK (offer_id <> ''),
    offer_type TEXT NOT NULL CHECK (offer_type IN ('bogo', 'discount', 'informational')),
    difficulty NUMERIC NOT NULL CHECK (difficulty >= 0),
    reward NUMERIC NOT NULL CHECK (reward >= 0),
    duration_days NUMERIC NOT NULL CHECK (duration_days > 0),
    source_record_id BIGINT NOT NULL UNIQUE REFERENCES loyalty.raw_records (raw_record_id)
);

CREATE TABLE IF NOT EXISTS loyalty.offer_channels (
    offer_id TEXT NOT NULL REFERENCES loyalty.offers,
    channel TEXT NOT NULL CHECK (channel <> ''),
    PRIMARY KEY (offer_id, channel)
);

CREATE TABLE IF NOT EXISTS loyalty.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES loyalty.customers,
    event_type TEXT NOT NULL CHECK (event_type IN ('offer received', 'offer viewed', 'offer completed', 'transaction')),
    time_hours INTEGER NOT NULL CHECK (time_hours >= 0),
    offer_id TEXT REFERENCES loyalty.offers,
    transaction_amount NUMERIC,
    completion_reward NUMERIC,
    source_record_id BIGINT NOT NULL UNIQUE REFERENCES loyalty.raw_records (raw_record_id),
    CHECK (
        (event_type = 'transaction' AND offer_id IS NULL
            AND transaction_amount IS NOT NULL AND completion_reward IS NULL)
        OR (event_type IN ('offer received', 'offer viewed') AND offer_id IS NOT NULL
            AND transaction_amount IS NULL AND completion_reward IS NULL)
        OR (event_type = 'offer completed' AND offer_id IS NOT NULL
            AND transaction_amount IS NULL AND completion_reward IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS events_customer_time_idx ON loyalty.events (customer_id, time_hours);
CREATE INDEX IF NOT EXISTS events_offer_customer_time_idx ON loyalty.events (offer_id, customer_id, time_hours);

-- A left join preserves purchases, which have no offer ID.
CREATE OR REPLACE VIEW loyalty.event_details AS
SELECT
    e.event_id,
    e.customer_id,
    c.age,
    c.gender,
    c.income,
    c.member_since,
    e.event_type,
    e.time_hours,
    e.offer_id,
    o.offer_type,
    o.difficulty AS offer_required_spend,
    o.reward AS offer_reward,
    o.duration_days,
    e.transaction_amount,
    e.completion_reward,
    e.source_record_id
FROM loyalty.events AS e
JOIN loyalty.customers AS c ON c.customer_id = e.customer_id
LEFT JOIN loyalty.offers AS o ON o.offer_id = e.offer_id;

CREATE OR REPLACE VIEW loyalty.transactions AS
SELECT event_id, customer_id, time_hours, transaction_amount, source_record_id
FROM loyalty.events
WHERE event_type = 'transaction';
