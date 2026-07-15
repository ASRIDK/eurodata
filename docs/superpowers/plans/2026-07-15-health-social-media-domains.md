# Health & Social Media Domains Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new real-source data domains — Health (7 World Bank series) and Social Media (3 Eurostat usage series) — to the eurodata catalog, then rebuild the DB and ingest live data.

**Architecture:** Append-only additions to the reference catalog (`DOMAINS`, `INDICATORS`) plus matching fetcher wiring (`WB_CODES` self-maps for World Bank, `SERIES_PARAMS` dimension pins for Eurostat). One small fetcher change lets two indicators share a single Eurostat dataset via a `#`-suffixed api_code. Hardcoded catalog-count assertions in three test files move together. Finally an operational DB rebuild + ingestion loads the rows.

**Tech Stack:** Python 3.13, DuckDB, `wbgapi` (World Bank), `requests` (Eurostat JSON API), pytest.

## Global Constraints

- **Real sources only.** Every indicator maps to a live, redistributable official source (World Bank or Eurostat, both CC BY 4.0). No synthetic data, no un-sourced proxies.
- **Seed ids are positional.** `INDICATORS` and `DOMAINS` use `enumerate` + `ON CONFLICT DO NOTHING`. **Only append** to these lists — never insert or reorder — or existing DB ids shift.
- **Test command:** `cd /Users/toto/eurodata && PYTHONPATH=src .venv/bin/python -m pytest -q`
- **Ruff is not installed in `.venv`** — do not attempt to run it.
- **DuckDB write-lock:** `data/eurodata.duckdb` allows one read-write process OR many read-only. Any running uvicorn/Streamlit (read-only) blocks `init_db.py` / ingestion. Stop them before rebuild.
- **Final catalog totals after this plan:** 9 domains, 47 indicators, 5 sources.
- **api_code convention:** World Bank indicators use the WB series code as the catalog `api_code` and self-map in `WB_CODES`. Eurostat indicators use the dataset id as `api_code`, except when two series share a dataset — then the second uses `<dataset>#<suffix>`.

---

### Task 1: Eurostat `#`-suffix dataset split

Lets a catalog `api_code` like `isoc_ci_ac_i#Y16_24` be fetched from dataset `isoc_ci_ac_i` while records are still emitted under the full api_code (so `load_records` matches the catalog row). Pure, isolated logic — build and test it first.

**Files:**
- Modify: `src/eurodata/sources/eurostat.py`
- Test: `tests/test_sources_eurostat.py` (create if absent; otherwise append)

**Interfaces:**
- Produces: `dataset_id(api_code: str) -> str` — strips any `#suffix`, returning the bare Eurostat dataset id. Used by `EurostatFetcher.fetch`.

- [ ] **Step 1: Write the failing test**

Create/append `tests/test_sources_eurostat.py`:

```python
from eurodata.sources.eurostat import dataset_id


def test_dataset_id_passthrough_without_suffix():
    assert dataset_id("isoc_ci_ac_i") == "isoc_ci_ac_i"
    assert dataset_id("prc_hicp_manr") == "prc_hicp_manr"


def test_dataset_id_strips_suffix():
    assert dataset_id("isoc_ci_ac_i#Y16_24") == "isoc_ci_ac_i"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_sources_eurostat.py -q`
Expected: FAIL — `ImportError: cannot import name 'dataset_id'`.

- [ ] **Step 3: Add the helper and use it in `fetch`**

In `src/eurodata/sources/eurostat.py`, add near the other module-level helpers (e.g. just below `_to_iso3`):

```python
def dataset_id(api_code: str) -> str:
    """Eurostat dataset id for a catalog api_code. A ``#suffix`` disambiguates
    multiple catalog indicators drawn from one dataset (e.g.
    ``isoc_ci_ac_i#Y16_24``); it is stripped for the HTTP call but kept as the
    record's indicator_code so it matches the catalog row."""
    return api_code.split("#", 1)[0]
```

Then in `EurostatFetcher.fetch`, change the request line so the HTTP call uses the bare dataset while records keep the full api_code. Replace:

```python
            try:
                data = self._get(api_code, params)
```

with:

```python
            try:
                data = self._get(dataset_id(api_code), params)
```

(The `normalize_eurostat(jsonstat_rows(data), api_code)` call below is already keyed on the full `api_code` — leave it unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_sources_eurostat.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/eurodata/sources/eurostat.py tests/test_sources_eurostat.py
git commit -m "feat(eurostat): #-suffix api_code so indicators can share a dataset

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Catalog + fetcher wiring for both domains

Add the 2 domains and 10 indicators, wire World Bank and Eurostat, and move all hardcoded count assertions to the new totals in one coherent, fully-green change.

**Files:**
- Modify: `src/eurodata/reference/catalog.py`
- Modify: `src/eurodata/sources/world_bank.py:32-62` (`WB_CODES` dict)
- Modify: `src/eurodata/sources/eurostat.py:24-46` (`SERIES_PARAMS` dict)
- Modify: `tests/test_seed.py:35-37`, `tests/test_seed.py:59-60`, `tests/test_seed.py:70`
- Modify: `tests/test_api.py:88`
- Modify: `tests/test_graph_build.py:28-29`

**Interfaces:**
- Consumes: `dataset_id` from Task 1 (already wired into `fetch`).
- Produces: catalog with 9 domains / 47 indicators; new Eurostat series keyed `isoc_ci_ac_i`, `isoc_ci_ac_i#Y16_24`, `isoc_cismt` in `SERIES_PARAMS`.

- [ ] **Step 1: Update the count/name tests first (they should fail)**

In `tests/test_seed.py`, extend the domain-name set (lines 35–37) to:

```python
    assert {"Demographics", "Economy", "Digital & Connectivity", "Energy & Green",
            "AI & Technology", "Governance & Geopolitics",
            "Startups & Business", "Health", "Social Media"} == names
```

In `tests/test_seed.py` change line 59 `== 7` → `== 9` and line 60 `== 37` → `== 47`:

```python
    assert con.execute("SELECT COUNT(*) FROM domain").fetchone()[0] == 9
    assert con.execute("SELECT COUNT(*) FROM indicator").fetchone()[0] == 47
```

In `tests/test_seed.py` change line 70 `== 7` → `== 9`:

```python
    assert con.execute("SELECT COUNT(*) FROM domain").fetchone()[0] == 9
```

In `tests/test_api.py` change line 88 `== 37` → `== 47`:

```python
    assert len(cov) == 47
```

In `tests/test_graph_build.py` change lines 28–29 `== 37` / `== 7` → `== 47` / `== 9`:

```python
    assert node_types["indicator"] == 47
    assert node_types["domain"] == 9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_seed.py tests/test_api.py tests/test_graph_build.py -q`
Expected: FAIL — assertion errors on domain/indicator counts and the domain-name set (catalog not yet extended).

- [ ] **Step 3: Append the two domains**

In `src/eurodata/reference/catalog.py`, append inside `DOMAINS` (after the `Startups & Business` entry, before the closing `]`):

```python
    # --- added 2026-07-15 (append-only; ids are positional) ---
    {"name": "Health", "description": "Health spending, workforce, and outcomes", "color": "#9D755D"},
    {"name": "Social Media", "description": "Social network use by individuals and enterprises", "color": "#BAB0AC"},
```

- [ ] **Step 4: Append the ten indicators**

In `src/eurodata/reference/catalog.py`, append inside `INDICATORS` (after the last v4 entry `Unemployment Rate (monthly)`, before the closing `]`):

```python
    # --- added 2026-07-15: Health (World Bank; append-only, positional ids) ---
    {"domain": "Health", "name": "Health Expenditure (% GDP)", "unit": "%", "api_code": "SH.XPD.CHEX.GD.ZS", "source_priority": 1,
     "definition": "Current health expenditure, % of GDP (World Bank SH.XPD.CHEX.GD.ZS, from WHO Global Health Expenditure Database)."},
    {"domain": "Health", "name": "Physicians", "unit": "per 1,000 people", "api_code": "SH.MED.PHYS.ZS", "source_priority": 1,
     "definition": "Physicians per 1,000 people (World Bank SH.MED.PHYS.ZS, from WHO/OECD)."},
    {"domain": "Health", "name": "Hospital Beds", "unit": "per 1,000 people", "api_code": "SH.MED.BEDS.ZS", "source_priority": 1,
     "definition": "Hospital beds per 1,000 people (World Bank SH.MED.BEDS.ZS, from WHO/OECD/Eurostat)."},
    {"domain": "Health", "name": "Out-of-pocket Health Spending", "unit": "% of health expenditure", "api_code": "SH.XPD.OOPC.CH.ZS", "source_priority": 1,
     "definition": "Out-of-pocket expenditure, % of current health expenditure (World Bank SH.XPD.OOPC.CH.ZS, from WHO GHED)."},
    {"domain": "Health", "name": "Measles Immunization", "unit": "% of children 12-23 months", "api_code": "SH.IMM.MEAS", "source_priority": 1,
     "definition": "Immunization against measles, % of children ages 12-23 months (World Bank SH.IMM.MEAS, from WHO/UNICEF)."},
    {"domain": "Health", "name": "Infant Mortality", "unit": "per 1,000 live births", "api_code": "SP.DYN.IMRT.IN", "source_priority": 1,
     "definition": "Mortality rate, infant, per 1,000 live births (World Bank SP.DYN.IMRT.IN, UN IGME estimate)."},
    {"domain": "Health", "name": "Suicide Mortality", "unit": "per 100,000 people", "api_code": "SH.STA.SUIC.P5", "source_priority": 1,
     "definition": "Suicide mortality rate, per 100,000 population (World Bank SH.STA.SUIC.P5, from WHO); series ends ~2021 (WHO reporting lag)."},
    # --- added 2026-07-15: Social Media (Eurostat; append-only, positional ids) ---
    {"domain": "Social Media", "name": "Individuals in Social Networks", "unit": "%", "api_code": "isoc_ci_ac_i", "source_priority": 1,
     "definition": "Individuals using the internet for participating in social networks, % of all individuals (Eurostat isoc_ci_ac_i, indic_is=I_IUSNET, ind_type=IND_TOTAL)."},
    {"domain": "Social Media", "name": "Youth in Social Networks (16-24)", "unit": "%", "api_code": "isoc_ci_ac_i#Y16_24", "source_priority": 1,
     "definition": "Individuals aged 16-24 using the internet for participating in social networks, % of that age group (Eurostat isoc_ci_ac_i, indic_is=I_IUSNET, ind_type=Y16_24)."},
    {"domain": "Social Media", "name": "Enterprises Using Social Media", "unit": "%", "api_code": "isoc_cismt", "source_priority": 1,
     "definition": "Enterprises (10+ persons employed, business economy) using any social media, % of enterprises (Eurostat isoc_cismt, indic_is=E_SM1_ANY, size_emp=GE10)."},
```

- [ ] **Step 5: Add World Bank self-maps**

In `src/eurodata/sources/world_bank.py`, append inside `WB_CODES` (after the v3 Startups block, before the closing `}`):

```python
        # 2026-07-15: Health
        "SH.XPD.CHEX.GD.ZS": "SH.XPD.CHEX.GD.ZS",  # Current health exp, % GDP
        "SH.MED.PHYS.ZS": "SH.MED.PHYS.ZS",        # Physicians /1k
        "SH.MED.BEDS.ZS": "SH.MED.BEDS.ZS",        # Hospital beds /1k
        "SH.XPD.OOPC.CH.ZS": "SH.XPD.OOPC.CH.ZS",  # Out-of-pocket, % of CHE
        "SH.IMM.MEAS": "SH.IMM.MEAS",              # Measles immunization %
        "SP.DYN.IMRT.IN": "SP.DYN.IMRT.IN",        # Infant mortality /1k
        "SH.STA.SUIC.P5": "SH.STA.SUIC.P5",        # Suicide mortality /100k
```

- [ ] **Step 6: Add Eurostat series pins**

In `src/eurodata/sources/eurostat.py`, append inside `SERIES_PARAMS` (before the closing `}`):

```python
    # 2026-07-15: Social Media (usage)
    # Individuals participating in social networks, % of all individuals
    "isoc_ci_ac_i": {"indic_is": "I_IUSNET", "unit": "PC_IND",
                     "ind_type": "IND_TOTAL"},
    # Same series for the 16-24 age group; shares the dataset via #-suffix
    "isoc_ci_ac_i#Y16_24": {"indic_is": "I_IUSNET", "unit": "PC_IND",
                            "ind_type": "Y16_24"},
    # Enterprises (10+ employed) using any social media, % of enterprises;
    # biennial coverage (2014, 2015, 2017, 2019, 2021, 2023, 2025)
    "isoc_cismt": {"indic_is": "E_SM1_ANY", "unit": "PC_ENT",
                   "size_emp": "GE10", "nace_r2": "C10-S951_X_K"},
```

- [ ] **Step 7: Run the full suite to verify green**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: PASS — all tests green (previously-failing count/name assertions now satisfied; no regressions).

- [ ] **Step 8: Commit**

```bash
git add src/eurodata/reference/catalog.py src/eurodata/sources/world_bank.py \
        src/eurodata/sources/eurostat.py tests/test_seed.py tests/test_api.py \
        tests/test_graph_build.py
git commit -m "feat: Health & Social Media domains (9 domains, 47 indicators)

7 World Bank health series + 3 Eurostat social-media usage series, all
api_codes verified live against source APIs. Youth cut shares the
isoc_ci_ac_i dataset via #-suffix.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: DB rebuild + live ingestion + verification

Operational task: load real rows for the new indicators and verify end-to-end. Not a code commit.

**Files:** none modified (writes `data/eurodata.duckdb` and `data/raw/`).

- [ ] **Step 1: Ensure no process holds the write-lock**

Run: `lsof data/eurodata.duckdb 2>/dev/null || echo "no holders"`
If a uvicorn/python process is listed, stop it (note its PID and `kill` it). The DB must be free before the next step.

- [ ] **Step 2: Reseed the schema/catalog**

Run: `PYTHONPATH=src .venv/bin/python scripts/init_db.py`
Expected: prints `Initialized DB with <N> countries.` `seed_all` also UPDATEs indicator metadata, so the two new domains and ten indicators land in the `domain`/`indicator` tables.

- [ ] **Step 3: Run ingestion (World Bank + Eurostat + others)**

Run: `PYTHONPATH=src .venv/bin/python scripts/run_ingestion.py`
Expected: per-source record counts print. World Bank was intermittently timing out on 2026-07-15 — if `World Bank` reports 0 or far fewer records than usual, it is logged to `ingestion_error` and can be retried (rerun this step, or `run_source 'World Bank'`) without re-fetching the others. Eurostat may 307-throttle; the fetcher backs off and retries automatically.

- [ ] **Step 4: Verify new rows exist per domain**

Run:
```bash
PYTHONPATH=src .venv/bin/python -c "
import eurodata as ed
for ind in ['Health Expenditure (% GDP)', 'Infant Mortality', 'Individuals in Social Networks', 'Enterprises Using Social Media']:
    df = ed.statistic_best(indicator=ind)
    print(f'{ind:35} rows={len(df):5} countries={df[\"iso3\"].nunique() if len(df) else 0}')
"
```
Expected: each indicator prints a non-zero row count across multiple countries. (If the World Bank health rows are 0 due to the API outage, retry Step 3 for World Bank before treating it as a failure.)

- [ ] **Step 5: Verify the web backend catalog exposes both domains**

Start the backend read-only and query the catalog:
```bash
PYTHONPATH=src .venv/bin/python -m uvicorn web.backend.main:app --port 8000 &
sleep 4
curl -s localhost:8000/api/domains | python -m json.tool | grep -E "Health|Social Media"
kill %1
```
Expected: both `Health` and `Social Media` appear in the domains response. (Adjust the endpoint path if the backend exposes domains under a different route — confirm against `web/backend/main.py`.)

- [ ] **Step 6: Final full-suite check**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q`
Expected: PASS — confirms the rebuilt DB still satisfies all catalog-count and behavior tests.

---

## Self-Review notes

- **Spec coverage:** 2 domains (Task 2 Step 3) ✓; 7 Health indicators + 3 Social Media (Task 2 Step 4) ✓; WB_CODES (Step 5) ✓; SERIES_PARAMS + `#`-split (Task 1 + Task 2 Step 6) ✓; test count bumps in all three files (Task 2 Step 1) ✓; DB rebuild + ingestion + verification (Task 3) ✓; out-of-scope items untouched ✓.
- **Type consistency:** `dataset_id` defined in Task 1, consumed in Task 1 `fetch`; api_codes `isoc_ci_ac_i`, `isoc_ci_ac_i#Y16_24`, `isoc_cismt` identical across catalog (Task 2 Step 4) and `SERIES_PARAMS` (Task 2 Step 6). Counts 9/47 consistent across catalog and all three test files.
- **No placeholders:** every code/edit step shows exact content and exact commands.
