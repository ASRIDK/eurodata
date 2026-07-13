import duckdb

from eurodata.reference.countries import COUNTRIES
from eurodata.reference.blocs import BLOCS, MEMBERSHIPS
from eurodata.reference.borders import BORDERS  # noqa: F401 (used by graph build)
from eurodata.reference.catalog import DOMAINS, INDICATORS, SOURCES
from eurodata.reference.events import EVENTS


def seed_events(con: duckdb.DuckDBPyConnection) -> None:
    for e in EVENTS:
        con.execute(
            "INSERT INTO event (code, title, description, event_type, iso3, bloc_code, "
            "start_date, end_date, source, source_url, confidence, tags, affected_domains) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (code) DO NOTHING",
            [e["code"], e["title"], e["description"], e["event_type"], e["iso3"],
             e["bloc_code"], e["start_date"], e["end_date"], e["source"],
             e["source_url"], e["confidence"], e["tags"], e["affected_domains"]],
        )


def seed_all(con: duckdb.DuckDBPyConnection) -> None:
    for i, c in enumerate(COUNTRIES, start=1):
        con.execute(
            "INSERT INTO geography (id, code, level, name, iso2, iso3, "
            "is_transcontinental, is_disputed, note) "
            "VALUES (?, ?, 'country', ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [i, c["iso3"], c["name"], c["iso2"], c["iso3"],
             c["is_transcontinental"], c["is_disputed"], c["note"]],
        )
    for i, b in enumerate(BLOCS, start=1):
        con.execute("INSERT INTO bloc (id, code, name) VALUES (?, ?, ?) "
                    "ON CONFLICT DO NOTHING", [i, b["code"], b["name"]])
    for iso3, code, since, until in MEMBERSHIPS:
        con.execute(
            "INSERT INTO geography_bloc (geography_id, bloc_id, since_year, until_year) "
            "SELECT g.id, b.id, ?, ? FROM geography g, bloc b "
            "WHERE g.iso3 = ? AND b.code = ? ON CONFLICT DO NOTHING",
            [since, until, iso3, code],
        )
    for i, d in enumerate(DOMAINS, start=1):
        con.execute("INSERT INTO domain (id, name, description, color) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT DO NOTHING", [i, d["name"], d["description"], d["color"]])
    domain_ids = {name: did for did, name in con.execute("SELECT id, name FROM domain").fetchall()}
    for i, ind in enumerate(INDICATORS, start=1):
        con.execute(
            "INSERT INTO indicator (id, domain_id, name, unit, api_code, source_priority, "
            "definition, is_proxy, proxy_note, frequency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [i, domain_ids[ind["domain"]], ind["name"], ind["unit"],
             ind["api_code"], ind["source_priority"], ind.get("definition"),
             ind.get("is_proxy", False), ind.get("proxy_note"),
             ind.get("frequency", "annual")],
        )
        # Upsert metadata so databases seeded before these fields existed
        # (or with stale values) pick up the current catalog.
        con.execute(
            "UPDATE indicator SET unit = ?, api_code = ?, definition = ?, "
            "is_proxy = ?, proxy_note = ?, frequency = ? WHERE domain_id = ? AND name = ?",
            [ind["unit"], ind["api_code"], ind.get("definition"),
             ind.get("is_proxy", False), ind.get("proxy_note"),
             ind.get("frequency", "annual"),
             domain_ids[ind["domain"]], ind["name"]],
        )
    for i, s in enumerate(SOURCES, start=1):
        con.execute(
            "INSERT INTO source (id, name, organization, url, api_endpoint, "
            "reliability_score, license, redistributable, update_frequency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [i, s["name"], s["organization"], s["url"], s["api_endpoint"],
             s["reliability_score"], s["license"], s["redistributable"], s["update_frequency"]],
        )
    seed_events(con)
