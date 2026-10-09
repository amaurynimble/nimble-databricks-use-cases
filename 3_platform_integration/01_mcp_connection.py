# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 3: connect Nimble to every agent in the workspace
# MAGIC MCP (Model Context Protocol) is the standard way AI assistants call outside tools.
# MAGIC Nimble runs an MCP server with web search, page extraction, site mapping, crawling and Web Search Agents.
# MAGIC Unity Catalog holds the connection to it, and access follows Unity Catalog grants.
# MAGIC Genie, Databricks One, AI Playground and Agent Bricks can then all use the same governed connection.
# MAGIC
# MAGIC There are two ways to add it:
# MAGIC - **From the Databricks Marketplace.** Open the listing **Nimble MCP: Agentic Web Search Platform**, click **Get instantly**, and pick a catalog and schema. Databricks creates the MCP server for you.
# MAGIC - **From this notebook.** The next cell creates the Unity Catalog connection `nimble_mcp` with the key you stored in `00_install`.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import os, sys
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
from common import config
from databricks.sdk import WorkspaceClient
cfg, nimble = start(spark, dbutils)
w = WorkspaceClient()
CONNECTION = "nimble_mcp"

# COMMAND ----------

existing = {c.name for c in w.connections.list()}
if CONNECTION in existing:
    print(f"Connection {CONNECTION} already exists")
else:
    spark.sql(f"""
    CREATE CONNECTION {CONNECTION} TYPE HTTP
    OPTIONS (
      host 'https://mcp.nimbleway.com',
      port '443',
      base_path '/mcp',
      bearer_token secret('{cfg['secret_scope']}', '{cfg['secret_key']}'),
      is_mcp_connection 'true'
    )
    COMMENT 'Nimble MCP server: live web search, extraction, crawling and Web Search Agents. Powered by Nimble.'
    """)
    print(f"Created connection {CONNECTION}")

# COMMAND ----------

# MAGIC %md ## List the Nimble tools through the Databricks MCP proxy
# MAGIC Every call goes through Databricks at `/api/2.0/mcp/external/nimble_mcp`. Databricks checks the caller's grants and writes each call to the audit log.

# COMMAND ----------

resp = w.api_client.do("POST", f"/api/2.0/mcp/external/{CONNECTION}",
                       body={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                       headers={"Accept": "application/json, text/event-stream"})
tools = resp["result"]["tools"]
print(f"{len(tools)} Nimble tools available to agents in this workspace:")
for t in tools:
    print(f"  {t['name']:36s} {t.get('title') or ''}")

# COMMAND ----------

# MAGIC %md ## Call one tool the way an agent does

# COMMAND ----------

resp = w.api_client.do("POST", f"/api/2.0/mcp/external/{CONNECTION}",
                       body={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                             "params": {"name": "nimble_search", "arguments": {"query": "running shoe launches this month", "max_results": 3}}},
                       headers={"Accept": "application/json, text/event-stream"})
for part in resp["result"]["content"]:
    print(part.get("text", "")[:1500])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Who can use it
# MAGIC Only the owner can use the connection at first. To give a team access, run a grant like this one:
# MAGIC ```sql
# MAGIC GRANT USE CONNECTION ON CONNECTION nimble_mcp TO `ai-team`;
# MAGIC ```
# MAGIC To try it in Databricks One or AI Playground, add **nimble_mcp** under Tools, then ask a question that needs the live web.
# MAGIC To use the same server in Cursor or GitHub Copilot, see `cursor_mcp.json` in this folder.

# COMMAND ----------

cfg["mcp_connection"] = CONNECTION
config.save(cfg["user"], {k: v for k, v in cfg.items() if k != "user"})
