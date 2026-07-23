"""Probe every registered source and report whether it still returns data.

This is a *health check*, not an ingestion: nothing is written to DuckDB. It
exists because the failure mode that once emptied this dataset was silent --
Eurostat's fetcher wrapped every call in `except Exception: continue`, so a
broken API looked exactly like a working one that had no data, and the whole
dataset quietly rode on the World Bank fallback for two indicators.

Upstream APIs break in ways a unit test cannot catch: dataflow keys get retired
(World Bank's Doing Business `IC.REG.*` codes), datasets get discontinued after
a classification revision (the Eurostat enterprise-demography series end in
2020), and gateways start returning 502s under load. Running this on a schedule
turns those into a visible alert instead of a dataset that slowly goes stale.

Exit status: 0 if every enabled source returned records, 1 otherwise -- so CI
can fail the job and open an issue.

    python scripts/check_sources.py             # all sources
    python scripts/check_sources.py --json      # machine-readable
    python scripts/check_sources.py --source "World Bank"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import traceback
from importlib import import_module

try:
    from _bootstrap import ensure_paths
    ensure_paths()
except ModuleNotFoundError:
    pass  # already importable

# Importing the modules is what registers the fetchers.
for _module in (
    "eurodata.sources.eurostat",
    "eurodata.sources.ecb",
    "eurodata.sources.oecd",
    "eurodata.sources.world_bank",
):
    import_module(_module)

from eurodata.sources.registry import all_sources, get_fetcher  # noqa: E402


def probe(source_name: str, start_year: int) -> dict:
    """Fetch one source and summarize the outcome. Never raises."""
    started = time.monotonic()
    fetcher = get_fetcher(source_name)
    result: dict = {
        "source": source_name,
        "enabled": bool(fetcher.enabled),
        "records": 0,
        "series_errors": [],
        "fatal": None,
    }
    if not fetcher.enabled:
        result["disabled_reason"] = fetcher.disabled_reason
        result["seconds"] = round(time.monotonic() - started, 1)
        return result
    try:
        records = fetcher.fetch(start_year)
        result["records"] = len(records)
        result["indicators"] = sorted({r.indicator_code for r in records})
    except Exception as exc:  # noqa: BLE001 - a probe reports, it does not crash
        result["fatal"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc(limit=3)
    # Per-series failures are recorded on the fetcher rather than raised, which
    # is exactly the signal we want: a source can "succeed" with half its series
    # broken.
    result["series_errors"] = [
        {"series": s, "error": str(e)[:200]} for s, e in getattr(fetcher, "errors", [])
    ]
    result["seconds"] = round(time.monotonic() - started, 1)
    return result


def is_healthy(r: dict) -> bool:
    """A disabled source is not a failure (it is deliberately off); an enabled
    one that raised, or came back with nothing, is."""
    if not r["enabled"]:
        return True
    return r["fatal"] is None and r["records"] > 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", action="append", help="probe only this source (repeatable)")
    ap.add_argument("--start-year", type=int, default=dt.date.today().year - 1,
                    help="narrow the fetch window to keep the probe cheap")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args(argv[1:])

    names = args.source or all_sources()
    results = [probe(n, args.start_year) for n in names]

    if args.json:
        print(json.dumps({"checked_at": dt.datetime.now(dt.UTC).isoformat(),
                          "start_year": args.start_year,
                          "results": results}, indent=2))
    else:
        print(f"Source health @ {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC "
              f"(from {args.start_year})\n")
        print(f"  {'SOURCE':<14} {'STATUS':<10} {'RECORDS':>8}  {'TIME':>6}  DETAIL")
        for r in results:
            if not r["enabled"]:
                status, detail = "skipped", r.get("disabled_reason", "")
            elif r["fatal"]:
                status, detail = "FAILED", r["fatal"][:70]
            elif r["records"] == 0:
                status, detail = "EMPTY", "returned no records"
            elif r["series_errors"]:
                status = "degraded"
                detail = f"{len(r['series_errors'])} series failed"
            else:
                status, detail = "ok", f"{len(r.get('indicators', []))} indicators"
            print(f"  {r['source']:<14} {status:<10} {r['records']:>8,}  "
                  f"{r['seconds']:>5}s  {detail}")
        for r in results:
            for e in r["series_errors"][:5]:
                print(f"      ! {r['source']} / {e['series']}: {e['error'][:90]}")

    unhealthy = [r["source"] for r in results if not is_healthy(r)]
    if unhealthy:
        print(f"\nUNHEALTHY: {', '.join(unhealthy)}", file=sys.stderr)
        return 1
    print("\nAll enabled sources returned data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
