# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 2: ratings and reviews, added to a table you already have
# MAGIC This notebook starts from a watchlist of products, one row per product.
# MAGIC A Nimble Web Search Agent reads each product's live pages on US retailers and the brand site.
# MAGIC It adds the star rating, review count, price, the retailer it read, and what reviewers praise and complain about.
# MAGIC Every value cites its page.
# MAGIC
# MAGIC The input is the table `product_watchlist`. The output is the table `product_reviews`. A run at effort high takes 10 to 25 minutes for 8 products.

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
from common.research import run_agent
cfg, nimble = start(spark, dbutils)

EFFORT = "high"     # enrichment accepts medium, high or x-high
RUN_ID = ""         # paste a run id here to read a finished run instead of starting a new one

# COMMAND ----------

# MAGIC %md ## 1. The watchlist
# MAGIC The first run creates `product_watchlist` with 8 running shoes. Edit the table to track your own products.

# COMMAND ----------

if not spark.catalog.tableExists("product_watchlist"):
    spark.createDataFrame([
        ("Nike", "Pegasus 41", "daily trainer"), ("Adidas", "Adizero Evo SL", "daily trainer"),
        ("HOKA", "Clifton 10", "daily trainer"), ("On", "Cloudmonster 2", "daily trainer"),
        ("Brooks", "Ghost 17", "daily trainer"), ("New Balance", "Fresh Foam X 1080v14", "daily trainer"),
        ("Asics", "Novablast 5", "daily trainer"), ("Saucony", "Ride 18", "daily trainer"),
    ], "brand STRING, model STRING, category STRING").write.saveAsTable("product_watchlist")
    spark.sql("COMMENT ON TABLE product_watchlist IS 'Products to enrich with live ratings and reviews. Powered by Nimble.'")
watchlist = [r.asDict() for r in spark.table("product_watchlist").collect()]
display(spark.table("product_watchlist"))

# COMMAND ----------

# MAGIC %md ## 2. Run the agent on the watchlist

# COMMAND ----------

task = ("Fill in the rating, review count, price, retailer, product URL, praise and complaints for each product. "
        "Use live US retailer or brand product pages and cite them.")
agent_id, run_id, rows, confidence = run_agent(nimble, "agents/product_reviews.json", task,
                                               input_data=watchlist, effort=EFFORT, run_id=RUN_ID)

# COMMAND ----------

# MAGIC %md ## 3. Land the rows in `product_reviews`

# COMMAND ----------

from datetime import datetime, timezone

def num(v, cast=float):
    try:
        return cast(v) if v is not None else None
    except (TypeError, ValueError):
        return None

records = [{
    "brand": r.get("brand"), "model": r.get("model"), "category": r.get("category"),
    "rating": num(r.get("rating")), "review_count": num(r.get("review_count"), int), "price_usd": num(r.get("price_usd")),
    "retailer": r.get("retailer"), "product_url": r.get("product_url"),
    "top_praise": r.get("top_praise") or [], "top_complaints": r.get("top_complaints") or [],
    "source_urls": r["_source_urls"], "high_confidence_share": r["_high_confidence_share"], "claims_json": r["_claims_json"],
    "run_confidence": confidence, "run_id": run_id, "loaded_at": datetime.now(timezone.utc),
} for r in rows]
schema = """brand STRING, model STRING, category STRING, rating DOUBLE, review_count INT, price_usd DOUBLE, retailer STRING,
product_url STRING, top_praise ARRAY<STRING>, top_complaints ARRAY<STRING>, source_urls ARRAY<STRING>,
high_confidence_share DOUBLE, claims_json STRING, run_confidence STRING, run_id STRING, loaded_at TIMESTAMP"""
spark.createDataFrame(records, schema).write.mode("append").option("mergeSchema", "true").saveAsTable("product_reviews")
spark.sql("COMMENT ON TABLE product_reviews IS 'Live star rating, review count, price, praise and complaints for each watchlist product, one row per product per run. Every value cites its page. Powered by Nimble Web Search Agents.'")

display(spark.sql("""
SELECT brand, model, rating, review_count, price_usd, retailer, top_praise, top_complaints, product_url
FROM product_reviews WHERE run_id = (SELECT max_by(run_id, loaded_at) FROM product_reviews)
ORDER BY rating DESC
"""))
