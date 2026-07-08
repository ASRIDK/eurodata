DOMAINS = [
    {"name": "Demographics", "description": "Population, age, migration", "color": "#4C78A8"},
    {"name": "Economy", "description": "GDP, inflation, trade, employment", "color": "#F58518"},
    {"name": "Digital & Connectivity", "description": "Internet, broadband, digital economy", "color": "#54A24B"},
    {"name": "Energy & Green", "description": "Energy, renewables, emissions", "color": "#72B7B2"},
]

# domain must match a DOMAINS name; api_code is the source series key.
INDICATORS = [
    {"domain": "Demographics", "name": "Population", "unit": "persons", "api_code": "demo_pjan", "source_priority": 1},
    {"domain": "Demographics", "name": "Median Age", "unit": "years", "api_code": "demo_pjanind", "source_priority": 1},
    {"domain": "Economy", "name": "GDP", "unit": "EUR", "api_code": "nama_10_gdp", "source_priority": 1},
    {"domain": "Economy", "name": "GDP per capita", "unit": "EUR", "api_code": "sdg_08_10", "source_priority": 1},
    {"domain": "Economy", "name": "Inflation (HICP)", "unit": "%", "api_code": "prc_hicp_aind", "source_priority": 1},
    {"domain": "Economy", "name": "Unemployment Rate", "unit": "%", "api_code": "une_rt_a", "source_priority": 1},
    {"domain": "Digital & Connectivity", "name": "Internet Users %", "unit": "%", "api_code": "isoc_ci_ifp_iu", "source_priority": 1},
    {"domain": "Digital & Connectivity", "name": "Broadband Coverage %", "unit": "%", "api_code": "isoc_ci_it_en2", "source_priority": 1},
    {"domain": "Energy & Green", "name": "Renewable Energy Share %", "unit": "%", "api_code": "nrg_ind_ren", "source_priority": 1},
    {"domain": "Energy & Green", "name": "Greenhouse Gas Emissions", "unit": "tonnes CO2e", "api_code": "env_air_gge", "source_priority": 1},
]

SOURCES = [
    {"name": "Eurostat", "organization": "European Commission", "url": "https://ec.europa.eu/eurostat",
     "api_endpoint": "https://ec.europa.eu/eurostat/api/dissemination",
     "reliability_score": 0.95, "license": "CC BY 4.0", "redistributable": True, "update_frequency": "varies"},
    {"name": "ECB", "organization": "European Central Bank", "url": "https://data.ecb.europa.eu",
     "api_endpoint": "https://data-api.ecb.europa.eu/service",
     "reliability_score": 0.95, "license": "ECB reuse policy (attribution)", "redistributable": True, "update_frequency": "daily"},
    {"name": "OECD", "organization": "OECD", "url": "https://data.oecd.org",
     "api_endpoint": "https://sdmx.oecd.org/public/rest",
     "reliability_score": 0.92, "license": "OECD terms (attribution)", "redistributable": True, "update_frequency": "varies"},
    {"name": "World Bank", "organization": "World Bank", "url": "https://data.worldbank.org",
     "api_endpoint": "https://api.worldbank.org/v2",
     "reliability_score": 0.9, "license": "CC BY 4.0", "redistributable": True, "update_frequency": "annual"},
]
