# eurodata

Open-source, file-based **European data intelligence dataset** covering geographical Europe (~44 countries).

- **Facts**: trustworthy official statistics (Eurostat, ECB, OECD, World Bank) in a single DuckDB fact table with full revision lineage.
- **Graph**: countries, indicators, sources, and blocs modeled as nodes/edges (DuckDB → NetworkX) for centrality and community analysis.
- **Open**: versioned downloadable bundles (Parquet / CSV / DuckDB / GraphML).

See the design spec: [`docs/superpowers/specs/2026-07-08-eurodata-design.md`](docs/superpowers/specs/2026-07-08-eurodata-design.md).

## Status
v1 in development — dataset + structural graph. Correlation/neuro engine and forecasting are planned for v2.
