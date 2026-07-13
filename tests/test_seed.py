from eurodata.reference.countries import COUNTRIES
from eurodata.reference.blocs import BLOCS, MEMBERSHIPS
from eurodata.reference.borders import BORDERS
from eurodata.reference.catalog import DOMAINS, INDICATORS, SOURCES


def test_country_list_shape():
    assert len(COUNTRIES) >= 40
    codes = {c["iso3"] for c in COUNTRIES}
    assert {"DEU", "FRA", "RUS", "TUR", "XKX"} <= codes
    rus = next(c for c in COUNTRIES if c["iso3"] == "RUS")
    assert rus["is_transcontinental"] is True
    xkx = next(c for c in COUNTRIES if c["iso3"] == "XKX")
    assert xkx["is_disputed"] is True


def test_blocs_and_memberships():
    assert {"EU", "EUROZONE", "SCHENGEN", "EFTA", "EEA", "NATO"} <= {b["code"] for b in BLOCS}
    pairs = {(m[0], m[1]) for m in MEMBERSHIPS}
    assert ("DEU", "EU") in pairs
    # Regression: Eurozone/Schengen were nearly empty in v1 seed data.
    current = [(m[0], m[1]) for m in MEMBERSHIPS if m[3] is None]
    assert len([p for p in current if p[1] == "EUROZONE"]) >= 20
    assert len([p for p in current if p[1] == "SCHENGEN"]) >= 25
    assert len([p for p in current if p[1] == "EU"]) == 27
    assert ("GBR", "EU", 1973, 2020) in set(MEMBERSHIPS)


def test_borders_symmetry_sample():
    assert ("FRA", "DEU") in BORDERS or ("DEU", "FRA") in BORDERS


def test_catalog_covers_domains():
    names = {d["name"] for d in DOMAINS}
    assert {"Demographics", "Economy", "Digital & Connectivity", "Energy & Green",
            "AI & Technology", "Governance & Geopolitics",
            "Startups & Business"} == names
    assert any(s["name"] == "Eurostat" and s["redistributable"] for s in SOURCES)
    assert all("domain" in ind and "api_code" in ind for ind in INDICATORS)
    # every proxy indicator must say what it proxies
    for ind in INDICATORS:
        if ind.get("is_proxy"):
            assert ind.get("proxy_note"), f"{ind['name']} is a proxy without a note"


import duckdb
from eurodata.db import init_schema
from eurodata.model.seed import seed_all


def test_seed_all_populates_tables():
    con = duckdb.connect(":memory:")
    for seq in ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    init_schema(con)
    seed_all(con)
    assert con.execute("SELECT COUNT(*) FROM geography").fetchone()[0] >= 40
    assert con.execute("SELECT COUNT(*) FROM bloc").fetchone()[0] == 6
    assert con.execute("SELECT COUNT(*) FROM domain").fetchone()[0] == 7
    assert con.execute("SELECT COUNT(*) FROM indicator").fetchone()[0] == 32
    assert con.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 5
    assert con.execute("SELECT COUNT(*) FROM event").fetchone()[0] >= 40
    # idempotent
    seed_all(con)
    assert con.execute("SELECT COUNT(*) FROM domain").fetchone()[0] == 7
    assert con.execute("SELECT COUNT(*) FROM event").fetchone()[0] >= 40
