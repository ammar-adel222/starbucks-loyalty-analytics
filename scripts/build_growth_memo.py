"""Create a one-page growth memo from the validated database and campaign results."""

import json

import psycopg
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from import_data import PROJECT_DIR, connection_settings


def build_memo():
    results = json.loads((PROJECT_DIR / "results" / "campaign_comparisons.json").read_text(encoding="utf-8"))
    with psycopg.connect(**connection_settings(PROJECT_DIR / ".env")) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        manifests = [row[0] for row in connection.execute("SELECT manifest FROM loyalty.ingestion_batches ORDER BY imported_at")]
        if manifests != results["source_manifests"]:
            raise ValueError("Regenerate campaign comparisons for the current import before building the memo.")
        buyers, spend = connection.execute("SELECT COUNT(DISTINCT customer_id), SUM(transaction_amount) FROM loyalty.transactions").fetchone()
        eligible, no_view = connection.execute("""SELECT COUNT(*) FILTER (WHERE eligible_for_rates),
            COUNT(*) FILTER (WHERE eligible_for_rates AND completion_status='no_recorded_view')
            FROM loyalty.offer_deliveries""").fetchone()
        returning, cohort_total = connection.execute("""SELECT SUM(active_customers),SUM(cohort_customers)
            FROM loyalty.weekly_purchase_retention WHERE weeks_since_first_purchase=1""").fetchone()
        less_recent, share = connection.execute("""SELECT customers,spend_share_pct FROM loyalty.rfm_segment_summary
            WHERE rfm_segment='Previously active, less recent'""").fetchone()
        last_hour = connection.execute("SELECT MAX(time_hours) FROM loyalty.events").fetchone()[0]
    pair_index = next(index for index, pair in enumerate(results["pairs"], start=1)
        if pair["offer_a"]["offer_type"] == "discount"
        and float(pair["offer_a"]["difficulty"]) == 10 and float(pair["offer_a"]["reward"]) == 2)
    comparison = next(row for row in results["overall"] if row["pair"] == pair_index)
    retention = float(returning / cohort_total * 100)

    output_dir = PROJECT_DIR / "output" / "pdf"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "growth_recommendations.pdf"
    document = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=44, leftMargin=44,
        topMargin=36, bottomMargin=36, title="Starbucks Rewards growth recommendations", author="Starbucks Loyalty Analytics")
    green = colors.HexColor("#006241")
    ink = colors.HexColor("#18382D")
    body = ParagraphStyle("Body", fontName="Helvetica", fontSize=10, leading=14, textColor=ink, spaceAfter=7)
    heading = ParagraphStyle("Heading", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=green, spaceBefore=8, spaceAfter=5)
    title = ParagraphStyle("Title", parent=heading, fontSize=23, leading=27, spaceBefore=0, spaceAfter=8)
    small = ParagraphStyle("Small", parent=body, fontSize=8, leading=11, textColor=colors.HexColor("#52675E"))
    metric = ParagraphStyle("Metric", parent=body, fontSize=15, leading=19, fontName="Helvetica-Bold", spaceAfter=2)
    label = ParagraphStyle("Label", parent=small, fontSize=8, leading=11)
    story = [Paragraph("Starbucks Rewards", small), Paragraph("Growth recommendations", title),
        Paragraph(f"Decision memo for the loyalty team | Simulated observation, hours 0-{last_hour}", small)]
    metrics = Table([[
        [Paragraph(f"{buyers:,}", metric), Paragraph("Purchasing customers", label)],
        [Paragraph(f"${float(spend)/1_000_000:.2f}M", metric), Paragraph("Recorded purchase amount", label)],
        [Paragraph(f"{eligible:,}", metric), Paragraph("Eligible offer deliveries", label)],
    ]], colWidths=[174,174,176])
    metrics.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#EDF5EF")),
        ("TOPPADDING",(0,0),(-1,-1),12),("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("LEFTPADDING",(0,0),(-1,-1),12),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [Spacer(1,9),metrics,Spacer(1,10)]
    story += [Paragraph("Prioritize a controlled discount package test", heading),
        Paragraph(f"For spend-$10, reward-$2 offers, the 10-day package with email, mobile, social and web had a "
            f"{comparison['rate_b_pct']:.2f}% completion-after-view rate versus {comparison['rate_a_pct']:.2f}% for the 7-day package "
            f"with email, mobile and web. The observed gap was <b>{comparison['difference_pp']:.2f} percentage points</b> "
            f"(customer-clustered 95% CI {comparison['ci95_low_pp']:.2f}-{comparison['ci95_high_pp']:.2f}). "
            "Duration and channels change together. Randomize eligible customers between both packages and a no-offer holdout, balancing pre-offer RFM groups.", body),
        Paragraph("Measure value over the same 10 days after assignment in every arm. Use purchase amount per assigned customer, including zero spend, as the primary outcome. Track purchase rate and issued reward amounts. Agree on the minimum worthwhile difference before sizing the experiment.", body),
        Paragraph("Protect previously active customer relationships", heading),
        Paragraph(f"At the end-period snapshot, <b>{less_recent:,} previously active, less-recent customers contributed {share:.2f}%</b> "
            "of recorded purchase amount. Use this group to size the re-engagement opportunity, then recalculate audiences from information available at send time. "
            "The working definition uses a three-day recency cutoff and upper-quartile count or spend. Test re-engagement with a randomized holdout and measure seven-day purchase rate.", body),
        Paragraph("Monitor repeat purchasing and reward engagement", heading),
        Paragraph(f"<b>{retention:.2f}%</b> of customers in the three cohorts with complete following-week observation purchased again "
            f"({int(returning):,}/{int(cohort_total):,}). Track this calendar-week measure alongside cohort size. Investigate "
            f"<b>{no_view:,} eligible reward-bearing deliveries</b> completed with no recorded view, reviewing tracking, matching and timing before changing reward policy.", body),
        Paragraph("Interpretation and measurement", heading),
        Paragraph("The dataset is simulated and covers roughly 30 days. Offer rates exclude incomplete follow-up and ambiguous matches. "
            "Campaign features use the seven days strictly before receipt; early deliveries have insufficient history. "
            "Confidence intervals describe historical package associations. A randomized experiment and cost data are needed to estimate incremental purchasing and profit.", small),
        Paragraph('Sources are the validated PostgreSQL views and customer-clustered campaign comparisons. '
            '<link href="https://github.com/ammar-adel222/starbucks-loyalty-analytics" color="#006241">Project queries and methods on GitHub</link>.', small)]
    document.build(story)
    if document.page != 1:
        raise ValueError(f"Memo must be one page; generated {document.page} pages.")
    print(f"Created one-page memo: {path.relative_to(PROJECT_DIR)}")
    return path


if __name__ == "__main__":
    build_memo()
