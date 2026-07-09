"""Read-only smoke test against the bundled database, if present."""
import pathlib

import pytest

from eurodata.api import EuroData

_DB = pathlib.Path(__file__).resolve().parent.parent / "data" / "eurodata.duckdb"


@pytest.mark.skipif(not _DB.exists(), reason="bundled DB not built")
def test_real_db_opens_and_has_core_coverage():
    db = EuroData(str(_DB), read_only=True)
    try:
        cov = db.coverage()
        assert len(cov) >= 26
        populated = cov[cov["rows"] > 0]
        assert len(populated) >= 20
        assert not db.events().empty
        lo, hi = db.years()
        assert lo <= 2000 and hi >= 2024
        s = db.series(country="FRA", indicator="GDP")
        assert not s.empty
    finally:
        db.close()
