# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 1: refresh the feed every day and alert on changes
# MAGIC This notebook turns the pricing feed into a daily job.
# MAGIC
# MAGIC 1. It creates the job **Nimble shelf feed (daily)**. The job runs `01_build_shelf_feed` every morning on serverless compute.
# MAGIC 2. It creates the view `shelf_alerts`. The view lists what changed in the latest snapshot: a watched shoe priced well below its list price, or a rival brand in a sponsored slot on a search for your brand.
# MAGIC 3. It creates a SQL alert on that view. The alert emails you when the view has rows.
# MAGIC
# MAGIC Change the settings in the next cell before you run it.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start, warehouse_sql
cfg, nimble = start(spark, dbutils)

YOUR_BRAND = "Nike"                       # the brand whose searches you watch
WATCHED_PRODUCT = "pegasus 41"            # a product name fragment to watch for deep discounts
DISCOUNT_ALERT_PCT = 15                   # alert when the watched product sells this far below list price
RUN_AT_HOUR = 6                           # local hour for the daily refresh
TIMEZONE = "America/Los_Angeles"

# COMMAND ----------

# MAGIC %md ## 1. The daily job

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs

w = WorkspaceClient()
here = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
feed_notebook = here.rsplit("/", 1)[0] + "/01_build_shelf_feed"
JOB_NAME = "Nimble shelf feed (daily)"
settings = dict(
    name=JOB_NAME,
    tasks=[jobs.Task(task_key="build_shelf_feed", notebook_task=jobs.NotebookTask(notebook_path=feed_notebook))],
    schedule=jobs.CronSchedule(quartz_cron_expression=f"0 0 {RUN_AT_HOUR} * * ?", timezone_id=TIMEZONE),
    max_concurrent_runs=1,
    tags={"powered_by": "nimble"},
)
existing = next((j for j in w.jobs.list(name=JOB_NAME)), None)
if existing:
    w.jobs.reset(job_id=existing.job_id, new_settings=jobs.JobSettings(**settings))
    job_id = existing.job_id
else:
    job_id = w.jobs.create(**settings).job_id
print(f"Job {job_id} runs {feed_notebook} every day at {RUN_AT_HOUR}:00 {TIMEZONE}")
displayHTML(f'<a href="/jobs/{job_id}">Open the job</a>')

# COMMAND ----------

# MAGIC %md ## 2. The view of changes worth a look

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW shelf_alerts
COMMENT 'Changes in the latest shelf snapshot: a watched product sold far below list price, or a rival brand in a sponsored slot on a search for {YOUR_BRAND}. Powered by Nimble.'
AS
WITH latest AS (
  SELECT * FROM shelf_products WHERE captured_at = (SELECT max(captured_at) FROM shelf_products)
)
SELECT 'deep discount' AS reason, retailer, search_keyword, position, brand, product_name, price, list_price, discount_pct, product_url, captured_at
FROM latest
WHERE lower(product_name) LIKE '%{WATCHED_PRODUCT.lower()}%' AND discount_pct >= {DISCOUNT_ALERT_PCT}
UNION ALL
SELECT 'rival sponsored on your search', retailer, search_keyword, position, brand, product_name, price, list_price, discount_pct, product_url, captured_at
FROM latest
WHERE lower(search_keyword) LIKE '%{YOUR_BRAND.lower()}%' AND sponsored
  AND brand IS NOT NULL AND brand NOT IN ('{YOUR_BRAND}', 'Jordan')
""")
display(spark.sql("SELECT reason, retailer, search_keyword, position, brand, product_name, price, list_price, discount_pct FROM shelf_alerts ORDER BY reason, retailer, position"))

# COMMAND ----------

# MAGIC %md ## 3. The SQL alert
# MAGIC The alert checks the view an hour after the job and emails you when it finds rows.

# COMMAND ----------

from databricks.sdk.service import sql as dbsql

ALERT_NAME = "Nimble shelf feed: changes to review"
fq_view = f"`{cfg['catalog']}`.`{cfg['schema']}`.shelf_alerts"
alert = dbsql.AlertV2(
    display_name=ALERT_NAME,
    query_text=f"SELECT count(*) AS changes FROM {fq_view}",
    warehouse_id=cfg["warehouse_id"],
    evaluation=dbsql.AlertV2Evaluation(
        source=dbsql.AlertV2OperandColumn(name="changes"),
        comparison_operator=dbsql.ComparisonOperator.GREATER_THAN,
        threshold=dbsql.AlertV2Operand(value=dbsql.AlertV2OperandValue(double_value=0)),
        notification=dbsql.AlertV2Notification(subscriptions=[dbsql.AlertV2Subscription(user_email=cfg["user"])]),
    ),
    schedule=dbsql.CronSchedule(quartz_cron_schedule=f"0 0 {(RUN_AT_HOUR + 1) % 24} * * ?", timezone_id=TIMEZONE),
    custom_summary="Shelf feed: {{ALERT_RESULT_VALUE}} changes to review",
    parent_path=f"/Users/{cfg['user']}",
)
existing = next((a for a in w.alerts_v2.list_alerts() if a.display_name == ALERT_NAME), None)
if existing:
    w.alerts_v2.update_alert(id=existing.id, alert=alert, update_mask="display_name,query_text,warehouse_id,evaluation,schedule,custom_summary")
    alert_id = existing.id
else:
    alert_id = w.alerts_v2.create_alert(alert=alert).id
_, rows = warehouse_sql(w, cfg["warehouse_id"], f"SELECT count(*) FROM {fq_view}")
print(f"Alert {alert_id} created. The view has {rows[0][0]} rows today, so the alert would fire: {int(rows[0][0]) > 0}")
displayHTML(f'<a href="/sql/alerts-v2/{alert_id}">Open the alert</a>')

# COMMAND ----------

# MAGIC %md ## 4. Run the job once now
# MAGIC This run checks the job end to end. It takes about three minutes.

# COMMAND ----------

run = w.jobs.run_now(job_id=job_id)
print("Started run", run.run_id)
displayHTML(f'<a href="/jobs/{job_id}/runs/{run.run_id}">Follow the run</a>')
