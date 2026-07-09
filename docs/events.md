# Event layer

`event` rows are curated, dated European events for event-study analysis.
Seed data lives in `src/eurodata/reference/events.py`; every entry cites a
primary source URL.

## Schema

| Column | Meaning |
|--------|---------|
| `code` | Stable slug (idempotent seeding key), e.g. `covid-pandemic-2020` |
| `event_type` | `election`, `policy_change`, `ai_regulation`, `war_conflict`, `energy_shock`, `financial_crisis`, `pandemic`, `eu_membership`, `eurozone_membership`, `sanctions`, `major_technology_policy`, `technology_milestone` |
| `iso3` / `bloc_code` | Scope: one country, one bloc, or Europe/global (both NULL) |
| `start_date` / `end_date` | `end_date` NULL for point-in-time events |
| `confidence` | 1.0 = officially dated fact; 0.9 = accepted-but-fuzzy period boundaries |
| `tags`, `affected_domains` | Comma-separated; domains match the `domain` table |

## Scope resolution in `event_study`

- country event → that country
- bloc event → bloc members *as of the event year*
- global event → all countries

For each affected country the study compares the indicator mean over
`[year-window, year-1]` vs `[year, year+window]` and reports deltas.

```python
ed.event_study(indicator="Inflation (HICP)",
               event_type="energy_shock", window_years=3)
```

Interpretation caveats: windows overlap for nearby events, results are simple
before/after means (no counterfactual), and annual data hides within-year
dynamics. Treat outputs as descriptive, not causal.
