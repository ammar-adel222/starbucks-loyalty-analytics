"""Create or refresh the project Metabase dashboard and verify its SQL results."""

import argparse
from decimal import Decimal
import json
import math
import re
import time
import urllib.error
import urllib.request

import psycopg
from psycopg import sql

from import_data import PROJECT_DIR, connection_settings, project_settings


class Metabase:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.session = None

    def request(self, method, path, payload=None):
        headers = {"Content-Type": "application/json"}
        if self.session:
            headers["X-Metabase-Session"] = self.session
        request = urllib.request.Request(self.url + path, method=method, headers=headers,
            data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                content = response.read()
                return json.loads(content) if content else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Metabase {method} {path} returned HTTP {error.code}.") from None

    def login(self, settings):
        for _ in range(60):
            try:
                if self.request("GET", "/api/health").get("status") == "ok":
                    break
            except (RuntimeError, urllib.error.URLError):
                pass
            time.sleep(3)
        else:
            raise RuntimeError("Metabase is still starting. Check docker compose logs metabase.")
        properties = self.request("GET", "/api/session/properties")
        if properties.get("setup-token"):
            session = self.request("POST", "/api/setup", {
                "token": properties["setup-token"],
                "user": {"first_name": "Loyalty", "last_name": "Analyst",
                    "email": settings["METABASE_ADMIN_EMAIL"], "password": settings["METABASE_ADMIN_PASSWORD"]},
                "prefs": {"site_name": "Starbucks loyalty analytics", "site_locale": "en"},
            })
        else:
            session = self.request("POST", "/api/session", {
                "username": settings["METABASE_ADMIN_EMAIL"], "password": settings["METABASE_ADMIN_PASSWORD"],
            })
        self.session = session["id"]


def template_tags(query):
    return sorted(set(re.findall(r"\{\{(\w+)\}\}", query)))


def native_parameters(values):
    """Bind native queries using Metabase's template-tag IDs."""
    return [{"id": "starbucks-" + name, "type": "category",
        "target": ["variable", ["template-tag", name]], "value": value}
        for name, value in values.items()]


def compile_query(query, values):
    """Resolve the project's optional SQL blocks and bind values for direct verification."""
    query = query.replace("%", "%%")
    parameters = []
    def optional(match):
        block = match.group(1)
        if not all(name in values for name in template_tags(block)):
            return ""
        def variable(tag):
            parameters.append(values[tag.group(1)])
            return "%s"
        return re.sub(r"\{\{(\w+)\}\}", variable, block)
    return re.sub(r"\[\[(.*?)\]\]", optional, query, flags=re.DOTALL), parameters


def configure_reader(settings, env_file):
    with psycopg.connect(**connection_settings(env_file)) as connection:
        role = sql.Identifier("metabase_reader")
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname='metabase_reader'").fetchone()
        command = "ALTER ROLE {} LOGIN PASSWORD {}" if exists else "CREATE ROLE {} LOGIN PASSWORD {}"
        connection.execute(sql.SQL(command).format(role, sql.Literal(settings["METABASE_READER_PASSWORD"])))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA loyalty TO {}").format(role))
        connection.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA loyalty TO {}").format(role))
        connection.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA loyalty GRANT SELECT ON TABLES TO {}").format(role))


def provision(api, spec, settings, env_file):
    configure_reader(settings, env_file)
    databases = api.request("GET", "/api/database")["data"]
    database = next((item for item in databases if item["name"] == "Starbucks PostgreSQL"), None)
    database_payload = {"name": "Starbucks PostgreSQL", "engine": "postgres", "is_full_sync": False,
        "details": {"host": "postgres", "port": 5432, "dbname": settings.get("POSTGRES_DB", "starbucks"),
            "user": "metabase_reader", "password": settings["METABASE_READER_PASSWORD"], "ssl": False,
            "schema-filters-type": "inclusion", "schema-filters-patterns": "loyalty"}}
    if database:
        api.request("PUT", f"/api/database/{database['id']}", database_payload)
    else:
        database = api.request("POST", "/api/database", database_payload)

    collections = api.request("GET", "/api/collection")
    collection = next((item for item in collections if item["name"] == spec["collection"]), None)
    if collection is None:
        collection = api.request("POST", "/api/collection", {
            "name": spec["collection"], "description": "Managed by the Starbucks loyalty analytics repository."})
    dashboards = api.request("GET", "/api/dashboard")
    dashboard = next((item for item in dashboards
        if item["name"] == spec["name"] and item.get("collection_id") == collection["id"]), None)
    if dashboard is None:
        dashboard = api.request("POST", "/api/dashboard", {
            "name": spec["name"], "collection_id": collection["id"], "description": spec["description"]})
    dashboard_id = dashboard["id"]
    dashboard = api.request("GET", f"/api/dashboard/{dashboard_id}")
    tab_ids = {tab["name"]: tab["id"] for tab in dashboard.get("tabs", [])}
    tabs = [{"id": tab_ids.get(name, -index-1), "name": name, "position": index}
        for index, name in enumerate(spec["tabs"])]
    tab_ids = {tab["name"]: tab["id"] for tab in tabs}
    existing_cards = [card for card in api.request("GET", "/api/card") if card.get("collection_id") == collection["id"]]
    card_ids = {}
    for item in spec["cards"]:
        query = "\n".join(item["sql"])
        tags = {name: {"id": "starbucks-" + name, "name": name,
            "display-name": name.replace("_", " ").title(), "type": "text", "required": False}
            for name in template_tags(query)}
        description = f"Managed by setup_metabase.py with key {item['key']}."
        existing = next((card for card in existing_cards if card.get("description") == description), None)
        payload = {"name": item["name"], "description": description, "display": item["display"],
            "collection_id": collection["id"], "visualization_settings": item["settings"],
            "dataset_query": {"database": database["id"], "type": "native", "native": {"query": query, "template-tags": tags}}}
        card = api.request("PUT", f"/api/card/{existing['id']}", payload) if existing else api.request("POST", "/api/card", payload)
        card_ids[item["key"]] = card["id"]
        print(f"Configured {item['name']}", flush=True)

    with psycopg.connect(**connection_settings(env_file)) as connection:
        segments = [row[0] for row in connection.execute("SELECT DISTINCT rfm_segment FROM loyalty.customer_rfm_before_offers WHERE full_history_observed ORDER BY rfm_segment")]
    parameters = [
        {"id": "offer_type", "name": "Offer type (offer charts)", "slug": "offer_type", "type": "string/=", "sectionId": "string",
            "isMultiSelect": False, "values_source_type": "static-list", "values_source_config": {"values": ["bogo", "discount", "informational"]}},
        {"id": "rfm_segment", "name": "Pre-offer segment", "slug": "rfm_segment", "type": "string/=", "sectionId": "string",
            "isMultiSelect": False, "values_source_type": "static-list", "values_source_config": {"values": segments}},
    ]
    existing_layout = dashboard.get("dashcards", [])
    layout, next_id = [], -100
    for name, note in spec["notes"].items():
        existing = next((card for card in existing_layout if card.get("card_id") is None
            and card.get("dashboard_tab_id") == tab_ids[name]), None)
        layout.append({"id": existing["id"] if existing else next_id, "card_id": None,
            "dashboard_tab_id": tab_ids[name], "row": 0, "col": 0, "size_x": 24, "size_y": 2,
            "parameter_mappings": [], "visualization_settings": {"virtual_card": {"display": "text", "visualization_settings": {}}, "text": note}})
        next_id -= 1
    for item in spec["cards"]:
        card_id = card_ids[item["key"]]
        existing = next((card for card in existing_layout if card.get("card_id") == card_id), None)
        mappings = [{"parameter_id": name, "card_id": card_id, "target": ["variable", ["template-tag", name]]}
            for name in template_tags("\n".join(item["sql"]))]
        layout.append({"id": existing["id"] if existing else next_id, "card_id": card_id,
            "dashboard_tab_id": tab_ids[item["tab"]], "row": item["row"], "col": item["col"],
            "size_x": item["width"], "size_y": item["height"], "parameter_mappings": mappings, "visualization_settings": {}})
        next_id -= 1
    api.request("PUT", f"/api/dashboard/{dashboard_id}", {"name": spec["name"], "description": spec["description"],
        "width": "full", "parameters": parameters, "dashcards": layout,
        "tabs": [{"id": tab_ids[name], "name": name, "position": index} for index, name in enumerate(spec["tabs"])]})
    saved = api.request("GET", f"/api/dashboard/{dashboard_id}")
    tab_ids = {tab["name"]: tab["id"] for tab in saved["tabs"]}
    if set(tab_ids) != set(spec["tabs"]):
        raise ValueError("Metabase did not retain all dashboard tabs. Rerun provisioning.")
    state = {"url": api.url, "dashboard_id": dashboard_id, "database_id": database["id"],
        "collection_id": collection["id"], "cards": card_ids, "tabs": tab_ids}
    (PROJECT_DIR / ".metabase-state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def verify(api, spec, state, env_file):
    checks = 0
    with psycopg.connect(**connection_settings(env_file)) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        for item in spec["cards"]:
            query = "\n".join(item["sql"])
            tags = template_tags(query)
            samples = [{}]
            if tags:
                samples.append({name: "discount" if name == "offer_type" else "Frequent recent" for name in tags})
            if len(tags) > 1:
                samples += [{name: "discount" if name == "offer_type" else "Frequent recent"} for name in tags]
            for values in samples:
                parameters = native_parameters(values)
                result = api.request("POST", f"/api/card/{state['cards'][item['key']]}/query", {"parameters": parameters, "ignore_cache": True})
                if result.get("status") != "completed":
                    raise ValueError(f"Metabase query failed for {item['key']}.")
                compiled, bound = compile_query(query, values)
                expected = connection.execute(compiled, bound).fetchall()
                actual = result["data"]["rows"]
                if len(actual) != len(expected):
                    raise ValueError(f"Row count mismatch for {item['key']}.")
                for api_row, db_row in zip(actual, expected):
                    if len(api_row) != len(db_row):
                        raise ValueError(f"Column count mismatch for {item['key']}.")
                    for api_value, db_value in zip(api_row, db_row):
                        numeric = isinstance(db_value, (int, float, Decimal)) and db_value is not None
                        equal = math.isclose(float(api_value), float(db_value), rel_tol=0, abs_tol=1e-6) if numeric and api_value is not None else api_value == db_value
                        if not equal:
                            raise ValueError(f"Value mismatch for {item['key']}.")
                checks += 1
            print(f"Verified {item['name']}", flush=True)
    print(f"PASS {checks} unfiltered and filtered Metabase-to-PostgreSQL comparisons.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Execute every card and compare results with PostgreSQL.")
    args = parser.parse_args()
    env_file = PROJECT_DIR / ".env"
    settings = project_settings(env_file)
    for name in ("METABASE_ADMIN_EMAIL", "METABASE_ADMIN_PASSWORD", "METABASE_READER_PASSWORD"):
        if not settings.get(name):
            raise ValueError(f"Set {name} in .env before provisioning Metabase.")
    api = Metabase(f"http://localhost:{settings.get('METABASE_PORT', '3000')}")
    with psycopg.connect(**connection_settings(env_file), autocommit=True) as lock_connection:
        lock_connection.execute("SELECT pg_advisory_lock(hashtext('loyalty_metabase_setup'))")
        api.login(settings)
        spec = json.loads((PROJECT_DIR / "metabase" / "dashboard.json").read_text(encoding="utf-8"))
        state = provision(api, spec, settings, env_file)
        if args.verify:
            verify(api, spec, state, env_file)
    print(f"Dashboard ready at {api.url}/dashboard/{state['dashboard_id']}")
    print("Sign in using METABASE_ADMIN_EMAIL and METABASE_ADMIN_PASSWORD from the local .env file.")


if __name__ == "__main__":
    main()
