# Starbucks Loyalty Analytics

An exploration of the simulated Starbucks Rewards dataset used in the Udacity data science capstone, with a planned PostgreSQL and Metabase analysis of offer engagement, purchasing, retention, and customer segments.

PostgreSQL now stores the original JSON records and normalized customers, offers, channels, and events. The `loyalty.event_details` view connects events to customer profiles and offer definitions through their IDs.

## Start with the exploration notebook

Open [01_starbucks_data_exploration.ipynb](01_starbucks_data_exploration.ipynb) to inspect the data structure, missing demographics, event payloads, repeated records, purchases, and one customer's activity timeline. Saved outputs are included.

The local dataset contains 17,000 customers, 10 offer definitions, and 306,534 activity records.

To rerun the notebook, use a Python notebook environment with pandas installed and place these JSON Lines files beside the notebook:

- `profile.json` — customer profiles.
- `portfolio.json` — offer definitions.
- `transcript.json` — customer activities and purchases.

The raw dataset and archive are excluded from version control. Obtain the Starbucks Rewards capstone files separately and retain their original names.

## Run PostgreSQL and import the data

Use Docker Desktop with Linux containers and Python 3.10 or newer. Run these commands from the repository root in PowerShell.

On a fresh checkout, create your local configuration:

```powershell
Copy-Item .env.example .env
```

Set `POSTGRES_PASSWORD` in `.env` to a local password. Keep `.env` local. It is excluded from Git. The importer reads simple `KEY=value` settings from this file; environment variables take precedence. If port 5432 is occupied, set `POSTGRES_PORT` to an available port.

```powershell
python -m pip install -r requirements.txt
docker compose up -d --wait
python scripts/import_data.py
```

The importer creates the schema, preserves each source record, normalizes its fields, and validates row counts and monetary totals before committing. It uses one transaction and an import lock. Rerunning with identical files validates the existing import and leaves the data unchanged. A different file set requires its own database, keeping the current dataset intact.

Blank lines are skipped. `raw_records.source_line` retains physical file line numbers, while the notebook's `source_row` numbers parsed event records.

To read the example joins and run reconciliation checks:

```powershell
Get-Content sql/004_explore.sql | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
Get-Content sql/003_validation.sql | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
```

Stop the container with `docker compose stop`. The named Docker volume retains the database. PostgreSQL is available on localhost at the port configured in `.env`.

## Database structure

All project tables and views are in the `loyalty` schema.

| Table or view | One row represents |
|---|---|
| `ingestion_batches` | An import, with file hashes and source counts |
| `raw_records` | One JSON line, identified by file and line number |
| `customers` | One customer, keyed by `customer_id` |
| `offers` | One offer definition, keyed by `offer_id` |
| `offer_channels` | One offer and one of its distribution channels |
| `events` | One recorded activity, with customer and optional offer references |
| `event_details` | One event joined to its customer and offer attributes |
| `transactions` | One purchase event |

`profile.id` and `transcript.person` become `customer_id`. `portfolio.id` and either offer-ID payload spelling become `offer_id`. Source age 118 becomes an unknown cleaned age while `age_raw` preserves the original value. Missing demographics remain SQL `NULL`. Amounts use `NUMERIC`, offer duration uses days, and event time uses hours from the observation start.

Transactions carry a customer and purchase amount. Their offer ID is `NULL`, so the joined view uses a left join to offers. Source event repetitions are retained and individually traceable. The channel bridge is queried separately or aggregated to avoid multiplying events.

The SQL files define the schema (`001`), transformations (`002`), reconciliation checks (`003`), and example joins (`004`). The Python importer runs the first three automatically.

## Planned work

1. Define delivery-level offer funnels and investigate completions without a prior view.
2. Analyze purchase retention and RFM segments.
3. Compare campaigns with hypothesis tests.
4. Build a Metabase dashboard using Docker and write a one-page growth memo.

Future ML applications include personalized offer targeting and repeat-purchase prediction, following completion of the analytics work.

## Data acknowledgement

The source is the simulated Starbucks Rewards dataset associated with the Udacity capstone. Analysis and interpretations in this project are independent.
