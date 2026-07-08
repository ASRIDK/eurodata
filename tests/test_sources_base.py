from eurodata.sources.base import Record, BaseFetcher
from eurodata.sources.registry import register, get_fetcher, all_sources


def test_record_defaults():
    r = Record(iso3="DEU", indicator_code="nama_10_gdp", year=2020, value=1.5)
    assert r.quarter is None and r.unit is None


def test_registry_roundtrip():
    class Dummy(BaseFetcher):
        source_name = "Dummy"
        def fetch(self, start_year: int):
            return [Record("DEU", "x", 2020, 1.0)]
    register(Dummy)
    assert "Dummy" in all_sources()
    assert isinstance(get_fetcher("Dummy"), Dummy)
