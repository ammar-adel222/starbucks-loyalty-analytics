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
| `offer_receipts` | One receipt with its expiry and observation window |
| `offer_event_candidates` | One possible link between a view/completion and a delivery |
| `offer_event_matches` | One view/completion with its matching status |
| `offer_deliveries` | One delivery with its matched activity and eligibility flags |
| `offer_funnel_by_offer` | One offer with delivery counts, denominators, and rates |

`profile.id` and `transcript.person` become `customer_id`. `portfolio.id` and either offer-ID payload spelling become `offer_id`. Source age 118 becomes an unknown cleaned age while `age_raw` preserves the original value. Missing demographics remain SQL `NULL`. Amounts use `NUMERIC`, offer duration uses days, and event time uses hours from the observation start.

Transactions carry a customer and purchase amount. Their offer ID is `NULL`, so the joined view uses a left join to offers. Source event repetitions are retained and individually traceable. The channel bridge is queried separately or aggregated to avoid multiplying events.

The SQL files define the schema (`001`), transformations (`002`), import checks (`003`), example joins (`004`), funnel views (`005`), funnel queries (`006`), and funnel checks (`007`). The importer applies the schema and funnel views, loads new data when needed, and runs both sets of checks. Rerun the importer to add the funnel to an existing import.

## Delivery-level offer funnel

Each receipt is a separate delivery, including repeated receipts of the same offer by a customer. Views and completions become candidates when their customer and offer match and their recorded hour falls between receipt and expiry, including both endpoints.

Expiry is inclusive because the transcript contains completion events exactly at expiry. The audit keeps those events visible and reports how many candidate counts would change with an exclusive expiry rule. It identifies 557 completion events and 563 view events affected by this choice.

An event is assigned only when it has exactly one candidate delivery. Events with multiple candidates remain ambiguous, and every affected delivery is flagged. Source event order does not establish within-hour chronology.

For the main rates, a delivery must have an expiry at or before the last observed event hour (714), no ambiguous candidate events, and a unique receipt timestamp for its customer and offer. This is a conservative follow-up boundary based on the available log. Excluding ambiguous deliveries can change the composition of the comparison population; counts remain visible beside the rates.

- View rate is viewed eligible deliveries divided by all eligible deliveries.
- Any-completion rate is completed eligible reward-bearing deliveries divided by eligible reward-bearing deliveries.
- Completion-after-view rate uses the same denominator and requires the first matched view to precede the first matched completion strictly.
- Same-hour views/completions, views after first completion, and completions with no recorded view have separate categories.
- Informational offers have view rates. Their completion rates are SQL `NULL`.

Repeated completion events contribute to event counts and convert a delivery once. The timing categories use the first uniquely matched completion. Activity summaries on excluded deliveries are partial when events are ambiguous, so inspect their audit rows before interpreting them. Channel comparisons describe the combination attached to an offer.

Current delivery coverage is 76,277 receipts, 66,041 fully observable windows, and 61,839 eligible deliveries. There are 5,219 deliveries affected by ambiguous activity, including some with incomplete follow-up. These exclusion counts overlap.

| Offer type | Eligible deliveries | View rate | Any completion | Completion after view |
|---|---:|---:|---:|---:|
| BOGO | 26,089 | 83.44% | 50.67% | 31.58% |
| Discount | 20,688 | 68.82% | 58.58% | 37.41% |
| Informational | 15,062 | 65.00% | — | — |

Among eligible reward-bearing deliveries, 15,979 had a view before first completion, 2,115 had a view in the same hour, 2,901 had a later first view, and 4,343 completed with no recorded view. Another 21,439 had no matched completion. These are observed campaign outcomes; a campaign experiment would be needed to estimate incremental purchasing.

```powershell
python scripts/import_data.py
Get-Content sql/006_funnel_queries.sql | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
python -m unittest discover -s tests -v
```

The eight regression checks create and remove a disposable database on the configured PostgreSQL server. They cover expiry boundaries, overlapping receipts, same-hour events, missing and later views, repeated completions, incomplete follow-up, and informational offers. The Docker configuration supplies the database-creation permission they require.

## Planned work

1. Analyze purchase retention and RFM segments.
2. Compare campaigns with hypothesis tests.
3. Build a Metabase dashboard using Docker and write a one-page growth memo.

Future ML applications include personalized offer targeting and repeat-purchase prediction, following completion of the analytics work.

## Data acknowledgement

The source is the simulated Starbucks Rewards dataset associated with the Udacity capstone. Analysis and interpretations in this project are independent.
