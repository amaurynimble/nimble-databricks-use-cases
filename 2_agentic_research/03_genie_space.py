# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 2: ask questions in plain English with Genie
# MAGIC This notebook creates the Genie space **Market research (Nimble)**.
# MAGIC The space holds the research tables and the live Nimble functions.
# MAGIC Genie answers from the tables first. When the tables can't answer, it calls Nimble for live web data.
# MAGIC
# MAGIC Then the notebook asks Genie three sample questions.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import json, os, sys, uuid
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
from databricks.sdk import WorkspaceClient
cfg, nimble = start(spark, dbutils)
w = WorkspaceClient()
fq = lambda n: f"{cfg['catalog']}.{cfg['schema']}.{n}"

TITLE = "Market research (Nimble)"
tables = sorted(fq(t) for t in ("competitor_earnings", "product_reviews", "product_watchlist", "shelf_products")
                if spark.catalog.tableExists(fq(t)))
functions = [fq(f) for f in ("nimble_search", "nimble_retail_search", "nimble_product_reviews")] if cfg.get("warehouse_functions_ok") else []
if not functions:
    print("The SQL warehouse can't reach Nimble yet, so the space gets tables only. See step 4 of 00_install.")
INSTRUCTIONS = """You answer questions about competitors and the retail shelf.
- competitor_earnings: quarterly revenue, growth, gross margin and operating income per company. Revenue is in millions of each company's reporting currency, so compare growth and margins across companies, not raw revenue. Quote fiscal_quarter_label and source_url.
- product_reviews: live rating, review count, price, praise and complaints per watchlist product. Use the latest run_id per product.
- shelf_products: retailer search results, one snapshot per day. Use the latest captured_at unless asked for a trend. list_price is set only when the item is on sale.
- When the tables can't answer (today's news, a product not in the tables, a live price), call nimble_search, nimble_retail_search or nimble_product_reviews, and cite the URLs.
"""
space = {
    "version": 2,
    "data_sources": {"tables": [{"identifier": t} for t in tables]},
    "instructions": {
        "text_instructions": [{"id": uuid.uuid4().hex, "content": [l + "\n" for l in INSTRUCTIONS.splitlines()]}],
        "sql_functions": sorted([{"id": uuid.uuid4().hex, "identifier": f} for f in functions], key=lambda f: (f["id"], f["identifier"])),
    },
}
body = {"title": TITLE, "warehouse_id": cfg["warehouse_id"], "parent_path": f"/Users/{cfg['user']}", "serialized_space": json.dumps(space)}

listing = w.api_client.do("GET", "/api/2.0/genie/spaces") or {}
existing = next((s for s in listing.get("spaces", []) if s.get("title") == TITLE), None)
if existing:
    space_id = existing["space_id"]
    w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{space_id}", body=body)
else:
    space_id = w.api_client.do("POST", "/api/2.0/genie/spaces", body=body)["space_id"]
cfg["genie_space_id"] = space_id
from common import config; config.save(cfg["user"], {k: v for k, v in cfg.items() if k != "user"})
print("Genie space", space_id, "with", len(tables), "tables and", len(functions), "functions")
displayHTML(f'<a href="/genie/rooms/{space_id}">Open the Genie space</a>')

# COMMAND ----------

# MAGIC %md ## Ask three sample questions

# COMMAND ----------

QUESTIONS = [
    "Which company grew revenue fastest in its latest quarter, and what was its gross margin?",
    "Which products on the watchlist have a rating above 4.5, and what do reviewers complain about?",
    "On which retailer is Nike most often on sale in the latest shelf snapshot?",
]
for q in QUESTIONS:
    msg = w.genie.start_conversation_and_wait(space_id=space_id, content=q)
    print("Q:", q)
    for a in msg.attachments or []:
        if a.text and a.text.content:
            print("A:", a.text.content[:800])
        if a.query:
            if a.query.description:
                print("A:", a.query.description[:800])
            res = w.genie.get_message_attachment_query_result(space_id, msg.conversation_id, msg.message_id, a.attachment_id)
            sr = res.statement_response
            cols = [c.name for c in sr.manifest.schema.columns]
            for row in (sr.result.data_array or [])[:5]:
                print("   ", dict(zip(cols, row)))
    print()
