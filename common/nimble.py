"""Small Nimble API client used by every notebook in this repository.

Three Nimble products are used:
  - Search: POST /v1/search, live web search results.
  - Extraction Templates: POST /v1/agents/run, one retailer page in, structured rows out.
  - Web Search Agents: /v2/agents, research tasks in plain language with cited, graded output.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://sdk.nimbleway.com"
CLIENT_SOURCE = "nimble-databricks-use-cases"


class Nimble:
    def __init__(self, api_key):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Client-Source": CLIENT_SOURCE,
        }

    def _post(self, path, body, timeout=120):
        r = requests.post(BASE + path, headers=self.headers, json=body, timeout=timeout)
        if r.status_code >= 300:
            raise RuntimeError(f"Nimble {path} returned {r.status_code}: {r.text[:500]}")
        return r.json()

    def _get(self, path, timeout=60):
        r = requests.get(BASE + path, headers=self.headers, timeout=timeout)
        if r.status_code >= 300:
            raise RuntimeError(f"Nimble {path} returned {r.status_code}: {r.text[:500]}")
        return r.json()

    # Search -------------------------------------------------------------------------------------
    def search(self, query, max_results=5, focus=None, search_depth="lite", country="US"):
        body = {"query": query, "max_results": max_results, "search_depth": search_depth, "country": country, "locale": "en"}
        if focus:
            body["focus"] = focus
        return self._post("/v1/search", body, timeout=60).get("results") or []

    # Extraction Templates ----------------------------------------------------------------------
    def template_run(self, template, params, localization=False, retries=1):
        """Run one Extraction Template (for example amazon_serp). Returns the list of parsed items."""
        body = {"agent": template, "params": params, "localization": localization}
        last = None
        for attempt in range(retries + 1):
            try:
                d = self._post("/v1/agents/run", body, timeout=120)
                parsing = (d.get("data") or {}).get("parsing")
                if isinstance(parsing, dict):
                    for key in ("entities", "products", "results", "items"):
                        if isinstance(parsing.get(key), list):
                            return parsing[key]
                    return [parsing]
                return parsing or []
            except Exception as e:  # retailer timeouts are common; retry once
                last = e
                time.sleep(3)
        raise last

    def template_run_many(self, jobs, workers=8):
        """jobs: list of dicts with template, params and any extra keys. Returns (job, items, error) tuples."""
        def one(job):
            try:
                return job, self.template_run(job["template"], job["params"], job.get("localization", False)), None
            except Exception as e:
                return job, [], str(e)[:300]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, jobs))

    # Web Search Agents -------------------------------------------------------------------------
    def wsa_find(self, display_name):
        """Return the id of an agent on this key with this display name, or None."""
        try:
            d = self._get("/v2/agents?limit=200")
        except Exception:
            return None
        items = d.get("data") or d.get("agents") or d.get("items") or (d if isinstance(d, list) else [])
        for a in items:
            if a.get("display_name") == display_name:
                return a.get("id")
        return None

    def wsa_create(self, spec):
        """Create a Web Search Agent from a spec, or reuse the one with the same display name."""
        existing = self.wsa_find(spec["display_name"])
        if existing:
            return existing
        return self._post("/v2/agents", spec, timeout=60)["id"]

    def wsa_start(self, agent_id, input, input_data=None, effort=None):
        body = {"input": input}
        if input_data is not None:
            body["input_data"] = input_data
        if effort:
            body["effort"] = effort
        return self._post(f"/v2/agents/{agent_id}/runs", body, timeout=60)["id"]

    def wsa_status(self, agent_id, run_id):
        return self._get(f"/v2/agents/{agent_id}/runs/{run_id}", timeout=30).get("status")

    def wsa_wait(self, agent_id, run_id, every=30, max_minutes=45):
        t0 = time.time()
        while True:
            status = self.wsa_status(agent_id, run_id)
            print(f"  {int(time.time() - t0):>5}s  {status}")
            if status in ("completed", "failed", "cancelled"):
                return status
            if time.time() - t0 > max_minutes * 60:
                return status
            time.sleep(every)

    def wsa_result(self, agent_id, run_id):
        """Return (rows, run_confidence). Each row carries its own source URLs and claim grades."""
        d = self._get(f"/v2/agents/{agent_id}/runs/{run_id}/result", timeout=120)
        out = d.get("output") or {}
        trust = out.get("trust") or {}
        claims = trust.get("claims") or []
        content = out.get("content")
        rows = content if isinstance(content, list) else None
        if isinstance(content, dict):
            rows = next((v for v in content.values() if isinstance(v, list)), [content])
        rows = rows or []
        enriched = []
        for i, row in enumerate(rows):
            prefix = f"$[{i}]"
            mine = [c for c in claims if str(c.get("path", "")).startswith(prefix + ".") or c.get("path") == prefix]
            urls = []
            for c in mine:
                for cit in c.get("citations") or []:
                    if cit.get("url") and cit["url"] not in urls:
                        urls.append(cit["url"])
            grades = [c.get("confidence") for c in mine if c.get("confidence")]
            row = dict(row)
            row["_source_urls"] = urls
            row["_claims_json"] = json.dumps(mine)
            row["_high_confidence_share"] = round(grades.count("high") / len(grades), 2) if grades else None
            enriched.append(row)
        return enriched, trust.get("confidence")
