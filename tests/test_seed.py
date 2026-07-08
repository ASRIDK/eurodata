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
    assert {"EU", "EUROZONE", "SCHENGEN", "EFTA", "EEA"} <= {b["code"] for b in BLOCS}
    assert ("DEU", "EU") in {(m[0], m[1]) for m in MEMBERSHIPS}


def test_borders_symmetry_sample():
    assert ("FRA", "DEU") in BORDERS or ("DEU", "FRA") in BORDERS


def test_catalog_covers_four_domains():
    names = {d["name"] for d in DOMAINS}
    assert names == {"Demographics", "Economy", "Digital & Connectivity", "Energy & Green"}
    assert any(s["name"] == "Eurostat" and s["redistributable"] for s in SOURCES)
    assert all("domain" in ind and "api_code" in ind for ind in INDICATORS)


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
    assert con.execute("SELECT COUNT(*) FROM bloc").fetchone()[0] == 5
    assert con.execute("SELECT COUNT(*) FROM domain").fetchone()[0] == 4
    assert con.execute("SELECT COUNT(*) FROM indicator").fetchone()[0] == 10
    assert con.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 4
    # idempotent
    seed_all(con)
    assert con.execute("SELECT COUNT(*) FROM domain").fetchone()[0] == 4
