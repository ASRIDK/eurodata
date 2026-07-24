"""Prefect orchestration for the eurodata data pipeline.

Kept out of the importable ``eurodata`` package so the core library and its
tests never depend on Prefect. Install the orchestrator with the optional
extra: ``pip install -e ".[orchestration]"``.
"""
