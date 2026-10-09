# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 1 (optional): compare Nimble with your current pricing feed
# MAGIC Run this notebook when you have a sample of the feed you buy today.
# MAGIC It matches your vendor's rows to the Nimble feed on retailer and product id, then reports three numbers per retailer:
# MAGIC
# MAGIC - **Coverage:** the share of your vendor's products that Nimble also found.
# MAGIC - **Price match:** the share of matched products where both prices agree within 2%.
# MAGIC - **Freshness:** the age of each feed's latest price, in hours.
# MAGIC
# MAGIC Load your sample into a table with these columns, then set `VENDOR_TABLE` below:
# MAGIC `retailer` (amazon, walmart, target, footlocker or asos), `product_id` (ASIN, Walmart id, Target TCIN or the retailer's id), `price`, `captured_at`.

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
cfg, nimble = start(spark, dbutils)

VENDOR_TABLE = ""   # for example "main.pricing.vendor_feed_sample"
PRICE_TOLERANCE_PCT = 2

# COMMAND ----------

if not VENDOR_TABLE:
    dbutils.notebook.exit("Set VENDOR_TABLE to your vendor sample, then run again.")

display(spark.sql(f"""
WITH vendor AS (
  SELECT lower(retailer) AS retailer, CAST(product_id AS STRING) AS product_id, price, captured_at
  FROM {VENDOR_TABLE}
  QUALIFY row_number() OVER (PARTITION BY lower(retailer), product_id ORDER BY captured_at DESC) = 1
),
nimble AS (
  SELECT retailer, product_id, price, captured_at FROM shelf_products
  QUALIFY row_number() OVER (PARTITION BY retailer, product_id ORDER BY captured_at DESC) = 1
)
SELECT v.retailer,
       count(*)                                                    AS vendor_products,
       count(n.product_id)                                         AS found_by_nimble,
       round(100 * count(n.product_id) / count(*), 1)              AS coverage_pct,
       round(100 * avg(CASE WHEN n.product_id IS NULL THEN NULL
                            WHEN abs(n.price - v.price) <= v.price * {PRICE_TOLERANCE_PCT} / 100 THEN 1 ELSE 0 END), 1) AS price_match_pct,
       round(avg((unix_timestamp() - unix_timestamp(v.captured_at)) / 3600), 1) AS vendor_age_hours,
       round(avg((unix_timestamp() - unix_timestamp(n.captured_at)) / 3600), 1) AS nimble_age_hours
FROM vendor v LEFT JOIN nimble n ON n.retailer = v.retailer AND n.product_id = v.product_id
GROUP BY v.retailer ORDER BY v.retailer
"""))
