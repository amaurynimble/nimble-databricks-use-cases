# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 1: build a retail pricing feed
# MAGIC This notebook builds a pricing and shelf feed for running shoes from five US retailers: Amazon, Walmart, Target, Foot Locker and ASOS.
# MAGIC Nimble runs the same search a shopper runs on each retailer site, and returns every product on the results page.
# MAGIC Each row holds the price, the list price when the item is on sale, the rating, the review count and whether the slot is sponsored.
# MAGIC
# MAGIC The feed lands in the Delta table `shelf_products`. Each run adds a dated snapshot, so the table builds a price history.
# MAGIC The searches come from the control table `shelf_queries`. Add a row there to track a new keyword or retailer.
# MAGIC
# MAGIC Run `00_install` once before this notebook.

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
from common.shelf import RETAILERS, normalise
cfg, nimble = start(spark, dbutils)

# COMMAND ----------

# MAGIC %md ## 1. The control table
# MAGIC The first run creates `shelf_queries` with 8 keywords on 5 retailers. Later runs keep your edits.

# COMMAND ----------

DEFAULT_KEYWORDS = [
    "nike running shoes", "nike pegasus 41", "nike air max", "adidas running shoes",
    "hoka running shoes", "on cloud running shoes", "new balance running shoes", "asics running shoes",
]
if not spark.catalog.tableExists("shelf_queries"):
    rows = [(r, k, True) for r in RETAILERS for k in DEFAULT_KEYWORDS]
    spark.createDataFrame(rows, "retailer STRING, keyword STRING, enabled BOOLEAN") \
        .write.saveAsTable("shelf_queries")
    spark.sql("COMMENT ON TABLE shelf_queries IS 'Searches the shelf feed runs: one row per retailer and keyword. Powered by Nimble.'")
    print("Created shelf_queries")
display(spark.sql("SELECT retailer, count(*) AS keywords FROM shelf_queries WHERE enabled GROUP BY retailer ORDER BY retailer"))

# COMMAND ----------

# MAGIC %md ## 2. Run every search through Nimble
# MAGIC The 40 searches run in parallel and take about two minutes. A retailer that times out is retried once.

# COMMAND ----------

import time
from datetime import datetime, timezone

queries = [r.asDict() for r in spark.sql("SELECT retailer, keyword FROM shelf_queries WHERE enabled").collect()]
jobs = []
for q in queries:
    template, param = RETAILERS[q["retailer"]]
    jobs.append({"template": template, "params": {param: q["keyword"]}, **q})

t0 = time.time()
captured_at = datetime.now(timezone.utc)
results = nimble.template_run_many(jobs, workers=10)
retry = [j for j, items, err in results if not items]
if retry:
    print(f"Retrying {len(retry)} empty searches")
    results = [r for r in results if r[1]] + nimble.template_run_many(retry, workers=5)

rows, empty = [], []
for job, items, err in results:
    if not items:
        empty.append(f"{job['retailer']} / {job['keyword']}")
    for it in items:
        if isinstance(it, dict):
            rows.append(normalise(job["retailer"], job["keyword"], it, captured_at))
print(f"{len(rows)} products from {len(results) - len(empty)} of {len(results)} searches in {time.time() - t0:.0f} s")
if empty:
    print("No results for:", ", ".join(empty))

# COMMAND ----------

# MAGIC %md ## 3. Append the snapshot to `shelf_products`

# COMMAND ----------

SCHEMA = """retailer STRING, search_keyword STRING, position INT, product_name STRING, brand STRING, price DOUBLE,
list_price DOUBLE, discount_pct DOUBLE, rating DOUBLE, review_count INT, sponsored BOOLEAN, in_stock BOOLEAN,
product_id STRING, product_url STRING, image_url STRING, captured_at TIMESTAMP"""
df = spark.createDataFrame(rows, SCHEMA)
df.write.mode("append").option("mergeSchema", "true").saveAsTable("shelf_products")
spark.sql("COMMENT ON TABLE shelf_products IS 'Retail shelf feed: every product on the search results page of five US retailers, one snapshot per run. Powered by Nimble.'")
print("shelf_products now holds", spark.table("shelf_products").count(), "rows")

# COMMAND ----------

# MAGIC %md ## 4. Read the latest snapshot
# MAGIC This query compares brands across retailers. It shows the number of products, the average price, the share on sale and the share of sponsored slots.

# COMMAND ----------

display(spark.sql("""
WITH latest AS (
  SELECT * FROM shelf_products WHERE captured_at = (SELECT max(captured_at) FROM shelf_products)
)
SELECT brand, retailer,
       count(*)                                           AS products,
       round(avg(price), 2)                               AS avg_price,
       round(100 * avg(CASE WHEN list_price IS NOT NULL THEN 1 ELSE 0 END), 1) AS pct_on_sale,
       round(avg(discount_pct), 1)                        AS avg_discount_pct,
       round(100 * avg(CASE WHEN sponsored THEN 1 ELSE 0 END), 1)       AS pct_sponsored
FROM latest
WHERE brand IN ('Nike', 'Jordan', 'adidas', 'HOKA', 'On', 'New Balance', 'Asics', 'Brooks', 'Puma')
GROUP BY brand, retailer
ORDER BY brand, retailer
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC Next, open `02_schedule_and_alert` to refresh this feed every day, then `03_dashboard` to publish a dashboard on it.
