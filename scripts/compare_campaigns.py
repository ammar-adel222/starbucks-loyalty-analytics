"""Compare catalog-matched offer packages using customer-clustered inference."""

import argparse
from itertools import combinations
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row
import statsmodels
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from import_data import PROJECT_DIR, connection_settings


RFM_SEGMENTS = (
    "Frequent, higher-spend recent", "Frequent recent", "Higher-spend recent",
    "No purchases in window", "Occasional, less recent", "Other recent",
    "Previously active, less recent",
)


def catalog_pairs(catalog):
    """Select all reward-bearing pairs with identical type, requirement, and reward."""
    pairs = []
    for _, group in catalog.loc[catalog["offer_type"].ne("informational")].groupby(
        ["offer_type", "difficulty", "reward"], sort=True
    ):
        group = group.sort_values(["duration_days", "offer_id"])
        for a, b in combinations(group.to_dict("records"), 2):
            pairs.append({"offer_a": a, "offer_b": b})
    return pairs


def compare_rates(data, offer_a, offer_b):
    """Estimate the delivery-weighted rate difference B minus A on common receipt waves."""
    if offer_a == offer_b:
        raise ValueError("Comparison requires two different offers.")
    sample = data.loc[data["offer_id"].isin([offer_a, offer_b])].copy()
    if sample[["customer_id", "received_hour", "completed_after_view"]].isna().any().any():
        raise ValueError("Comparison data contains missing identifiers, waves, or outcomes.")
    if not sample["completed_after_view"].isin([0, 1]).all():
        raise ValueError("Completion outcomes must be binary.")
    waves_a = set(sample.loc[sample["offer_id"].eq(offer_a), "received_hour"])
    waves_b = set(sample.loc[sample["offer_id"].eq(offer_b), "received_hour"])
    waves = sorted(waves_a & waves_b)
    included = sample.loc[sample["received_hour"].isin(waves)].copy()
    result = {
        "offer_a": offer_a, "offer_b": offer_b, "common_waves": [int(wave) for wave in waves],
        "excluded_for_wave_support": len(sample) - len(included),
        "customer_clusters": int(included["customer_id"].nunique()),
        "difference_pp": None, "std_error_pp": None, "ci95_low_pp": None,
        "ci95_high_pp": None, "p_value": None, "status": "no_common_waves",
    }
    for arm, offer_id in (("a", offer_a), ("b", offer_b)):
        rows = included.loc[included["offer_id"].eq(offer_id)]
        result[f"deliveries_{arm}"] = len(rows)
        result[f"customers_{arm}"] = int(rows["customer_id"].nunique())
        result[f"completed_{arm}"] = int(rows["completed_after_view"].sum())
        result[f"rate_{arm}_pct"] = float(rows["completed_after_view"].mean() * 100) if len(rows) else None
    if not waves:
        return result
    result["difference_pp"] = result["rate_b_pct"] - result["rate_a_pct"]
    if result["customer_clusters"] < 2 or len(included) <= 2:
        result["status"] = "insufficient_clusters_or_deliveries"
        return result
    if included.groupby("offer_id")["completed_after_view"].nunique().le(1).all():
        result["status"] = "degenerate_variance"
        return result

    design = pd.DataFrame({
        "constant": np.ones(len(included)),
        "offer_b": included["offer_id"].eq(offer_b).to_numpy(dtype=float),
    })
    groups, _ = pd.factorize(included["customer_id"])
    fit = sm.OLS(included["completed_after_view"].to_numpy(dtype=float), design).fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True, "df_correction": True},
        use_t=True,
    )
    standard_error = float(fit.bse["offer_b"])
    if not np.isfinite(standard_error) or standard_error <= 1e-12:
        result["status"] = "degenerate_variance"
        return result
    interval = fit.conf_int(alpha=0.05).loc["offer_b"]
    result.update({
        "std_error_pp": 100 * standard_error,
        "ci95_low_pp": float(100 * interval.iloc[0]),
        "ci95_high_pp": float(100 * interval.iloc[1]),
        "p_value": float(fit.pvalues["offer_b"]),
        "status": "estimated",
    })
    return result


def adjust_family(results):
    """Apply Holm across the entire planned family, retaining non-estimable contrasts."""
    if not results:
        return
    p_values = [row["p_value"] if row["p_value"] is not None else 1.0 for row in results]
    rejected, adjusted, _, _ = multipletests(p_values, alpha=0.05, method="holm")
    for row, reject, p_value in zip(results, rejected, adjusted):
        row["p_holm"] = float(p_value) if row["p_value"] is not None else None
        row["reject_holm_05"] = bool(reject) if row["p_value"] is not None else False


def analyze(data, catalog):
    if data["delivery_id"].duplicated().any():
        raise ValueError("Each delivery must appear once in the comparison input.")
    main, exploratory = [], []
    pairs = catalog_pairs(catalog)
    for pair_number, pair in enumerate(pairs, start=1):
        a, b = pair["offer_a"]["offer_id"], pair["offer_b"]["offer_id"]
        row = compare_rates(data, a, b)
        row["pair"] = pair_number
        main.append(row)
        for segment in RFM_SEGMENTS:
            row = compare_rates(data.loc[data["rfm_segment"].eq(segment)], a, b)
            row.update({"pair": pair_number, "rfm_segment": segment})
            exploratory.append(row)
    adjust_family(main)
    adjust_family(exploratory)
    return pairs, main, exploratory


def number(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def p_text(value):
    if value is None:
        return "—"
    return "<0.0001" if value < 0.0001 else f"{value:.4f}"


def render_report(pairs, main, exploratory):
    lines = [
        "# Campaign package comparisons",
        "",
        "These comparisons quantify differences in completion after a strictly earlier view between offers with the same type, spending requirement, and reward. They help choose campaign packages for a controlled experiment. Duration and channel combinations vary together, and the historical assignment and eligibility filters can change audience composition.",
        "",
        "## Comparison definitions",
        "",
        "Pairs are chosen from catalog terms before fitting outcome comparisons. A is the shorter-duration package; equal durations use offer ID order. B is the other package. Every difference below is B minus A, measured in percentage points.",
        "",
        "| Pair | Type | Required spend | Reward | A duration | A channels | B duration | B channels |",
        "|---|---|---:|---:|---:|---|---:|---|",
    ]
    for index, pair in enumerate(pairs, start=1):
        a, b = pair["offer_a"], pair["offer_b"]
        lines.append(f"| {index} | {a['offer_type']} | ${a['difficulty']} | ${a['reward']} | {a['duration_days']} days | {a['channels']} | {b['duration_days']} days | {b['channels']} |")
    lines += [
        "", "## Overall package comparisons", "",
        "The sample uses deliveries with full offer follow-up, unambiguous event matching, and seven days of observable purchase history. Each contrast retains receipt waves represented in both arms. The outcome uses each offer's full validity period, so a longer duration provides more time to complete. The null hypothesis is equal completion-after-view rates; tests are two-sided at the 5% level.",
        "",
        "| Pair | A completed / deliveries | A rate | B completed / deliveries | B rate | Difference pp | Individual 95% CI pp | Raw p | Holm p |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for row in main:
        interval = f"{number(row['ci95_low_pp'])} to {number(row['ci95_high_pp'])}"
        lines.append(f"| {row['pair']} | {row['completed_a']} / {row['deliveries_a']} | {number(row['rate_a_pct'])}% | {row['completed_b']} / {row['deliveries_b']} | {number(row['rate_b_pct'])}% | {number(row['difference_pp'])} | {interval} | {p_text(row['p_value'])} | {p_text(row['p_holm'])} |")
    lines += ["", "| Pair | Distinct customers in A | Distinct customers in B | Customer clusters across both arms | Common receipt hours | Deliveries outside common waves | Status |", "|---|---:|---:|---:|---|---:|---|"]
    for row in main:
        waves = ", ".join(map(str, row["common_waves"])) or "—"
        lines.append(f"| {row['pair']} | {row['customers_a']} | {row['customers_b']} | {row['customer_clusters']} | {waves} | {row['excluded_for_wave_support']} | {row['status']} |")
    lines += ["", "## Package findings", ""]
    for row in main:
        if row["status"] != "estimated":
            lines.append(f"Pair {row['pair']} has status `{row['status']}` and requires more usable comparison data for inference.")
        elif row["reject_holm_05"]:
            higher_arm = "B" if row["difference_pp"] > 0 else "A"
            lines.append(f"Pair {row['pair']} has a higher observed completion-after-view rate for {higher_arm} by {abs(row['difference_pp']):.2f} percentage points. Its Holm-adjusted p-value is {p_text(row['p_holm'])}.")
        else:
            lines.append(f"Pair {row['pair']} has an estimated B-minus-A difference of {number(row['difference_pp'])} percentage points. Its 95% interval runs from {number(row['ci95_low_pp'])} to {number(row['ci95_high_pp'])}, and the Holm-adjusted p-value is {p_text(row['p_holm'])}.")
        lines.append("")
    lines += [
        "", "## Business interpretation", "",
        "Each positive difference describes a higher observed completion-after-view rate for B in the retained deliveries. Compare its confidence interval with the business value of the difference. The outcome combines engagement and qualifying completion; a different offer duration changes the opportunity to complete. A statistically detectable package difference supplies a candidate for randomized testing with purchase amount per contacted customer and issued reward amounts as business measures.",
        "",
        "Receipt-wave matching restricts time support. Remaining differences in wave weights, customer mix, prior exposure, offer duration, channels, and eligibility can contribute to the rates. The estimates measure historical package associations. Incremental purchasing and profit require a suitable experiment and cost information.",
        "",
        "For the next campaign experiment, randomize eligible customers between the two packages and a no-offer holdout, balancing pre-offer RFM groups. Measure purchase amount per assigned customer, including customers who spend zero, over the same post-send window in every arm. Track purchase rate and issued reward amounts alongside it. Choose the minimum worthwhile business difference before calculating the sample size.",
        "",
        "## Exploratory customer segments", "",
        "Segments use purchases recorded in the seven days strictly before receipt, the 72-hour recency rule, and the existing population quartile cutoffs. Each segment contrast finds its own common receipt waves. These groups were already inspected during descriptive analysis, so their tests remain exploratory. Holm correction is applied across all planned segment contrasts as a separate family.",
        "",
        "| Pair | Pre-offer segment | A deliveries | A rate | B deliveries | B rate | Difference pp | Individual 95% CI pp | Holm p |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in exploratory:
        interval = f"{number(row['ci95_low_pp'])} to {number(row['ci95_high_pp'])}"
        lines.append(f"| {row['pair']} | {row['rfm_segment']} | {row['deliveries_a']} | {number(row['rate_a_pct'])}% | {row['deliveries_b']} | {number(row['rate_b_pct'])}% | {number(row['difference_pp'])} | {interval} | {p_text(row['p_holm'])} |")
    lines += [
        "", "## Statistical method and reproduction", "",
        "An OLS model with an intercept and offer-B indicator estimates the delivery-weighted difference in proportions. Its standard errors use a customer-clustered sandwich covariance with the finite-sample correction. The same customer can contribute repeated deliveries and observations in both arms. Student t inference uses the number of customer clusters minus one as its degrees of freedom. Distinct customers are assumed independent. This models association within the observed comparison population.",
        "",
        f"Holm correction controls the tested family at 5% across {len(main)} overall contrasts and separately across {len(exploratory)} exploratory segment contrasts. The displayed 95% intervals are individual intervals. Holm-adjusted p-values determine the multiple-testing decisions. Non-estimable contrasts retain their place in the family with p=1 for adjustment and an empty reported p-value.",
        "",
        "Run `python scripts/import_data.py`, then `python scripts/compare_campaigns.py`. The script reads `loyalty.campaign_comparison_inputs` and writes this report plus aggregate results to `results/campaign_comparisons.json`. Input rows keep one record per delivery. Both arms retain the existing offer-expiry and ambiguity rules.",
        "",
        "The implemented methods follow the statsmodels documentation for [clustered covariance](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html) and [Holm correction](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html).",
        "", "## Source offer identifiers", "",
    ]
    for index, pair in enumerate(pairs, start=1):
        lines.append(f"- Pair {index} uses A `{pair['offer_a']['offer_id']}` and B `{pair['offer_b']['offer_id']}`.")
    lines += ["", "Source file hashes and row counts are included in the aggregate JSON result so the comparison population can be traced to its import.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=PROJECT_DIR / ".env")
    args = parser.parse_args()
    try:
        with psycopg.connect(**connection_settings(args.env_file), row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            rows = connection.execute("SELECT * FROM loyalty.campaign_comparison_inputs ORDER BY delivery_id").fetchall()
            catalog_rows = connection.execute("""SELECT o.*, COALESCE(STRING_AGG(c.channel, ', ' ORDER BY c.channel), '') AS channels
                FROM loyalty.offers AS o LEFT JOIN loyalty.offer_channels AS c USING (offer_id)
                GROUP BY o.offer_id ORDER BY o.offer_id""").fetchall()
            manifests = connection.execute("SELECT manifest FROM loyalty.ingestion_batches ORDER BY imported_at").fetchall()
        if not rows or not catalog_rows:
            raise ValueError("Import the dataset before comparing campaigns.")
        data, catalog = pd.DataFrame(rows), pd.DataFrame(catalog_rows)
        pairs, overall, exploratory = analyze(data, catalog)
        result = {
            "method": "customer-clustered OLS difference in proportions; t inference; Holm correction",
            "outcome": "completion after strictly earlier view", "alpha": 0.05,
            "source_manifests": [row["manifest"] for row in manifests],
            "input_deliveries": len(data), "pairs": pairs, "overall": overall, "exploratory": exploratory,
            "versions": {"numpy": np.__version__, "pandas": pd.__version__, "statsmodels": statsmodels.__version__},
        }
        report = render_report(pairs, overall, exploratory)
        result_dir, doc_dir = PROJECT_DIR / "results", PROJECT_DIR / "docs"
        result_dir.mkdir(exist_ok=True)
        doc_dir.mkdir(exist_ok=True)
        (result_dir / "campaign_comparisons.json").write_text(
            json.dumps(result, default=str, allow_nan=False, indent=2) + "\n", encoding="utf-8"
        )
        (doc_dir / "campaign_comparison_findings.md").write_text(report, encoding="utf-8")
        print(f"Compared {len(overall)} catalog pairs and {len(exploratory)} segment contrasts.")
        for row in overall:
            print(f"Pair {row['pair']}: B-A {number(row['difference_pp'])} pp; 95% CI {number(row['ci95_low_pp'])} to {number(row['ci95_high_pp'])}; Holm p {p_text(row['p_holm'])}")
    except psycopg.Error as error:
        print(f"Campaign query failed: {error.diag.message_primary or type(error).__name__}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"Campaign comparison failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
