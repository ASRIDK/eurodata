"""Orchestrated eurodata ingestion pipeline (Prefect 3).

A single flow turns the pipeline scripts into an observable, retried,
materialization-graph DAG:

    ingest[eurostat] ─┐
    ingest[ecb]       ├─▶ build_graph ─▶ quality_gate ─▶ release
    ingest[oecd]      │
    ingest[world_bank]┘

Each source is a discrete task with retries; the ``quality_gate`` task runs the
data-quality contracts (``eurodata.ingest.quality``) and **fails the flow** if a
blocking contract is broken, so a bad refresh never publishes a release.

Run it:

    pip install -e ".[ingest,app,orchestration]"
    python -m flows.ingestion                 # full run + release
    python -m flows.ingestion --no-release    # skip the Parquet export

DuckDB is single-writer, so the per-source tasks run sequentially; each opens
its own connection to the same file. Fetch-level failures are caught by
``run_source`` (they land in ``ingestion_run``/``ingestion_error`` rather than
crashing), and the freshness / no-failed-run contracts then decide whether the
result is acceptable.
"""
from __future__ import annotations

import argparse
from importlib import import_module

from prefect import flow, task
from prefect.logging import get_run_logger

from eurodata.config import get_settings
from eurodata.db import connect
from eurodata.export.release import export_facts
from eurodata.graph.build import build_graph
from eurodata.ingest.pipeline import run_source
from eurodata.ingest.quality import run_quality_checks
from eurodata.sources.registry import all_sources

# Importing a source module registers its fetcher in the registry.
_SOURCE_MODULES = (
    "eurodata.sources.eurostat",
    "eurodata.sources.ecb",
    "eurodata.sources.oecd",
    "eurodata.sources.world_bank",
)


def _register_sources() -> None:
    for module_name in _SOURCE_MODULES:
        import_module(module_name)


@task(retries=2, retry_delay_seconds=30, task_run_name="ingest-{source_name}")
def ingest_source(db_path: str, source_name: str, start_year: int) -> int:
    """Fetch and load one source. Returns the number of records loaded."""
    logger = get_run_logger()
    _register_sources()
    con = connect(db_path)
    try:
        count = run_source(con, source_name, start_year)
    finally:
        con.close()
    logger.info("ingested %s: %d records", source_name, count)
    return count


@task(retries=1)
def build_structural_graph(db_path: str) -> None:
    """Rebuild the countries/indicators/sources correlation graph."""
    con = connect(db_path)
    try:
        build_graph(con)
    finally:
        con.close()


@task
def quality_gate(db_path: str, *, min_rows: int = 1000) -> dict:
    """Run the data-quality contracts and fail the flow on a blocking breach."""
    logger = get_run_logger()
    con = connect(db_path, read_only=True)
    try:
        report = run_quality_checks(con, min_rows=min_rows)
    finally:
        con.close()
    logger.info("\n%s", report.summary())
    report.raise_for_status()  # blocking contract -> raises -> flow fails
    return report.as_dict()


@task
def release(db_path: str, out_dir: str) -> str:
    """Export the redistributable facts to Parquet."""
    logger = get_run_logger()
    con = connect(db_path, read_only=True)
    try:
        path = export_facts(con, out_dir)
    finally:
        con.close()
    logger.info("wrote release %s", path)
    return str(path)


@flow(name="eurodata-ingestion")
def ingestion_flow(db_path: str | None = None, start_year: int | None = None,
                   *, do_release: bool = True, min_rows: int = 1000) -> dict:
    """End-to-end refresh: ingest every source, rebuild the graph, gate on data
    quality, then (optionally) cut a release. Returns the quality report."""
    logger = get_run_logger()
    settings = get_settings()
    db_path = db_path or settings.duckdb_path
    start_year = start_year if start_year is not None else settings.ingest_start_year

    # The registry is only populated by importing the source modules; do it
    # here (not just inside the task) or all_sources() is empty in a fresh
    # process and the flow silently ingests nothing.
    _register_sources()
    counts: dict[str, int] = {}
    for source_name in all_sources():
        counts[source_name] = ingest_source(db_path, source_name, start_year)
    logger.info("ingestion complete: %s", counts)

    build_structural_graph(db_path)
    report = quality_gate(db_path, min_rows=min_rows)  # raises if blocked

    if do_release:
        release(db_path, settings.release_dir)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eurodata ingestion pipeline.")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--min-rows", type=int, default=1000)
    parser.add_argument("--no-release", action="store_true",
                        help="skip the Parquet release export")
    args = parser.parse_args()
    ingestion_flow(db_path=args.db_path, start_year=args.start_year,
                   do_release=not args.no_release, min_rows=args.min_rows)


if __name__ == "__main__":
    main()
