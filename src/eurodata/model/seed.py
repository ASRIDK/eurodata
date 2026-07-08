import duckdb

from eurodata.reference.countries import COUNTRIES
from eurodata.reference.blocs import BLOCS, MEMBERSHIPS
from eurodata.reference.borders import BORDERS  # noqa: F401 (used by graph build)
from eurodata.reference.catalog import DOMAINS, INDICATORS, SOURCES


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
            "INSERT INTO indicator (id, domain_id, name, unit, api_code, source_priority) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [i, domain_ids[ind["domain"]], ind["name"], ind["unit"],
             ind["api_code"], ind["source_priority"]],
        )
    for i, s in enumerate(SOURCES, start=1):
        con.execute(
            "INSERT INTO source (id, name, organization, url, api_endpoint, "
            "reliability_score, license, redistributable, update_frequency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [i, s["name"], s["organization"], s["url"], s["api_endpoint"],
             s["reliability_score"], s["license"], s["redistributable"], s["update_frequency"]],
        )
