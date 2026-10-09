"""Shared start-up for the use-case notebooks: settings, Nimble client and a SQL warehouse helper."""
import time

from . import config
from .nimble import Nimble


def start(spark, dbutils):
    user = spark.sql("SELECT current_user()").first()[0]
    cfg = config.load(user)
    if not cfg.get("installed"):
        raise RuntimeError("Run 00_install first. It stores your Nimble key and creates the schema.")
    cfg["user"] = user
    client = Nimble(dbutils.secrets.get(cfg["secret_scope"], cfg["secret_key"]))
    spark.sql(f"USE CATALOG `{cfg['catalog']}`")
    spark.sql(f"USE SCHEMA `{cfg['schema']}`")
    print(f"Using {cfg['catalog']}.{cfg['schema']} as {user}")
    return cfg, client


def warehouse_sql(w, warehouse_id, statement, timeout_s=600):
    """Run one statement on a SQL warehouse and return (columns, rows). Used to test the Nimble functions
    the way Genie and Agent Bricks call them."""
    from databricks.sdk.service.sql import StatementState
    r = w.statement_execution.execute_statement(warehouse_id=warehouse_id, statement=statement, wait_timeout="50s")
    t0 = time.time()
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING) and time.time() - t0 < timeout_s:
        time.sleep(5)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"{r.status.state}: {r.status.error.message if r.status.error else ''}")
    cols = [c.name for c in r.manifest.schema.columns] if r.manifest and r.manifest.schema else []
    rows = (r.result.data_array or []) if r.result else []
    return cols, rows


def pick_warehouse(w, preferred=""):
    if preferred:
        return preferred
    whs = list(w.warehouses.list())
    whs.sort(key=lambda x: (not x.enable_serverless_compute, str(x.state) != "State.RUNNING"))
    if not whs:
        raise RuntimeError("No SQL warehouse found. Create a serverless SQL warehouse, then run again.")
    return whs[0].id
