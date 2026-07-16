from __future__ import annotations

from eurodata.reference.countries import COUNTRIES
from eurodata.sources.base import BaseFetcher, Record
from eurodata.sources.registry import register

_EUROPE_ISO3 = {c["iso3"] for c in COUNTRIES}


def normalize_world_bank(rows: list[dict], indicator_code: str) -> list[Record]:
    out: list[Record] = []
    for row in rows:
        iso3 = row.get("countryiso3code")
        if iso3 not in _EUROPE_ISO3 or row.get("value") is None:
            continue
        try:
            year = int(str(row["date"])[:4])
            value = float(row["value"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Record(iso3=iso3, indicator_code=indicator_code, year=year, value=value))
    return out


@register
class WorldBankFetcher(BaseFetcher):
    source_name = "World Bank"
    # Eurostat api_code -> World Bank series (fallback coverage, all CC BY 4.0).
    # A few WB series are close proxies rather than exact matches for the
    # Eurostat concept; noted inline. Median Age (demo_pjanind) has no honest
    # WB equivalent, so it is left to Eurostat wiring.
    WB_CODES = {
        "demo_pjan": "SP.POP.TOTL",        # Population, total
        "nama_10_gdp": "NY.GDP.MKTP.CD",   # GDP (current US$)
        "sdg_08_10": "NY.GDP.PCAP.CD",     # GDP per capita (current US$)
        "prc_hicp_aind": "FP.CPI.TOTL.ZG", # CPI inflation (proxy for HICP)
        "une_rt_a": "SL.UEM.TOTL.ZS",      # Unemployment, % of labour force
        "isoc_ci_ifp_iu": "IT.NET.USER.ZS",     # Individuals using the internet, %
        "isoc_r_broad_h": "IT.NET.BBND.P2",     # Fixed broadband subs/100 (fallback proxy; Eurostat isoc_r_broad_h is primary)
        "nrg_ind_ren": "EG.FEC.RNEW.ZS",        # Renewable energy, % of final consumption
        "env_air_gge": "EN.GHG.ALL.MT.CE.AR5",  # Total GHG emissions (Mt CO2e)
        # v2 indicators: api_code in the catalog IS the World Bank series code.
        "GB.XPD.RSDV.GD.ZS": "GB.XPD.RSDV.GD.ZS",      # R&D expenditure, % GDP
        "SP.POP.SCIE.RD.P6": "SP.POP.SCIE.RD.P6",      # Researchers in R&D /1M
        "TX.VAL.TECH.MF.ZS": "TX.VAL.TECH.MF.ZS",      # High-tech exports %
        "IP.PAT.RESD": "IP.PAT.RESD",                  # Patent applications, residents
        "IP.JRN.ARTC.SC": "IP.JRN.ARTC.SC",            # Scientific journal articles
        "gov_10dd_edpt1": "GC.DOD.TOTL.GD.ZS",          # Central gov debt, % GDP (fallback proxy; Eurostat gov_10dd_edpt1 is primary)
        "NE.RSB.GNFS.ZS": "NE.RSB.GNFS.ZS",            # Trade balance, % GDP
        "BX.KLT.DINV.WD.GD.ZS": "BX.KLT.DINV.WD.GD.ZS",# FDI net inflows, % GDP
        "SP.DYN.TFRT.IN": "SP.DYN.TFRT.IN",            # Fertility rate
        "SP.DYN.LE00.IN": "SP.DYN.LE00.IN",            # Life expectancy
        "SP.URB.TOTL.IN.ZS": "SP.URB.TOTL.IN.ZS",      # Urban population %
        "SM.POP.NETM": "SM.POP.NETM",                  # Net migration
        "EN.GHG.CO2.PC.CE.AR5": "EN.GHG.CO2.PC.CE.AR5",# CO2 per capita
        "EG.IMP.CONS.ZS": "EG.IMP.CONS.ZS",            # Energy imports net, %
        # v3: Startups & Business
        "IC.BUS.NDNS.ZS": "IC.BUS.NDNS.ZS",            # New business density /1k 15-64
        "IC.BUS.NREG": "IC.BUS.NREG",                  # New businesses registered
        "SL.EMP.SELF.ZS": "SL.EMP.SELF.ZS",            # Self-employed, % of employment
        "FS.AST.PRVT.GD.ZS": "FS.AST.PRVT.GD.ZS",      # Private sector credit, % GDP
        # 2026-07-15: Health
        "SH.XPD.CHEX.GD.ZS": "SH.XPD.CHEX.GD.ZS",  # Current health exp, % GDP
        "SH.MED.PHYS.ZS": "SH.MED.PHYS.ZS",        # Physicians /1k
        "SH.MED.BEDS.ZS": "SH.MED.BEDS.ZS",        # Hospital beds /1k
        "SH.XPD.OOPC.CH.ZS": "SH.XPD.OOPC.CH.ZS",  # Out-of-pocket, % of CHE
        "SH.IMM.MEAS": "SH.IMM.MEAS",              # Measles immunization %
        "SP.DYN.IMRT.IN": "SP.DYN.IMRT.IN",        # Infant mortality /1k
        "SH.STA.SUIC.P5": "SH.STA.SUIC.P5",        # Suicide mortality /100k
    }

    def fetch(self, start_year: int) -> list[Record]:
        import datetime as dt

        import wbgapi as wb  # lazy import

        records: list[Record] = []
        economies = [c["iso3"] for c in COUNTRIES]
        end_year = dt.date.today().year + 1  # include the current year
        for eu_code, wb_code in self.WB_CODES.items():
            try:
                df = wb.data.DataFrame(wb_code, economies, range(start_year, end_year),
                                       labels=False).reset_index()
                rows = []
                for _, r in df.iterrows():
                    for col in df.columns:
                        if str(col).startswith("YR"):
                            rows.append({"countryiso3code": r["economy"],
                                         "date": str(col)[2:], "value": r[col]})
                records.extend(normalize_world_bank(rows, eu_code))
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                self.errors.append((wb_code, str(exc)))
        return records
