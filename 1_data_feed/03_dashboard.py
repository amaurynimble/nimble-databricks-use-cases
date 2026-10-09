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

board = Dashboard(display_name=NAME, serialized_dashboard=layout, warehouse_id=cfg["warehouse_id"], parent_path=parent)
try:
    d = w.lakeview.create(dashboard=board)
except Exception as e:  # already published once: update it in place
    if "already exists" not in str(e):
        raise
    existing_id = w.workspace.get_status(f"{parent}/{NAME}.lvdash.json").resource_id
    d = w.lakeview.update(dashboard_id=existing_id, dashboard=Dashboard(display_name=NAME, serialized_dashboard=layout, warehouse_id=cfg["warehouse_id"]))
w.lakeview.publish(dashboard_id=d.dashboard_id, embed_credentials=True, warehouse_id=cfg["warehouse_id"])
print("Published dashboard", d.dashboard_id)
displayHTML(f'<a href="/dashboardsv3/{d.dashboard_id}/published">Open the dashboard</a>')
