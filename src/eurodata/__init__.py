"""eurodata — open European data intelligence dataset.

    import eurodata as ed
    ed.series(country="FRA", indicator="GDP")
"""
from eurodata.api import (  # noqa: F401
    EuroData, EuroDataLookupError, open,
    countries, blocs, bloc_members, domains, indicators, sources, years,
    search_indicators, series, latest, provenance, revisions, revisions_summary,
    country_blocs, country_indicators, country_correlations,
    compare, forecast, coverage, ingestion_summary,
    events, event_types, event_study, correlate, lagged_correlation,
    query, relation, propagate,
)

__version__ = "0.2.0"
