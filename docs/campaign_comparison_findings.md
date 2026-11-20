# Campaign package comparisons

These comparisons quantify differences in completion after a strictly earlier view between offers with the same type, spending requirement, and reward. They help choose campaign packages for a controlled experiment. Duration and channel combinations vary together, and the historical assignment and eligibility filters can change audience composition.

## Comparison definitions

Pairs are chosen from catalog terms before fitting outcome comparisons. A is the shorter-duration package; equal durations use offer ID order. B is the other package. Every difference below is B minus A, measured in percentage points.

| Pair | Type | Required spend | Reward | A duration | A channels | B duration | B channels |
|---|---|---:|---:|---:|---|---:|---|
| 1 | bogo | $5 | $5 | 5.0 days | email, mobile, social, web | 7.0 days | email, mobile, web |
| 2 | bogo | $10 | $10 | 5.0 days | email, mobile, social, web | 7.0 days | email, mobile, social |
| 3 | discount | $10 | $2 | 7.0 days | email, mobile, web | 10.0 days | email, mobile, social, web |

## Overall package comparisons

The sample uses deliveries with full offer follow-up, unambiguous event matching, and seven days of observable purchase history. Each contrast retains receipt waves represented in both arms. The outcome uses each offer's full validity period, so a longer duration provides more time to complete. The null hypothesis is equal completion-after-view rates; tests are two-sided at the 5% level.

| Pair | A completed / deliveries | A rate | B completed / deliveries | B rate | Difference pp | Individual 95% CI pp | Raw p | Holm p |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| 1 | 1860 / 4698 | 39.59% | 1130 / 4712 | 23.98% | -15.61 | -17.48 to -13.74 | <0.0001 | <0.0001 |
| 2 | 1517 / 4780 | 31.74% | 1382 / 4610 | 29.98% | -1.76 | -3.62 to 0.11 | 0.0646 | 0.0646 |
| 3 | 904 / 3615 | 25.01% | 1760 / 3009 | 58.49% | 33.48 | 31.22 to 35.74 | <0.0001 | <0.0001 |

| Pair | Distinct customers in A | Distinct customers in B | Customer clusters across both arms | Common receipt hours | Deliveries outside common waves | Status |
|---|---:|---:|---:|---|---:|---|
| 1 | 4333 | 4331 | 7789 | 168, 336, 408, 504 | 1132 | estimated |
| 2 | 4401 | 4316 | 7795 | 168, 336, 408, 504 | 1169 | estimated |
| 3 | 3402 | 2955 | 5936 | 168, 336, 408 | 1157 | estimated |

## Package findings

Pair 1 has a higher observed completion-after-view rate for A by 15.61 percentage points. Its Holm-adjusted p-value is <0.0001.

Pair 2 has an estimated B-minus-A difference of -1.76 percentage points. Its 95% interval runs from -3.62 to 0.11, and the Holm-adjusted p-value is 0.0646.

Pair 3 has a higher observed completion-after-view rate for B by 33.48 percentage points. Its Holm-adjusted p-value is <0.0001.


## Business interpretation

Each positive difference describes a higher observed completion-after-view rate for B in the retained deliveries. Compare its confidence interval with the business value of the difference. The outcome combines engagement and qualifying completion; a different offer duration changes the opportunity to complete. A statistically detectable package difference supplies a candidate for randomized testing with purchase amount per contacted customer and issued reward amounts as business measures.

Receipt-wave matching restricts time support. Remaining differences in wave weights, customer mix, prior exposure, offer duration, channels, and eligibility can contribute to the rates. The estimates measure historical package associations. Incremental purchasing and profit require a suitable experiment and cost information.

For the next campaign experiment, randomize eligible customers between the two packages and a no-offer holdout, balancing pre-offer RFM groups. Measure purchase amount per assigned customer, including customers who spend zero, over the same post-send window in every arm. Track purchase rate and issued reward amounts alongside it. Choose the minimum worthwhile business difference before calculating the sample size.

## Exploratory customer segments

Segments use purchases recorded in the seven days strictly before receipt, the 72-hour recency rule, and the existing population quartile cutoffs. Each segment contrast finds its own common receipt waves. These groups were already inspected during descriptive analysis, so their tests remain exploratory. Holm correction is applied across all planned segment contrasts as a separate family.

| Pair | Pre-offer segment | A deliveries | A rate | B deliveries | B rate | Difference pp | Individual 95% CI pp | Holm p |
|---|---|---:|---:|---:|---:|---:|---|---:|
| 1 | Frequent, higher-spend recent | 558 | 56.09% | 574 | 33.10% | -22.99 | -28.65 to -17.34 | <0.0001 |
| 1 | Frequent recent | 527 | 31.88% | 558 | 15.41% | -16.47 | -21.48 to -11.45 | <0.0001 |
| 1 | Higher-spend recent | 174 | 56.90% | 177 | 40.11% | -16.78 | -27.21 to -6.35 | 0.0135 |
| 1 | No purchases in window | 1166 | 32.76% | 1167 | 19.45% | -13.31 | -16.83 to -9.79 | <0.0001 |
| 1 | Occasional, less recent | 975 | 39.28% | 911 | 24.37% | -14.91 | -19.08 to -10.74 | <0.0001 |
| 1 | Other recent | 1058 | 36.58% | 1082 | 23.84% | -12.73 | -16.58 to -8.89 | <0.0001 |
| 1 | Previously active, less recent | 240 | 53.33% | 243 | 31.28% | -22.06 | -30.76 to -13.36 | <0.0001 |
| 2 | Frequent, higher-spend recent | 542 | 56.46% | 501 | 58.28% | 1.83 | -4.12 to 7.77 | 1.0000 |
| 2 | Frequent recent | 593 | 14.33% | 509 | 19.25% | 4.92 | 0.55 to 9.29 | 0.1101 |
| 2 | Higher-spend recent | 198 | 57.07% | 171 | 42.11% | -14.97 | -25.17 to -4.76 | 0.0249 |
| 2 | No purchases in window | 1175 | 27.74% | 1180 | 22.88% | -4.86 | -8.36 to -1.37 | 0.0321 |
| 2 | Occasional, less recent | 966 | 27.43% | 959 | 26.49% | -0.95 | -4.94 to 3.04 | 1.0000 |
| 2 | Other recent | 1082 | 27.91% | 1076 | 29.09% | 1.18 | -2.65 to 5.01 | 1.0000 |
| 2 | Previously active, less recent | 224 | 53.57% | 214 | 38.79% | -14.79 | -24.03 to -5.54 | 0.0135 |
| 3 | Frequent, higher-spend recent | 348 | 34.20% | 238 | 75.63% | 41.43 | 34.01 to 48.86 | <0.0001 |
| 3 | Frequent recent | 355 | 21.69% | 288 | 65.97% | 44.28 | 37.30 to 51.26 | <0.0001 |
| 3 | Higher-spend recent | 141 | 34.04% | 119 | 68.07% | 34.02 | 22.49 to 45.56 | <0.0001 |
| 3 | No purchases in window | 1011 | 20.87% | 822 | 48.30% | 27.43 | 23.19 to 31.67 | <0.0001 |
| 3 | Occasional, less recent | 771 | 26.07% | 671 | 55.29% | 29.22 | 24.36 to 34.08 | <0.0001 |
| 3 | Other recent | 790 | 24.30% | 676 | 59.17% | 34.87 | 30.10 to 39.63 | <0.0001 |
| 3 | Previously active, less recent | 199 | 28.14% | 195 | 72.31% | 44.17 | 35.28 to 53.05 | <0.0001 |

## Statistical method and reproduction

An OLS model with an intercept and offer-B indicator estimates the delivery-weighted difference in proportions. Its standard errors use a customer-clustered sandwich covariance with the finite-sample correction. The same customer can contribute repeated deliveries and observations in both arms. Student t inference uses the number of customer clusters minus one as its degrees of freedom. Distinct customers are assumed independent. This models association within the observed comparison population.

Holm correction controls the tested family at 5% across 3 overall contrasts and separately across 21 exploratory segment contrasts. The displayed 95% intervals are individual intervals. Holm-adjusted p-values determine the multiple-testing decisions. Non-estimable contrasts retain their place in the family with p=1 for adjustment and an empty reported p-value.

Run `python scripts/import_data.py`, then `python scripts/compare_campaigns.py`. The script reads `loyalty.campaign_comparison_inputs` and writes this report plus aggregate results to `results/campaign_comparisons.json`. Input rows keep one record per delivery. Both arms retain the existing offer-expiry and ambiguity rules.

The implemented methods follow the statsmodels documentation for [clustered covariance](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html) and [Holm correction](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html).

## Source offer identifiers

- Pair 1 uses A `f19421c1d4aa40978ebb69ca19b0e20d` and B `9b98b8c7a33c4b65b9aebfe6a799e6d9`.
- Pair 2 uses A `4d5c57ea9a6940dd891ad53e9dbe8da0` and B `ae264e3637204a6fb9bb56bc8210ddfd`.
- Pair 3 uses A `2906b810c7d4411798c6938adc9daaa5` and B `fafdcd668e3743c1bb461111dcafc2a4`.

Source file hashes and row counts are included in the aggregate JSON result so the comparison population can be traced to its import.
