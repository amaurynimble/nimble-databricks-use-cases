# Databricks notebook source
# MAGIC %md
# MAGIC # Use case 3: a market analyst agent in Agent Bricks
# MAGIC This notebook builds the Agent Bricks supervisor **Market analyst (Nimble)**. A supervisor is an agent that picks the right tool for each part of a question.
# MAGIC It has these tools:
# MAGIC
# MAGIC - The Genie space from `2_agentic_research/03_genie_space`, for the tables: earnings, reviews and the shelf feed.
# MAGIC - The Nimble functions, for live retailer prices, live Amazon reviews and web search.
# MAGIC - The `nimble_mcp` connection from `01_mcp_connection`, for page extraction, crawling and research.
# MAGIC
# MAGIC The agent gets a serving endpoint, so apps, notebooks, Slack bots and Databricks One can call it.
# MAGIC Run `2_agentic_research/03_genie_space` and `01_mcp_connection` first.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import os, sys, time
sys.path.insert(0, os.path.abspath(".."))
from common.bootstrap import start
from common import config
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.supervisoragents import Example, GenieSpace, SupervisorAgent, Tool, UcConnection, UcFunction
cfg, nimble = start(spark, dbutils)
w = WorkspaceClient()
fq = lambda n: f"{cfg['catalog']}.{cfg['schema']}.{n}"
assert cfg.get("genie_space_id"), "Run 2_agentic_research/03_genie_space first."
assert cfg.get("warehouse_functions_ok"), "The SQL warehouse can't reach Nimble yet. See step 4 of 00_install."

NAME = "Market analyst (Nimble)"
INSTRUCTIONS = """You answer questions about competitors and the retail shelf. Show your numbers, name your sources and say when something is an estimate.
1. Start with the Genie tool for anything already collected: quarterly earnings, product ratings and reviews, and the daily retail shelf feed.
2. Use the live tools when the question needs something the tables don't have:
   - nimble_retail_search(retailer, keyword): what a shopper sees right now on amazon, walmart, target, footlocker or asos. One retailer per call.
   - nimble_product_reviews(asin): the live Amazon product page for one ASIN. Find the ASIN with nimble_retail_search('amazon', ...) first.
   - nimble_search(query, max_results, focus): web search. Use focus 'news' for announcements.
   - nimble_mcp: page extraction, site maps, crawling and deep research, when the functions above are not enough.
3. Revenue is in each company's reporting currency. Compare growth and margins, not raw revenue.
4. Every number from the web gets a URL. Every number from a table gets the table name.
5. If a live tool returns nothing, try one other retailer or keyword before you conclude."""

TOOLS = [
    ("research_tables", Tool(tool_type="genie_space", genie_space=GenieSpace(id=cfg["genie_space_id"]),
        description="Collected market data: competitor quarterly earnings, product ratings and reviews, and the daily retail shelf feed (price, list price, rating, sponsored slots on five US retailers).")),
    ("nimble_retail_search", Tool(tool_type="uc_function", uc_function=UcFunction(name=fq("nimble_retail_search")),
        description="LIVE retailer search: products a shopper sees now for a keyword on amazon, walmart, target, footlocker or asos, with price, list price when on sale, rating, reviews, sponsored flag and URL.")),
    ("nimble_product_reviews", Tool(tool_type="uc_function", uc_function=UcFunction(name=fq("nimble_product_reviews")),
        description="LIVE Amazon product page for one ASIN: price, rating, review count, five-star share, praise and complaint themes, AI review summary.")),
    ("nimble_search", Tool(tool_type="uc_function", uc_function=UcFunction(name=fq("nimble_search")),
        description="Live web search with page content. Use focus 'news' for announcements and earnings news.")),
]
if cfg.get("mcp_connection"):
    TOOLS.append(("nimble_mcp", Tool(tool_type="uc_connection", uc_connection=UcConnection(name=cfg["mcp_connection"]),
        description="Nimble MCP server: page extraction, site maps, crawling and Web Search Agents for cited research.")))
EXAMPLES = [Example(
    question="Which competitor has the highest gross margin in its latest quarter, and is it discounting running shoes on Amazon right now?",
    guidelines=["Read the latest gross margins from the Genie tool and name the quarter.",
                "Call nimble_retail_search('amazon', '<brand> running shoes') for that brand.",
                "Report the share of items on sale and the average discount, with product URLs."])]

# COMMAND ----------

agent = next((a for a in w.supervisor_agents.list_supervisor_agents() if a.display_name == NAME), None)
if not agent:
    agent = w.supervisor_agents.create_supervisor_agent(SupervisorAgent(
        display_name=NAME, instructions=INSTRUCTIONS,
        description="Answers market questions from the research tables first, then from the live web through Nimble."))
parent = agent.name
have = {t.tool_id or (t.name or "").split("/")[-1] for t in w.supervisor_agents.list_tools(parent)}
for tool_id, tool in TOOLS:
    if tool_id not in have:
        w.supervisor_agents.create_tool(parent=parent, tool=tool, tool_id=tool_id)
        print("added tool", tool_id)
if not list(w.supervisor_agents.list_examples(parent)):
    for ex in EXAMPLES:
        w.supervisor_agents.create_example(parent=parent, example=ex)
agent = w.supervisor_agents.get_supervisor_agent(parent)
cfg["supervisor_endpoint"] = agent.endpoint_name
config.save(cfg["user"], {k: v for k, v in cfg.items() if k != "user"})
print("Supervisor", parent, "endpoint", agent.endpoint_name)

# COMMAND ----------

# MAGIC %md ## Ask the agent one question
# MAGIC The new endpoint can take a few minutes to start. The answer itself takes about one minute.

# COMMAND ----------

import requests
endpoint = cfg["supervisor_endpoint"]
for _ in range(60):
    state = w.serving_endpoints.get(endpoint).state
    if state and str(state.ready).endswith("READY") and not str(state.ready).endswith("NOT_READY"):
        break
    time.sleep(20)

QUESTION = EXAMPLES[0].question
t0 = time.time()
r = requests.post(f"{w.config.host}/serving-endpoints/{endpoint}/invocations", headers=w.config.authenticate(),
                  json={"input": [{"role": "user", "content": QUESTION}]}, timeout=900)
r.raise_for_status()
out = r.json().get("output", [])
calls = [o.get("name") for o in out if o.get("type") == "function_call"]
answer = [c.get("text") for o in out if o.get("type") == "message" for c in o.get("content", []) if c.get("text")]
print(f"Q: {QUESTION}\nTools used: {calls}\nTime: {time.time() - t0:.0f} s\n")
print(answer[-1] if answer else r.text[:3000])
