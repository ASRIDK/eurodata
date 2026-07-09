# Adding a data source

Ground rules (non-negotiable):

1. **Never invent data.** Only open, legal, properly licensed sources.
2. Prefer official APIs / bulk downloads over HTML scraping.
3. Every record needs provenance: source row (with license), indicator
   `definition`, `unit`, and an honest `is_proxy` / `proxy_note` when the
   series is a stand-in for the official concept.
4. **No silent failures.** Per-series errors go into `self.errors`; the
   pipeline persists them to `ingestion_error` and marks the run
   `completed_with_errors`.

## Steps

1. **Catalog** — add the indicator(s) to `reference/catalog.py::INDICATORS`
   (**append at the end** — seed ids are positional) and, if new, the source to
   `SOURCES` with its license.
2. **Fetcher** — subclass `sources.base.BaseFetcher` in `sources/<name>.py`,
   decorate with `@register`, and emit `Record` objects whose
   `indicator_code` matches the catalog `api_code`. Use `requests` with
   explicit timeouts and bounded retries (see `sources/eurostat.py` for the
   pattern, including the JSON-stat decoder). If the source is not ready,
   set `enabled = False` with a `disabled_reason` instead of returning `[]`.
3. **Register the module** in `scripts/run_ingestion.py`'s import list.
4. **Tests** — add a normalization test with a small fixture payload (no
   network in unit tests) and update `tests/test_seed.py` counts.
5. **Verify** — `python scripts/init_db.py && python scripts/run_ingestion.py`,
   then check `ed.coverage()` and `ed.ingestion_summary()`.

Events follow the same pattern in `reference/events.py`: stable `code`,
primary `source_url`, honest `confidence`.
