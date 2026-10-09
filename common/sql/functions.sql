-- Nimble functions in Unity Catalog. 00_install replaces {catalog}, {schema}, {scope} and {key},
-- then runs each marked block as one statement.
-- Genie spaces and Agent Bricks agents call these functions as tools. They run on a SQL warehouse,
-- which needs the workspace preview "Enable networking for isolated workloads in Serverless SQL Warehouses".
-- Every public function returns plain SQL types (no VARIANT), because Agent Bricks tools reject VARIANT.

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}._nimble_search(query STRING, max_results INT, focus STRING, api_key STRING)
RETURNS TABLE(title STRING, description STRING, url STRING, content STRING)
LANGUAGE PYTHON
HANDLER 'Handler'
COMMENT 'Internal. Call nimble_search().'
AS $$
class Handler:
    def eval(self, query, max_results, focus, api_key):
        import requests
        body = {"query": query, "max_results": max_results or 5, "search_depth": "lite", "country": "US", "locale": "en"}
        if focus:
            body["focus"] = focus
        headers = {"Authorization": "Bearer " + (api_key or ""), "Content-Type": "application/json",
                   "X-Client-Source": "nimble-databricks-use-cases"}
        try:
            r = requests.post("https://sdk.nimbleway.com/v1/search", json=body, headers=headers, timeout=60)
            data = r.json() if r.status_code < 300 else {}
        except Exception:
            data = {}
        for x in data.get("results") or []:
            yield (x.get("title"), x.get("description"), x.get("url"), x.get("content"))
$$

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}.nimble_search(
    query       STRING COMMENT 'Plain-language search query, e.g. "On Holding quarterly results".',
    max_results INT    DEFAULT 5    COMMENT 'Number of results, 1 to 20.',
    focus       STRING DEFAULT NULL COMMENT 'Optional: general, news, shopping.'
)
RETURNS TABLE(title STRING, description STRING, url STRING, content STRING)
COMMENT 'Live web search through Nimble. Returns title, description, URL and page content for each result. Use focus news for announcements and earnings news.'
RETURN SELECT * FROM {catalog}.{schema}._nimble_search(query, max_results, focus, secret('{scope}', '{key}'))

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}._nimble_template_run(template STRING, params_json STRING, api_key STRING)
RETURNS TABLE(status STRING, item_json STRING)
LANGUAGE PYTHON
HANDLER 'Handler'
COMMENT 'Internal. Runs one Nimble Extraction Template and yields one row per parsed item.'
AS $$
class Handler:
    def eval(self, template, params_json, api_key):
        import json
        import requests
        headers = {"Authorization": "Bearer " + (api_key or ""), "Content-Type": "application/json",
                   "X-Client-Source": "nimble-databricks-use-cases"}
        body = {"agent": template, "params": json.loads(params_json or "{}"), "localization": False}
        try:
            r = requests.post("https://sdk.nimbleway.com/v1/agents/run", json=body, headers=headers, timeout=120)
            d = r.json() if r.status_code < 300 else {}
        except Exception:
            d = {}
        parsing = (d.get("data") or {}).get("parsing")
        if isinstance(parsing, dict):
            items = next((parsing[k] for k in ("entities", "products", "results", "items") if isinstance(parsing.get(k), list)), [parsing])
        else:
            items = parsing or []
        for it in items:
            yield (d.get("status"), json.dumps(it))
$$

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}.nimble_retail_search(
    retailer STRING COMMENT 'One of: amazon, walmart, target, footlocker, asos.',
    keyword  STRING COMMENT 'Search term as a shopper types it, e.g. "pegasus 41" or "puma running shoes".'
)
RETURNS TABLE(retailer STRING, position INT, product_name STRING, brand STRING, price DOUBLE, list_price DOUBLE,
              rating DOUBLE, review_count INT, sponsored BOOLEAN, product_id STRING, product_url STRING)
COMMENT 'LIVE retailer search through Nimble: the products a shopper sees right now for a keyword on Amazon, Walmart, Target, Foot Locker or ASOS, with price, list price when discounted, rating, review count, sponsored flag and URL. Takes 5 to 40 seconds.'
RETURN
SELECT retailer,
  try_cast(get_json_object(item_json, '$.position') AS INT),
  get_json_object(item_json, '$.product_name'),
  get_json_object(item_json, '$.product_brand'),
  try_cast(regexp_replace(coalesce(get_json_object(item_json, '$.price'), get_json_object(item_json, '$.product_price'), get_json_object(item_json, '$.price_current')), '[^0-9.]', '') AS DOUBLE),
  try_cast(regexp_replace(coalesce(get_json_object(item_json, '$.original_price'), get_json_object(item_json, '$.product_price_original')), '[^0-9.]', '') AS DOUBLE),
  try_cast(regexp_replace(coalesce(get_json_object(item_json, '$.rating'), get_json_object(item_json, '$.product_rating')), '[^0-9.]', '') AS DOUBLE),
  try_cast(regexp_replace(coalesce(get_json_object(item_json, '$.review_count'), get_json_object(item_json, '$.product_reviews_count')), '[^0-9]', '') AS INT),
  try_cast(coalesce(get_json_object(item_json, '$.sponsored'), get_json_object(item_json, '$.is_sponsored'), get_json_object(item_json, '$.is_promotion')) AS BOOLEAN),
  coalesce(get_json_object(item_json, '$.asin'), get_json_object(item_json, '$.tcin'), get_json_object(item_json, '$.product_id')),
  coalesce(get_json_object(item_json, '$.product_url'),
           CASE WHEN lower(retailer) = 'footlocker' THEN concat('https://www.footlocker.com/product/~/', get_json_object(item_json, '$.product_id'), '.html') END)
FROM {catalog}.{schema}._nimble_template_run(
       concat(lower(retailer), '_serp'),
       CASE WHEN lower(retailer) = 'footlocker' THEN to_json(named_struct('keywords', keyword)) ELSE to_json(named_struct('keyword', keyword)) END,
       secret('{scope}', '{key}'))

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}.nimble_product_reviews(
    asin STRING COMMENT 'Amazon ASIN of the product. Find it with nimble_retail_search(''amazon'', ...).'
)
RETURNS TABLE(asin STRING, product_title STRING, price DOUBLE, rating DOUBLE, review_count INT, five_star_pct STRING,
              positive_mentions STRING, neutral_mentions STRING, review_summary STRING, product_url STRING)
COMMENT 'LIVE Amazon product page through Nimble: price, star rating, review count, five-star share, the themes reviewers praise or question, and the AI review summary for one ASIN.'
RETURN
SELECT get_json_object(item_json, '$.asin'),
  get_json_object(item_json, '$.product_title'),
  try_cast(get_json_object(item_json, '$.web_price') AS DOUBLE),
  try_cast(get_json_object(item_json, '$.average_of_reviews') AS DOUBLE),
  try_cast(get_json_object(item_json, '$.number_of_reviews') AS INT),
  get_json_object(item_json, '$.reviews_statistics_percentage_five_to_zero.5_star'),
  array_join(from_json(get_json_object(item_json, '$.review_mentions_with_positive_sentiment'), 'ARRAY<STRING>'), ', '),
  array_join(from_json(get_json_object(item_json, '$.review_mentions_with_neutral_sentiment'), 'ARRAY<STRING>'), ', '),
  get_json_object(item_json, '$.reviews_ai_summary'),
  get_json_object(item_json, '$.product_url')
FROM {catalog}.{schema}._nimble_template_run('amazon_pdp', to_json(named_struct('asin', asin)), secret('{scope}', '{key}'))

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}._nimble_wsa_start(agent_id STRING, input STRING, input_data_json STRING, effort STRING, api_key STRING)
RETURNS TABLE(run_id STRING, status STRING, error STRING)
LANGUAGE PYTHON
HANDLER 'Handler'
COMMENT 'Internal. Call nimble_wsa_start().'
AS $$
class Handler:
    def eval(self, agent_id, input, input_data_json, effort, api_key):
        import json
        import requests
        body = {"input": input}
        if effort:
            body["effort"] = effort
        if input_data_json:
            body["input_data"] = json.loads(input_data_json)
        headers = {"Authorization": "Bearer " + (api_key or ""), "Content-Type": "application/json",
                   "X-Client-Source": "nimble-databricks-use-cases"}
        try:
            r = requests.post("https://sdk.nimbleway.com/v2/agents/%s/runs" % agent_id, json=body, headers=headers, timeout=60)
            d = r.json()
        except Exception as e:
            yield (None, "error", str(e)[:500])
            return
        if r.status_code >= 300:
            yield (None, "http_%d" % r.status_code, json.dumps(d)[:500])
            return
        yield (d.get("id"), d.get("status"), None)
$$

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}.nimble_wsa_start(
    agent_id        STRING COMMENT 'Web Search Agent id (starts with wsa_).',
    input           STRING COMMENT 'The research task in plain language.',
    input_data_json STRING DEFAULT NULL COMMENT 'Optional JSON array of rows to enrich.',
    effort          STRING DEFAULT NULL COMMENT 'Optional: medium (1 to 3 min), high (5 to 15 min), x-high (15 to 30 min).'
)
RETURNS TABLE(run_id STRING, status STRING, error STRING)
COMMENT 'Starts a Nimble Web Search Agent run and returns its run_id at once. The agent researches the live web and returns structured rows with a source URL and a confidence grade for each value. Read the output later with nimble_wsa_result_json.'
RETURN SELECT * FROM {catalog}.{schema}._nimble_wsa_start(agent_id, input, input_data_json, effort, secret('{scope}', '{key}'))

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}._nimble_wsa_result(agent_id STRING, run_id STRING, api_key STRING)
RETURNS TABLE(run_id STRING, status STRING, confidence STRING, item_index INT, item_json STRING, source_urls STRING)
LANGUAGE PYTHON
HANDLER 'Handler'
COMMENT 'Internal. Call nimble_wsa_result_json().'
AS $$
class Handler:
    def eval(self, agent_id, run_id, api_key):
        import json
        import requests
        headers = {"Authorization": "Bearer " + (api_key or ""), "Content-Type": "application/json",
                   "X-Client-Source": "nimble-databricks-use-cases"}
        base = "https://sdk.nimbleway.com/v2/agents/%s/runs/%s" % (agent_id, run_id)
        try:
            status = requests.get(base, headers=headers, timeout=30).json().get("status")
        except Exception:
            status = "error"
        if status != "completed":
            yield (run_id, status, None, None, None, None)
            return
        out = (requests.get(base + "/result", headers=headers, timeout=60).json() or {}).get("output") or {}
        trust = out.get("trust") or {}
        claims = trust.get("claims") or []
        content = out.get("content")
        rows = content if isinstance(content, list) else None
        if isinstance(content, dict):
            rows = next((v for v in content.values() if isinstance(v, list)), [content])
        for i, row in enumerate(rows or []):
            prefix = "$[%d]" % i
            urls = []
            for c in claims:
                p = str(c.get("path", ""))
                if p == prefix or p.startswith(prefix + "."):
                    for cit in c.get("citations") or []:
                        if cit.get("url") and cit["url"] not in urls:
                            urls.append(cit["url"])
            yield (run_id, status, trust.get("confidence"), i, json.dumps(row), json.dumps(urls))
$$

-- @@
CREATE OR REPLACE FUNCTION {catalog}.{schema}.nimble_wsa_result_json(
    agent_id STRING COMMENT 'Web Search Agent id the run belongs to.',
    run_id   STRING COMMENT 'Run id returned by nimble_wsa_start().'
)
RETURNS TABLE(run_id STRING, status STRING, confidence STRING, item_index INT, item_json STRING, source_urls STRING)
COMMENT 'Reads a Nimble Web Search Agent run: one row per output item as a JSON string, with the run confidence and the citation URLs. If the run is still going, returns one status row.'
RETURN SELECT * FROM {catalog}.{schema}._nimble_wsa_result(agent_id, run_id, secret('{scope}', '{key}'))
