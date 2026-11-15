# Starbucks Loyalty Analytics

An exploration of the simulated Starbucks Rewards dataset used in the Udacity data science capstone, with a planned PostgreSQL and Metabase analysis of offer engagement, purchasing, retention, and customer segments.

## Start with the exploration notebook

Open [01_starbucks_data_exploration.ipynb](01_starbucks_data_exploration.ipynb) to inspect the data structure, missing demographics, event payloads, repeated records, purchases, and one customer's activity timeline. Saved outputs are included.

The local dataset contains 17,000 customers, 10 offer definitions, and 306,534 activity records.

To rerun the notebook, use a Python notebook environment with pandas installed and place these JSON Lines files beside the notebook:

- `profile.json` — customer profiles.
- `portfolio.json` — offer definitions.
- `transcript.json` — customer activities and purchases.

The raw dataset and archive are excluded from version control. Obtain the Starbucks Rewards capstone files separately and retain their original names.

## Planned work

1. Model and load the data in PostgreSQL.
2. Define delivery-level offer funnels and investigate completions without a prior view.
3. Analyze purchase retention and RFM segments.
4. Compare campaigns with hypothesis tests.
5. Build a Metabase dashboard using Docker and write a one-page growth memo.

Future ML applications include personalized offer targeting and repeat-purchase prediction, following completion of the analytics work.

## Data acknowledgement

The source is the simulated Starbucks Rewards dataset associated with the Udacity capstone. Analysis and interpretations in this project are independent.
