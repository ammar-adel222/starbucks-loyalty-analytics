# Customer retention and RFM findings

The recorded period contains 16,578 purchasing customers and 422 customers with no purchase. Total purchase amount is $1,775,451.97 across 138,953 transaction records. These findings describe the simulated observation period ending at hour 714.

## Purchase retention

Customers enter a cohort in the week of their first observed purchase. Weeks start at hour zero and last 168 hours. A return means at least one purchase during the target calendar week. A customer who misses one week can return in a later week, so this retention measure can rise.

| First-purchase cohort | Customers | Cohort week | Following week | Two weeks later | Three weeks later |
|---|---:|---:|---:|---:|---:|
| Week 0 | 11,256 | 100% | 81.73% | 87.99% | 88.32% |
| Week 1 | 3,528 | 100% | 81.24% | 84.98% | — |
| Week 2 | 1,274 | 100% | 78.02% | — | — |
| Week 3 | 457 | 100% | — | — | — |
| Week 4 | 63 | — | — | — | — |

The following-week return rate across the three observable cohorts is 81.33% (13,060 of 16,058 customers). The dash indicates incomplete observation. The 63 week-4 customers remain in the cohort inventory and have no retention cell because even their first calendar week is incomplete. The 422 customers without purchases have no purchase cohort.

This is first-observed-purchase retention. Calendar cohorts provide unequal elapsed time between first purchase and the next week, depending on the day of entry. Membership dates are available for a separate membership-cohort analysis. A longer history would support stronger conclusions about sustained retention.

## RFM at the end of observation

Recency is hours since last purchase, frequency is transaction count, and monetary value is total recorded purchase amount. The snapshot uses all observed purchases through hour 714. Customers with no purchase have zero count and spend, and unknown recency.

The working recency cutoff is 72 hours. Frequent customers meet or exceed the purchasing population's 75th percentile of count; higher-spend customers meet or exceed its 75th percentile of amount. The snapshot cutoffs are 11 purchases and $150.94. Equal values receive the same classification, so group sizes can exceed an exact quartile. These thresholds are starting business rules to evaluate.

| Snapshot segment | Customers | Purchase amount | Share of amount |
|---|---:|---:|---:|
| Frequent, higher-spend recent | 1,656 | $452,421.41 | 25.48% |
| Previously active, less recent | 1,873 | $374,928.41 | 21.12% |
| Higher-spend recent | 1,188 | $291,802.04 | 16.44% |
| Occasional, less recent | 5,232 | $261,160.33 | 14.71% |
| Other recent | 4,598 | $260,053.55 | 14.65% |
| Frequent recent | 2,031 | $135,086.23 | 7.61% |
| No purchases in window | 422 | $0.00 | 0.00% |

Recent means the last purchase was within 72 hours, including the endpoint. Among recent purchasers, the categories distinguish high count and high amount, high count alone, high amount alone, and the remaining purchasers. Among less recent purchasers, meeting either upper-quartile cutoff creates the previously-active group. The remaining less-recent purchasers form the occasional group. Recorded purchase amount provides a measure of activity within this period; lifetime value and profit require additional data.

## Offer response using information available before receipt

Campaign segments use only purchases in the interval `[received hour - 168, received hour)`. Transactions recorded in the receipt hour are excluded because their within-hour order is unknown. A delivery before hour 168 gets an insufficient-history label. Even a customer with no purchase needs that observation time before entering the no-purchases group.

Seven-day frequency and amount cutoffs are recalculated across all purchasing customers at each delivery hour. The frequency cutoff is 3 purchases at hours 168, 336, 408, and 504, and 4 at hour 576. The corresponding amount cutoffs are $37.07, $37.44, $37.13, $43.46, and $45.64. The recency cutoff remains 72 hours.

This creates 102,000 customer-hour feature rows. Attaching those features to deliveries preserves all 76,277 delivery rows. After the existing follow-up and ambiguity rules and the seven-day history requirement, 49,369 deliveries enter campaign comparisons. The 12,650 hour-zero deliveries remain visible as insufficient history. Full-period snapshot segments and seven-day campaign segments use different purchase windows, so the snapshot customer counts cannot be used as campaign denominators.

The table reports eligible delivery counts and completion after a strictly earlier view. Percentages use the eligible reward-bearing deliveries in each segment and offer type.

| Pre-offer segment | BOGO deliveries | BOGO rate | Discount deliveries | Discount rate |
|---|---:|---:|---:|---:|
| Frequent, higher-spend recent | 2,387 | 51.36% | 1,595 | 45.96% |
| Frequent recent | 2,425 | 20.66% | 1,791 | 36.35% |
| Higher-spend recent | 915 | 51.04% | 589 | 47.88% |
| No purchases in window | 5,037 | 25.83% | 4,100 | 30.15% |
| Occasional, less recent | 4,322 | 29.99% | 3,275 | 37.68% |
| Other recent | 5,005 | 29.51% | 3,551 | 37.43% |
| Previously active, less recent | 1,010 | 44.55% | 844 | 45.97% |

An individual customer can contribute several deliveries and change segment over time. Rates pool offers with different requirements, rewards, channels, and timing. These descriptive comparisons identify experiments; the next hypothesis-testing stage will quantify uncertainty while accounting for repeated customers. A randomized control group is needed to estimate incremental purchasing.

## Campaign tests to prioritize

| Audience | Proposed test | Primary success measure |
|---|---|---|
| Frequent recent, below the higher-spend cutoff | Compare matched discount and BOGO offers. The observed completion gap is 15.69 percentage points. | Seven-day purchase amount per contacted customer, with repeat-purchase rate and issued reward amounts alongside it |
| Previously active, less recent | Compare a re-engagement offer with a randomized no-offer holdout. The snapshot group contributed 21.12% of observed purchase amount. | Incremental seven-day purchase rate |
| Frequent, higher-spend recent | Test an informational message against a reward-bearing offer and a holdout. | Purchase amount per contacted customer and issued reward amounts |
| Higher-spend recent | Test a reminder timed to the customer's purchase cadence. | Seven-day purchase rate |
| Other recent | Test a second-purchase or repeat-purchase reminder. | Seven-day repeat-purchase rate |
| Occasional, less recent | Test a small re-engagement campaign with a holdout. | Incremental seven-day purchase rate |
| No purchases in window | Test a purchase prompt. Separate customers with earlier observed purchases when choosing a first-purchase audience. | Seven-day purchase rate, with first-observed-purchase rate for the relevant audience |

Campaign audiences should be recalculated from information available at send time. Snapshot groups size current opportunities. The seven-day pre-offer logic supplies the historical comparison. A three-day gap indicates lower recent activity under the working rule; confirming churn would require a longer history.

## Verification and reproduction

The importer applies `sql/008_retention_rfm.sql` and runs `sql/010_retention_rfm_validation.sql`. Run `sql/009_retention_rfm_queries.sql` for the tables. Seventeen integration tests cover the funnel, retention boundaries, zero-activity cells, nonbuyers, tied metrics, and purchases recorded at or after receipt. Independent pandas calculations reproduced every retention cell, all 17,000 snapshot rows, and all 102,000 pre-offer feature rows.
