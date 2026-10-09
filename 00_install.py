# Databricks notebook source
# MAGIC %md
# MAGIC # Install
# MAGIC This notebook prepares your workspace for the three use cases in this repository. It takes about two minutes.
# MAGIC
# MAGIC It does five things:
# MAGIC 1. It stores your Nimble API key in a Databricks secret scope.
# MAGIC 2. It creates one schema for every table in this repository.
# MAGIC 3. It creates the Nimble functions in that schema, for Genie and Agent Bricks.
# MAGIC 4. It tests the Nimble API from this notebook and from your SQL warehouse.
# MAGIC 5. It saves your settings, so the other notebooks run without questions.
# MAGIC
# MAGIC Fill in the widgets at the top, attach serverless compute, and click **Run all**.
# MAGIC You can get a Nimble API key at https://online.nimbleway.com/account-settings/api-keys.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import os, sys
sys.path.insert(0, os.getcwd())
from common import config
from common.nimble import Nimble
from common.bootstrap import warehouse_sql, pick_warehouse
from databricks.sdk import WorkspaceClient

user = spark.sql("SELECT current_user()").first()[0]
saved = config.load(user)
dbutils.widgets.text("catalog", saved["catalog"], "1. Catalog (must exist)")
dbutils.widgets.text("schema", saved["schema"], "2. Schema (created if missing)")
dbutils.widgets.text("nimble_api_key", "", "3. Nimble API key (blank = keep stored key)")
dbutils.widgets.text("secret_scope", saved["secret_scope"], "4. Secret scope")
dbutils.widgets.text("warehouse_id", saved.get("warehouse_id", ""), "5. SQL warehouse id (blank = pick one)")

cfg = dict(saved)
for k in ("catalog", "schema", "secret_scope", "warehouse_id"):
    cfg[k] = dbutils.widgets.get(k).strip()
w = WorkspaceClient()

# COMMAND ----------

# MAGIC %md ## 1. Store the Nimble key in a secret scope

# COMMAND ----------

key = dbutils.widgets.get("nimble_api_key").strip()
scopes = {s.name for s in w.secrets.list_scopes()}
if cfg["secret_scope"] not in scopes:
    w.secrets.create_scope(scope=cfg["secret_scope"])
    print("Created secret scope", cfg["secret_scope"])
if key:
    w.secrets.put_secret(scope=cfg["secret_scope"], key=cfg["secret_key"], string_value=key)
    print("Stored the key. You can clear the widget now.")
try:
    api_key = dbutils.secrets.get(cfg["secret_scope"], cfg["secret_key"])
except Exception:
    raise RuntimeError("No Nimble key stored yet. Paste it in widget 3 and run again.")
print("Key found in scope", cfg["secret_scope"])

# COMMAND ----------

# MAGIC %md ## 2. Create the schema

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{cfg['catalog']}`.`{cfg['schema']}` COMMENT 'Nimble on Databricks: shelf feed, research tables and agent tools. Powered by Nimble.'")
print("Schema ready:", f"{cfg['catalog']}.{cfg['schema']}")

# COMMAND ----------

# MAGIC %md ## 3. Create the Nimble functions
# MAGIC Genie spaces and Agent Bricks agents call these functions as tools. Notebooks call the Nimble API directly.

# COMMAND ----------

cfg["warehouse_id"] = pick_warehouse(w, cfg["warehouse_id"])
print("SQL warehouse:", cfg["warehouse_id"])
text = open("common/sql/functions.sql").read()
for k in ("catalog", "schema"):
    text = text.replace("{" + k + "}", f"`{cfg[k]}`")
text = text.replace("{scope}", cfg["secret_scope"]).replace("{key}", cfg["secret_key"])
blocks = [b.strip() for b in text.split("-- @@")[1:] if b.strip()]
for b in blocks:
    name = b.split("FUNCTION", 1)[1].split("(", 1)[0].strip()
    try:
        spark.sql(b)
    except Exception as e:  # some workspaces only allow Python functions from a SQL warehouse
        warehouse_sql(w, cfg["warehouse_id"], b)
    print("  created", name)

# COMMAND ----------

# MAGIC %md ## 4. Test Nimble from this notebook and from the SQL warehouse

# COMMAND ----------

hits = Nimble(api_key).search("running shoe industry news", max_results=3, focus="news")
print(f"Notebook to Nimble: {len(hits)} search results")
for h in hits:
    print("  ", h.get("title"))
assert hits, "Nimble returned no results. Check the key."

try:
    _, rows = warehouse_sql(w, cfg["warehouse_id"], f"SELECT count(*) FROM `{cfg['catalog']}`.`{cfg['schema']}`.nimble_search('running shoe industry news', 3)")
    n = int(rows[0][0])
except Exception as e:
    n, err = 0, str(e)[:300]
cfg["warehouse_functions_ok"] = n > 0
if n > 0:
    print(f"SQL warehouse to Nimble: {n} results. Genie and Agent Bricks can call Nimble.")
else:
    print("SQL warehouse to Nimble: no results. The notebooks still work.\n"
          "Genie and Agent Bricks need outbound network access from the SQL warehouse:\n"
          "  1. Open Settings > Previews and turn on 'Enable networking for isolated workloads in Serverless SQL Warehouses'.\n"
          "  2. Stop the warehouse, then start it again.\n"
          "  3. Run this notebook again.")

# COMMAND ----------

# MAGIC %md ## 5. Save the settings

# COMMAND ----------

cfg["installed"] = True
print("Settings saved to", config.save(user, cfg))
displayHTML(f"<p>Install complete. Next, open <b>1_data_feed/01_build_shelf_feed</b> and click Run all.</p>")
