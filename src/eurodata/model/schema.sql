CREATE TABLE IF NOT EXISTS geography (
    id INTEGER PRIMARY KEY,
    code VARCHAR NOT NULL,
    level VARCHAR NOT NULL DEFAULT 'country',
    parent_id INTEGER,
    name VARCHAR NOT NULL,
    iso2 VARCHAR,
    iso3 VARCHAR,
    official_name VARCHAR,
    capital VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    area_km2 DOUBLE,
    is_transcontinental BOOLEAN DEFAULT FALSE,
    is_disputed BOOLEAN DEFAULT FALSE,
    note VARCHAR
);

CREATE TABLE IF NOT EXISTS bloc (
    id INTEGER PRIMARY KEY,
    code VARCHAR NOT NULL UNIQUE,
    name VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS geography_bloc (
    geography_id INTEGER NOT NULL,
    bloc_id INTEGER NOT NULL,
    since_year INTEGER,
    until_year INTEGER,
    PRIMARY KEY (geography_id, bloc_id)
);

CREATE TABLE IF NOT EXISTS domain (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    description VARCHAR,
    color VARCHAR
);

CREATE TABLE IF NOT EXISTS indicator (
    id INTEGER PRIMARY KEY,
    domain_id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    unit VARCHAR,
    description VARCHAR,
    api_code VARCHAR,
    source_priority INTEGER DEFAULT 1,
    is_forecastable BOOLEAN DEFAULT TRUE,
    frequency VARCHAR DEFAULT 'annual',
    definition VARCHAR,
    is_proxy BOOLEAN DEFAULT FALSE,
    proxy_note VARCHAR,
    UNIQUE (domain_id, name)
);

CREATE TABLE IF NOT EXISTS source (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    organization VARCHAR,
    url VARCHAR,
    api_endpoint VARCHAR,
    reliability_score DOUBLE DEFAULT 0.9,
    license VARCHAR,
    redistributable BOOLEAN DEFAULT FALSE,
    update_frequency VARCHAR
);

CREATE TABLE IF NOT EXISTS statistic_record (
    id BIGINT DEFAULT nextval('seq_statistic') PRIMARY KEY,
    geography_id INTEGER NOT NULL,
    indicator_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER,
    month INTEGER,
    value DOUBLE,
    unit VARCHAR,
    currency VARCHAR,
    price_basis VARCHAR,
    confidence_score DOUBLE DEFAULT 1.0,
    is_estimated BOOLEAN DEFAULT FALSE,
    vintage_date DATE,
    retrieved_at TIMESTAMP DEFAULT now(),
    UNIQUE (geography_id, indicator_id, source_id, year, quarter, month, vintage_date)
);

CREATE TABLE IF NOT EXISTS graph_node (
    id INTEGER PRIMARY KEY,
    node_type VARCHAR NOT NULL,
    ref_id INTEGER NOT NULL,
    label VARCHAR NOT NULL,
    UNIQUE (node_type, ref_id)
);

CREATE TABLE IF NOT EXISTS graph_edge (
    id BIGINT DEFAULT nextval('seq_edge') PRIMARY KEY,
    src_node_id INTEGER NOT NULL,
    dst_node_id INTEGER NOT NULL,
    edge_type VARCHAR NOT NULL,
    weight DOUBLE DEFAULT 1.0,
    props VARCHAR
);

CREATE TABLE IF NOT EXISTS raw_snapshot (
    id BIGINT DEFAULT nextval('seq_snapshot') PRIMARY KEY,
    source VARCHAR NOT NULL,
    endpoint VARCHAR,
    params VARCHAR,
    retrieved_at TIMESTAMP DEFAULT now(),
    file_path VARCHAR,
    sha256 VARCHAR
);

CREATE TABLE IF NOT EXISTS ingestion_error (
    id BIGINT DEFAULT nextval('seq_ingestion_error') PRIMARY KEY,
    source VARCHAR NOT NULL,
    series VARCHAR,
    error VARCHAR NOT NULL,
    occurred_at TIMESTAMP DEFAULT now()
);

-- Structured events (elections, crises, policy milestones) for event studies.
-- iso3 is NULL for bloc-/Europe-wide events; bloc_code is NULL for
-- country-specific ones. tags / affected_domains are comma-separated.
CREATE TABLE IF NOT EXISTS event (
    id BIGINT DEFAULT nextval('seq_event') PRIMARY KEY,
    code VARCHAR NOT NULL UNIQUE,
    title VARCHAR NOT NULL,
    description VARCHAR,
    event_type VARCHAR NOT NULL,
    iso3 VARCHAR,
    bloc_code VARCHAR,
    start_date DATE NOT NULL,
    end_date DATE,
    source VARCHAR,
    source_url VARCHAR,
    confidence DOUBLE DEFAULT 1.0,
    tags VARCHAR,
    affected_domains VARCHAR
);

CREATE TABLE IF NOT EXISTS ingestion_run (
    id BIGINT DEFAULT nextval('seq_run') PRIMARY KEY,
    source VARCHAR NOT NULL,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    status VARCHAR,
    records_processed INTEGER DEFAULT 0,
    error VARCHAR
);

CREATE OR REPLACE VIEW statistic_current AS
SELECT s.* FROM statistic_record s
JOIN (
    SELECT geography_id, indicator_id, source_id, year,
           COALESCE(quarter, -1) AS q, COALESCE(month, -1) AS m,
           MAX(COALESCE(vintage_date, DATE '0001-01-01')) AS max_vintage
    FROM statistic_record
    GROUP BY 1,2,3,4,5,6
) latest
ON s.geography_id = latest.geography_id
AND s.indicator_id = latest.indicator_id
AND s.source_id = latest.source_id
AND s.year = latest.year
AND COALESCE(s.quarter, -1) = latest.q
AND COALESCE(s.month, -1) = latest.m
AND COALESCE(s.vintage_date, DATE '0001-01-01') = latest.max_vintage;

CREATE OR REPLACE VIEW statistic_best AS
SELECT c.* FROM statistic_current c
JOIN indicator i ON i.id = c.indicator_id
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY c.geography_id, c.indicator_id, c.year,
                 COALESCE(c.quarter, -1), COALESCE(c.month, -1)
    ORDER BY i.source_priority ASC, c.source_id ASC
) = 1;
