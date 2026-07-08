# AfriNet — Complete Project Analysis

> Repository: https://github.com/AdemMarghli/AfriNet  
> Analyzed: 2026-07-08  
> Primary language: PLpgSQL (PostgreSQL schema-heavy project)  
> Created: 2026-07-08 | Stars: 0 | Forks: 0 | License: None

---

## 1. What is AfriNet?

AfriNet is an **Africa AI Intelligence Platform** — a full-stack data aggregation and analytics system covering all **54 African countries**. It ingests statistics from **20+ international sources**, validates them with AI agents, stores everything in PostgreSQL, runs simulations and forecasts, and displays everything through a **Streamlit dashboard**.

Think of it as a self-updating statistical observatory for the African continent, where AI agents handle data quality, forecasting, and insight generation automatically.

---

## 2. Project Structure

```
africa-ai-platform/
├── app/
│   ├── streamlit_app.py         # Main Streamlit dashboard entry point
│   └── components.py            # Reusable UI components
├── database/
│   ├── schema.sql               # Full PostgreSQL schema (ERD)
│   ├── seed_data.sql            # Domains, indicators, sources, countries
│   ├── africa_data.sql          # (root) Pre-loaded African data
│   ├── generated_collect_world_bank_public.sql
│   ├── generated_import_african_digital_data.sql
│   └── migrations/              # Schema migrations
├── src/
│   ├── config.py                # Pydantic settings (env vars)
│   ├── agents/
│   │   └── crew.py              # All 5 CrewAI agent definitions + task builders
│   ├── data_sources/            # 14 source fetcher modules
│   │   ├── registry.py          # Source registry
│   │   ├── world_bank.py
│   │   ├── who.py
│   │   ├── imf.py
│   │   ├── afdb.py
│   │   ├── unpd.py
│   │   ├── unicef.py
│   │   ├── itu.py
│   │   ├── gsma.py
│   │   ├── oecd_ai.py
│   │   ├── openalex.py
│   │   ├── owid.py
│   │   ├── github_activity.py
│   │   └── open_africa.py
│   ├── db/                      # SQLAlchemy connection + Repository pattern
│   ├── llm/
│   │   └── providers.py         # OpenAI + Gemini LLM configuration
│   └── services/                # 15 service modules (see §6)
├── scripts/
│   ├── init_db.py               # Creates tables, runs schema.sql
│   └── run_ingestion.py         # Triggers full data pipeline
├── data/                        # Raw data files
├── reports/                     # Generated reports
├── African_Digital_Data_ALL_54_Countries_FIXED.xlsx  # Bulk Excel dataset
├── requirements.txt
├── .env.example
└── test_import.py
```

---

## 3. Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Dashboard | Streamlit | ≥ 1.40.0 |
| Data manipulation | Pandas, NumPy | ≥ 2.2.0 / 1.26.0 |
| Visualization | Plotly | ≥ 5.24.0 |
| Database | PostgreSQL | 14+ |
| ORM / DB driver | SQLAlchemy + psycopg2-binary | ≥ 2.0.36 |
| AI Agents | CrewAI | ≥ 0.86.0 |
| LLM (reasoning) | OpenAI GPT-4.1 | via langchain-openai |
| LLM (extraction) | Google Gemini 2.5 Flash | via langchain-google-genai |
| ML / Analytics | scikit-learn, scipy, statsmodels | ≥ 1.5.0 |
| Config management | pydantic-settings | ≥ 2.6.0 |
| World Bank data | wbgapi | ≥ 1.0.12 |
| Google Trends | pytrends | ≥ 4.9.2 |
| Scheduling | APScheduler | ≥ 3.10.4 |
| Retry logic | tenacity | ≥ 9.0.0 |
| Kaggle datasets | kaggle | ≥ 1.6.17 |
| Runtime | Python | 3.11+ |

---

## 4. Data Domains (7)

1. **Demographics** — population, age distribution, fertility, urbanization, migration (UNPD, World Bank, OWID)
2. **Economy** — GDP, GDP per capita, inflation, trade, exports, growth (World Bank, AfDB, IMF)
3. **Health** — life expectancy, child mortality, vaccination, nutrition (WHO, UNICEF, OWID)
4. **Internet & Connectivity** — internet penetration, broadband, mobile, 4G/5G, fiber, mobile money (ITU, GSMA)
5. **Social Media** — Facebook, Instagram, LinkedIn, Twitter/X, TikTok, YouTube, Snapchat, Telegram, WhatsApp users per country (DataReportal)
6. **AI** — startups, funding, researchers, publications, patents, policies, jobs, GitHub repos (OECD AI, OpenAlex, GitHub API, Stanford HAI)
7. **Startups** — startup count, funding rounds (seed/A/B), unicorns, investors, accelerators, tech hubs, exits (Partech Africa)

---

## 5. Data Sources (20+)

| Source | Type | Key Indicators |
|--------|------|---------------|
| World Bank | API (wbgapi) | GDP, population, health, connectivity |
| AfDB | API | GDP, inflation, trade, exports |
| UNPD | API | Population, fertility, migration, urbanization |
| UNICEF | API | Child mortality, vaccination, nutrition |
| WHO | API | Health statistics |
| IMF | API | Macroeconomic |
| ITU | Dataset (Excel/CSV) | Internet users, broadband, mobile, 5G, fiber |
| GSMA | Dataset (Excel/CSV) | Mobile penetration, 4G/5G, smartphone, mobile money |
| OpenAlex | API | AI publication counts by country |
| Our World in Data | CSV | Population, life expectancy, CO2, energy |
| OECD AI Observatory | API | AI startups, funding, researchers, policies, jobs |
| GitHub API | API | AI/open-source repository counts |
| Open Africa (CKAN) | API | ITU-backed internet usage datasets |
| DataReportal | (integrated) | Social media user counts |
| Stanford HAI | (integrated) | AI ecosystem data |
| Partech Africa | (integrated) | Startup funding data |
| Crunchbase | API key (optional) | Startup data |
| PitchBook | API key (optional) | Investment data |
| PyTrends / Google Trends | API | Search interest trends |
| Kaggle | API | Dataset downloads |

**Note:** ITU and GSMA are marked `dataset_only` — they require manual Excel/CSV upload rather than live API access.

---

## 6. Services Layer (`src/services/`)

| Service | Purpose |
|---------|---------|
| `ingestion.py` | Master pipeline: fetches all sources, runs CrewAI validation, upserts to PostgreSQL |
| `forecasting.py` | Generates 1-10 year predictions with confidence intervals |
| `insights.py` | AI-generated trend/anomaly/correlation/policy insights per country+domain |
| `simulation.py` | What-if scenario modeling |
| `correlation.py` | Cross-indicator statistical correlation analysis |
| `chatbot.py` | Conversational AI over the data |
| `natural_dashboard.py` | Natural language query interface for the dashboard |
| `recommendation.py` | Policy/investment recommendations |
| `excel_ingestion.py` | Handles bulk Excel dataset uploads (ITU, GSMA, custom) |
| `source_connectors.py` | Source connection health checks |
| `context_builder.py` | Builds LLM context from DB for prompting |
| `data_gaps.py` | Identifies missing data across countries/years |
| `creator_fetching.py` | Fetches content creator / influencer data |
| `creator_rankings.py` | Ranks creators by reach/domain |

---

## 7. AI Agents (CrewAI)

The platform uses **5 distinct AI agents** orchestrated via CrewAI in sequential `Process` mode.

### Agent 1 — Data Validation Agent
- **LLM**: Gemini 2.5 Flash (extraction model)
- **Role**: Validates incoming records before PostgreSQL storage
- **Checks**: Completeness · Accuracy (plausible range for Africa) · Consistency (no sudden jumps) · Timeliness
- **Output**: JSON array with `overall_score`, `issues`, `approved` per record

### Agent 2 — Source Verification Agent
- **LLM**: Gemini 2.5 Flash (extraction model)
- **Role**: Assesses reliability of each data source
- **Checks**: Organization credibility · Licensing · Update frequency · Known biases for African data
- **Output**: JSON with `reliability_score`, `bias_score`, `completeness_score`, `notes`, `recommendation`

### Agent 3 — Forecasting Agent
- **LLM**: OpenAI GPT-4.1 (reasoning model)
- **Role**: Generates multi-year forecasts for country indicators
- **Method**: Trend analysis, regression, scenario modeling
- **Output**: JSON with forecast array (`predicted_value`, `lower_bound`, `upper_bound`, `confidence_score`) + methodology

### Agent 4 — Insights Agent
- **LLM**: OpenAI GPT-4.1 (reasoning model)
- **Role**: Synthesizes multi-domain data into actionable intelligence
- **Output**: 3-5 insights per country+domain, each typed as `trend | anomaly | correlation | policy`

### Agent 5 — Domain Ingestion Agent (dynamic, one per source)
- **LLM**: Gemini 2.5 Flash (extraction model)
- **Role**: Fetches, classifies, and normalizes data per source
- **Created dynamically** for each registered source during ingestion

---

## 8. Database Schema (PostgreSQL)

### Core Reference Tables
- `country` — 54 African countries (UUID PK, ISO2/ISO3, region, lat/lon, population, area)
- `region` — hierarchical regions (sub-regions supported via `parent_region_id`)
- `country_region` — many-to-many country ↔ region
- `domain` — 7 data domains with icon/color
- `indicator_category` — categories within domains
- `indicator` — all tracked metrics (with hierarchy via `parent_indicator_id`, `api_code` for source mapping)
- `source` — 20+ data sources with reliability scores
- `source_reliability` — per-source scored reliability assessments
- `document` — source documents/reports linked to countries

### Central Fact Table
- `statistic_record` — all numeric data points  
  `(country_id, indicator_id, source_id, year, quarter, month, value, confidence_score, is_estimated)`  
  Unique constraint: `(country_id, indicator_id, source_id, year, quarter, month)` — supports UPSERT

### Domain-Specific Denormalized Tables
- `demographic_distribution` — male/female, urban/rural, median age, dependency ratio
- `age_distribution` — 5-year age bands (0-4, 5-9, ... 75+)
- `connectivity_statistic` — internet %, broadband %, mobile users, 4G/5G, speed
- `social_media_statistic` — per-platform user counts (9 platforms)
- `startup_statistic` — counts, funding rounds, unicorns, accelerators, exits
- `ai_statistic` — AI startups, funding, researchers, publications, patents, policies, jobs
- `digital_economy_statistic` — e-commerce, digital payments, fintech, digital GDP share

### AI & Analytics Tables
- `ai_insight` — LLM-generated insights (typed, confidence-scored)
- `prediction` — forecasts with bounds and confidence
- `correlation` — statistical correlations between any two indicators
- `agent_log` — execution logs for all CrewAI runs
- `country_event` — historical events linked to countries and indicators

### Users & Simulation
- `user` — authenticated users with roles
- `user_query` — chatbot/NL query history with token usage
- `simulation` — saved what-if scenarios with parameters and results (JSONB)

---

## 9. Configuration

All config is managed via `pydantic-settings` reading from `.env`:

```
DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD
OPENAI_API_KEY        → GPT-4.1 (forecasting + insights)
GOOGLE_API_KEY        → Gemini 2.5 Flash (validation + extraction)
GITHUB_TOKEN          → GitHub API (AI repo counts)
YOUTUBE_API_KEY       → (social media data)
NEWSAPI_KEY           → (news mentions)
CRUNCHBASE_API_KEY    → (startup data, optional)
PITCHBOOK_API_KEY     → (investment data, optional)
ITU_API_KEY / GSMA_API_KEY / DATA365_API_KEY / HYPEAUDITOR_API_KEY
MODASH_API_KEY / FAVIKON_API_KEY  → (creator analytics, optional)
```

Default models: `openai_model = "gpt-4.1"` | `gemini_model = "gemini-2.5-flash"`

---

## 10. Setup & Run (Quick Reference)

```bash
# 1. Create virtualenv
cd africa-ai-platform
python -m venv .venv && source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# 2. Configure
cp .env.example .env   # then fill in DB_PASSWORD, API keys

# 3. Init database (creates all tables)
python scripts/init_db.py

# 4. Ingest data
python scripts/run_ingestion.py

# 5. Launch dashboard
streamlit run app/streamlit_app.py
# → open http://localhost:8501
```

---

## 11. Data Flow (End-to-End)

```
External APIs / Datasets
        ↓
src/data_sources/<source>.py   ← fetchers normalize to {iso3, indicator_code, year, value}
        ↓
CrewAI Domain Ingestion Agent  ← classifies & maps indicators
        ↓
CrewAI Data Validation Agent   ← scores completeness/accuracy/consistency/timeliness
        ↓
src/db/repository.py           ← upserts to PostgreSQL (statistic_record fact table)
        ↓
src/services/forecasting.py    ← CrewAI Forecasting Agent → prediction table
src/services/insights.py       ← CrewAI Insights Agent → ai_insight table
src/services/correlation.py    ← statistical correlation → correlation table
        ↓
app/streamlit_app.py           ← reads DB, renders Plotly charts, exposes chatbot + NL interface
```

---

## 12. Key Design Decisions

- **Star schema** with a central `statistic_record` fact table plus denormalized domain tables for fast dashboard queries.
- **Dual LLM strategy**: Gemini 2.5 Flash for cheap, fast extraction/validation; GPT-4.1 for high-quality reasoning/forecasting.
- **CrewAI optional**: ingestion works without CrewAI (agents gracefully disabled with try/except).
- **UPSERT everywhere**: all data writes use `ON CONFLICT DO UPDATE` to be idempotent.
- **Source priority**: `indicator.source_priority` controls which source wins when multiple sources provide the same indicator.
- **Extensible sources**: add a new fetcher to `src/data_sources/`, register it in `registry.py` — an ingestion agent is created automatically.

---

## 13. ⚠️ Security Issue (Critical)

The `.env.example` file in the repository contains **real API keys** (not placeholder values):
- An OpenAI API key (`sk-proj-...`)
- A Google API key (`AQ.Ab8RN6J...`)

**These credentials should be revoked immediately.** The owner (AdemMarghli) should:
1. Revoke both keys from the OpenAI and Google Cloud consoles now.
2. Generate new keys and store them only in the local `.env` file (which is in `.gitignore`).
3. Replace `.env.example` with placeholder values like `your_openai_key_here`.
4. Consider running `git filter-repo` or BFG to purge the keys from git history.

---

## 14. What's Notably Missing / Future Work

- No test suite (only `test_import.py` which likely just verifies imports)
- No Docker / docker-compose for local setup
- No CI/CD configuration
- No API layer (REST/GraphQL) — data is only accessible via Streamlit
- DataReportal, Stanford HAI, Partech Africa are referenced but no fetcher modules visible — likely handled via Excel ingestion
- IMF fetcher listed in `data_sources/` directory but not registered in `SOURCE_INGESTORS` dict
- Creator analytics (creator_fetching.py, creator_rankings.py) not documented in README — appears to be undocumented feature
