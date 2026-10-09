# Nimble on Databricks

This repository installs three working examples of live web data inside a Databricks workspace. Nimble is the web data platform that collects the data. Every example runs on serverless compute and lands its results in Unity Catalog tables.

| Folder | Use case | What lands in your workspace |
|---|---|---|
| `1_data_feed` | A retail pricing feed that you can test against the feed you buy today | The table `shelf_products`, a daily job, a SQL alert and an AI/BI dashboard |
| `2_agentic_research` | Research tasks in plain language, run by an agent | The tables `competitor_earnings` and `product_reviews`, with a source URL on every value, plus a Genie space |
| `3_platform_integration` | One governed Nimble connection for every agent and tool | A Unity Catalog MCP connection, an Agent Bricks agent and audit queries |

The examples use running shoes, with Nike and its competitors on five US retailers. To track other products, change the keyword list, the company list or the watchlist.

## Install

Check these four things first:

- Your workspace needs Unity Catalog, serverless notebooks and a serverless SQL warehouse.
- You need a catalog where you can create a schema.
- You need a Nimble API key. You can create one at https://online.nimbleway.com/account-settings/api-keys.
- Genie and Agent Bricks need the workspace preview **Enable networking for isolated workloads in Serverless SQL Warehouses**. Turn it on under Settings > Previews, then stop and start the warehouse. The notebooks work without it.

Then follow these steps:

1. In your workspace, open **Workspace > Create > Git folder** and paste `https://github.com/amaurynimble/nimble-databricks-use-cases`.
2. Open `00_install`, attach serverless compute, fill in the catalog, the schema name and your Nimble key, and click **Run all**. It takes about two minutes.
3. Open any notebook in the three folders and click **Run all**. Run the notebooks in each folder in number order.

The install stores your key in a Databricks secret scope. It saves your settings to `.nimble_use_cases.json` in your home folder, so the other notebooks need no input.

## 1. Retail pricing feed (`1_data_feed`)

| Notebook | What it does | Time |
|---|---|---|
| `01_build_shelf_feed` | Runs 8 searches on Amazon, Walmart, Target, Foot Locker and ASOS, and appends a dated snapshot to `shelf_products` | 3 min |
| `02_schedule_and_alert` | Creates a daily job, the view `shelf_alerts` and a SQL alert that emails you when the view has rows | 1 min |
| `03_dashboard` | Publishes the AI/BI dashboard **Running shoe shelf** | 1 min |
| `04_compare_with_your_feed` | Compares coverage, price match and freshness with a sample of your current vendor's feed | 1 min |

Each row in `shelf_products` holds the retailer, the search, the rank on the page, the brand, the price, the list price when the item is on sale, the rating, the review count and the sponsored flag. Edit the table `shelf_queries` to change the searches.

## 2. Agentic research (`2_agentic_research`)

A Nimble Web Search Agent takes a task in plain language and researches the live web. It returns rows in a fixed schema. Every value carries the page it came from and a confidence grade.

| Notebook | What it does | Time |
|---|---|---|
| `01_competitor_earnings` | Builds a table of quarterly revenue, growth, gross margin and operating income for 8 companies, from each company's own earnings releases and filings | 5 to 15 min |
| `02_ratings_and_reviews` | Adds rating, review count, price, praise and complaints to each product in the table `product_watchlist` | 10 to 25 min |
| `03_genie_space` | Creates the Genie space **Market research (Nimble)** over the tables and the live Nimble functions, then asks it three questions | 2 min |

The agent specs are in `2_agentic_research/agents/`. The first run creates each agent on your Nimble key. Later runs reuse it.

## 3. Platform integration (`3_platform_integration`)

| Notebook or file | What it does |
|---|---|
| `01_mcp_connection` | Creates the Unity Catalog connection `nimble_mcp` to the Nimble MCP server and lists its 27 tools. MCP (Model Context Protocol) is the standard way AI assistants call outside tools. You can also add Nimble from the Databricks Marketplace. |
| `02_market_analyst_agent` | Builds an Agent Bricks supervisor with the Genie space, the Nimble functions and the MCP connection, then asks it a question that needs both the tables and the live web |
| `03_governance` | Queries `system.access.audit` for every Nimble MCP call and every read of the Nimble key, by user and day, and shows who has access |
| `cursor_mcp.json` | Adds the same Nimble server to Cursor or GitHub Copilot, either through the Databricks proxy or directly |

## What the install creates

The schema holds the tables above and these functions:

| Function | What it returns |
|---|---|
| `nimble_search(query, max_results, focus)` | Live web search results with page content |
| `nimble_retail_search(retailer, keyword)` | The products a shopper sees right now on one retailer |
| `nimble_product_reviews(asin)` | The live Amazon product page for one product, with the review summary |
| `nimble_wsa_start(agent_id, input, ...)` and `nimble_wsa_result_json(agent_id, run_id)` | Starts a Web Search Agent run and reads its rows |

To remove everything, drop the schema, then delete the job, the alert, the dashboard, the Genie space and the Agent Bricks agent.
