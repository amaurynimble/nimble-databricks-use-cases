# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 1: publish a dashboard on the feed
# MAGIC This notebook publishes the AI/BI dashboard **Running shoe shelf** on the `shelf_products` table.
# MAGIC The dashboard compares brands across retailers: price, share on sale, discount depth and sponsored slots.
# MAGIC It also shows the price trend as the daily job adds snapshots.
# MAGIC The layout lives in `shelf_dashboard.lvdash.json`. Edit it in the dashboard editor after you publish.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import json, os, sys
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import Dashboard

cfg, nimble = start(spark, dbutils)
w = WorkspaceClient()

layout = open("shelf_dashboard.lvdash.json").read()
layout = layout.replace("__CATALOG__", f"`{cfg['catalog']}`").replace("__SCHEMA__", f"`{cfg['schema']}`")
NAME = "Running shoe shelf"
parent = f"/Users/{cfg['user']}"

existing = next((d for d in w.lakeview.list() if d.display_name == NAME and (d.path or "").startswith(parent)), None)
board = Dashboard(display_name=NAME, serialized_dashboard=layout, warehouse_id=cfg["warehouse_id"], parent_path=parent)
if existing:
    d = w.lakeview.update(dashboard_id=existing.dashboard_id, dashboard=board)
else:
    d = w.lakeview.create(dashboard=board)
w.lakeview.publish(dashboard_id=d.dashboard_id, embed_credentials=True, warehouse_id=cfg["warehouse_id"])
print("Published dashboard", d.dashboard_id)
displayHTML(f'<a href="/dashboardsv3/{d.dashboard_id}/published">Open the dashboard</a>')
