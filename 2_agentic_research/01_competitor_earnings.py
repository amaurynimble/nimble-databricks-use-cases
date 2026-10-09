# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 2: competitor quarterly earnings, researched by an agent
# MAGIC You give a list of companies in plain language. A Nimble Web Search Agent reads each company's own earnings releases and filings, and returns one row per company per quarter.
# MAGIC Each row holds revenue, growth, gross margin and operating income.
# MAGIC Every value carries the URL it came from and a confidence grade, so an analyst can check any number.
# MAGIC
# MAGIC The notebook starts one agent run per company, all at the same time. The rows land in the Delta table `competitor_earnings`.
# MAGIC At effort high the runs take 5 to 15 minutes.
# MAGIC To refresh after the next earnings season, run the notebook again. New quarters are added and existing ones are updated.

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
from common.research import run_agent_parallel
cfg, nimble = start(spark, dbutils)

COMPANIES = ["Nike", "adidas", "Puma", "On Holding", "Deckers Outdoor (HOKA)", "Lululemon", "Under Armour", "Asics"]
QUARTERS = 4
EFFORT = "high"     # dataset building needs high or x-high

# COMMAND ----------

tasks = {c: (f"Return the {QUARTERS} most recent fiscal quarters that {c} has reported as of today, one row per quarter. "
             "Use the company's own fiscal calendar, quarter labels and reporting currency.") for c in COMPANIES}
agent_id, rows = run_agent_parallel(nimble, "agents/competitor_earnings.json", tasks, effort=EFFORT)

# COMMAND ----------

# MAGIC %md ## Land the rows in `competitor_earnings`

# COMMAND ----------

from datetime import datetime, timezone

def num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None

records = [{
    "company": r.get("company"), "ticker": r.get("ticker"),
    "fiscal_quarter_label": r.get("fiscal_quarter_label"), "quarter_end_date": r.get("quarter_end_date"),
    "revenue_millions": num(r.get("revenue_millions")), "currency": r.get("currency"),
    "revenue_growth_yoy_pct": num(r.get("revenue_growth_yoy_pct")), "gross_margin_pct": num(r.get("gross_margin_pct")),
    "operating_income_millions": num(r.get("operating_income_millions")),
    "source_url": r.get("source_url"), "source_type": r.get("source_type"),
    "source_urls": r["_source_urls"], "high_confidence_share": r["_high_confidence_share"], "claims_json": r["_claims_json"],
    "run_confidence": r["_run_confidence"], "run_id": r["_run_id"], "loaded_at": datetime.now(timezone.utc),
} for r in rows if r.get("company") and r.get("revenue_millions") is not None]

schema = """company STRING, ticker STRING, fiscal_quarter_label STRING, quarter_end_date STRING, revenue_millions DOUBLE,
currency STRING, revenue_growth_yoy_pct DOUBLE, gross_margin_pct DOUBLE, operating_income_millions DOUBLE, source_url STRING,
source_type STRING, source_urls ARRAY<STRING>, high_confidence_share DOUBLE, claims_json STRING, run_confidence STRING,
run_id STRING, loaded_at TIMESTAMP"""
spark.createDataFrame(records, schema).selectExpr("*", "try_cast(quarter_end_date AS DATE) AS quarter_end").drop("quarter_end_date") \
    .withColumnRenamed("quarter_end", "quarter_end_date").createOrReplaceTempView("new_rows")

spark.sql("""
CREATE TABLE IF NOT EXISTS competitor_earnings (
  company STRING, ticker STRING, fiscal_quarter_label STRING, revenue_millions DOUBLE, currency STRING,
  revenue_growth_yoy_pct DOUBLE, gross_margin_pct DOUBLE, operating_income_millions DOUBLE, source_url STRING,
  source_type STRING, source_urls ARRAY<STRING>, high_confidence_share DOUBLE, claims_json STRING, run_confidence STRING,
  run_id STRING, loaded_at TIMESTAMP, quarter_end_date DATE)
COMMENT 'Quarterly revenue, growth, gross margin and operating income per company, from each issuer''s own earnings release or filing. Revenue in millions of the reporting currency. Every row cites its source. Powered by Nimble Web Search Agents.'
""")
spark.sql("""
MERGE INTO competitor_earnings t
USING (SELECT * FROM new_rows QUALIFY row_number() OVER (PARTITION BY lower(company), quarter_end_date ORDER BY high_confidence_share DESC NULLS LAST) = 1) s
ON lower(t.company) = lower(s.company) AND t.quarter_end_date = s.quarter_end_date
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
""")
print("competitor_earnings holds", spark.table("competitor_earnings").count(), "rows")

# COMMAND ----------

display(spark.sql("""
SELECT company, fiscal_quarter_label, quarter_end_date, revenue_millions, currency, revenue_growth_yoy_pct,
       gross_margin_pct, high_confidence_share, source_url
FROM competitor_earnings ORDER BY company, quarter_end_date DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC Check any gap before you fill it. A company that went private stops reporting. Asics publishes only cumulative half-year and nine-month totals, so the agent leaves its single quarters empty and does not guess a number. The notebook keeps only rows with a revenue figure.
