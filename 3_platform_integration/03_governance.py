# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 3: see every Nimble call in the audit log
# MAGIC Databricks records each use of Nimble in the system table `system.access.audit`.
# MAGIC This notebook shows three views: MCP tool calls by agents, reads of the Nimble key by notebooks and functions, and who has access.
# MAGIC Reading `system.access.audit` needs a grant from a workspace admin.

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
cfg, nimble = start(spark, dbutils)

# COMMAND ----------

# MAGIC %md ## MCP tool calls by agents, Genie and AI Playground

# COMMAND ----------

display(spark.sql("""
SELECT event_time, user_identity.email AS user, service_name,
       request_params.tool_name AS tool, request_params.json_rpc_method AS method,
       coalesce(request_params.mcp_server_name, request_params.connection_name) AS server,
       response.status_code
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND action_name IN ('mcpToolInvocation', 'mcpCall')
ORDER BY event_time DESC
LIMIT 200
"""))

# COMMAND ----------

# MAGIC %md ## Reads of the Nimble key, by user and day
# MAGIC Each notebook run, function call and job run reads the key once per call. The key itself never appears in plain text.

# COMMAND ----------

display(spark.sql(f"""
SELECT event_date, user_identity.email AS user, count(*) AS key_reads
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND service_name = 'secrets' AND action_name = 'getSecret'
  AND request_params.scope = '{cfg['secret_scope']}'
GROUP BY ALL ORDER BY event_date DESC, key_reads DESC
"""))

# COMMAND ----------

# MAGIC %md ## Who can use Nimble

# COMMAND ----------

display(spark.sql(f"SHOW GRANTS ON FUNCTION `{cfg['catalog']}`.`{cfg['schema']}`.nimble_retail_search"))
if cfg.get("mcp_connection"):
    display(spark.sql(f"SHOW GRANTS ON CONNECTION {cfg['mcp_connection']}"))
