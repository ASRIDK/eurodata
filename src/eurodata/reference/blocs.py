BLOCS = [
    {"code": "EU", "name": "European Union"},
    {"code": "EUROZONE", "name": "Eurozone"},
    {"code": "SCHENGEN", "name": "Schengen Area"},
    {"code": "EFTA", "name": "European Free Trade Association"},
    {"code": "EEA", "name": "European Economic Area"},
    {"code": "NATO", "name": "NATO (European members)"},
]

# (iso3, bloc_code, since_year, until_year|None)
# since_year is the year membership took effect. A row with until_year set is
# historical (e.g. GBR left the EU in 2020); queries about current membership
# must filter `until_year IS NULL`.
MEMBERSHIPS = [
    # --- European Union (27 current + GBR 1973-2020) ---
    ("DEU", "EU", 1958, None), ("FRA", "EU", 1958, None), ("ITA", "EU", 1958, None),
    ("NLD", "EU", 1958, None), ("BEL", "EU", 1958, None), ("LUX", "EU", 1958, None),
    ("DNK", "EU", 1973, None), ("IRL", "EU", 1973, None), ("GRC", "EU", 1981, None),
    ("ESP", "EU", 1986, None), ("PRT", "EU", 1986, None), ("AUT", "EU", 1995, None),
    ("FIN", "EU", 1995, None), ("SWE", "EU", 1995, None), ("CZE", "EU", 2004, None),
    ("EST", "EU", 2004, None), ("HUN", "EU", 2004, None), ("LVA", "EU", 2004, None),
    ("LTU", "EU", 2004, None), ("MLT", "EU", 2004, None), ("POL", "EU", 2004, None),
    ("SVK", "EU", 2004, None), ("SVN", "EU", 2004, None), ("CYP", "EU", 2004, None),
    ("BGR", "EU", 2007, None), ("ROU", "EU", 2007, None), ("HRV", "EU", 2013, None),
    ("GBR", "EU", 1973, 2020),

    # --- Eurozone (euro adoption year; 21 members incl. BGR from 2026) ---
    ("AUT", "EUROZONE", 1999, None), ("BEL", "EUROZONE", 1999, None),
    ("DEU", "EUROZONE", 1999, None), ("ESP", "EUROZONE", 1999, None),
    ("FIN", "EUROZONE", 1999, None), ("FRA", "EUROZONE", 1999, None),
    ("IRL", "EUROZONE", 1999, None), ("ITA", "EUROZONE", 1999, None),
    ("LUX", "EUROZONE", 1999, None), ("NLD", "EUROZONE", 1999, None),
    ("PRT", "EUROZONE", 1999, None), ("GRC", "EUROZONE", 2001, None),
    ("SVN", "EUROZONE", 2007, None), ("CYP", "EUROZONE", 2008, None),
    ("MLT", "EUROZONE", 2008, None), ("SVK", "EUROZONE", 2009, None),
    ("EST", "EUROZONE", 2011, None), ("LVA", "EUROZONE", 2014, None),
    ("LTU", "EUROZONE", 2015, None), ("HRV", "EUROZONE", 2023, None),
    ("BGR", "EUROZONE", 2026, None),

    # --- Schengen Area (year internal border checks were abolished) ---
    ("BEL", "SCHENGEN", 1995, None), ("DEU", "SCHENGEN", 1995, None),
    ("ESP", "SCHENGEN", 1995, None), ("FRA", "SCHENGEN", 1995, None),
    ("LUX", "SCHENGEN", 1995, None), ("NLD", "SCHENGEN", 1995, None),
    ("PRT", "SCHENGEN", 1995, None), ("ITA", "SCHENGEN", 1997, None),
    ("AUT", "SCHENGEN", 1997, None), ("GRC", "SCHENGEN", 2000, None),
    ("DNK", "SCHENGEN", 2001, None), ("FIN", "SCHENGEN", 2001, None),
    ("SWE", "SCHENGEN", 2001, None), ("ISL", "SCHENGEN", 2001, None),
    ("NOR", "SCHENGEN", 2001, None), ("CZE", "SCHENGEN", 2007, None),
    ("EST", "SCHENGEN", 2007, None), ("HUN", "SCHENGEN", 2007, None),
    ("LVA", "SCHENGEN", 2007, None), ("LTU", "SCHENGEN", 2007, None),
    ("MLT", "SCHENGEN", 2007, None), ("POL", "SCHENGEN", 2007, None),
    ("SVK", "SCHENGEN", 2007, None), ("SVN", "SCHENGEN", 2007, None),
    ("CHE", "SCHENGEN", 2008, None), ("LIE", "SCHENGEN", 2011, None),
    ("HRV", "SCHENGEN", 2023, None), ("BGR", "SCHENGEN", 2025, None),
    ("ROU", "SCHENGEN", 2025, None),

    # --- EFTA ---
    ("NOR", "EFTA", 1960, None), ("CHE", "EFTA", 1960, None),
    ("ISL", "EFTA", 1970, None), ("LIE", "EFTA", 1991, None),

    # --- EEA (EFTA side only; EU members participate via the EU) ---
    ("NOR", "EEA", 1994, None), ("ISL", "EEA", 1994, None), ("LIE", "EEA", 1995, None),

    # --- NATO (European members, accession year) ---
    ("BEL", "NATO", 1949, None), ("DNK", "NATO", 1949, None),
    ("FRA", "NATO", 1949, None), ("ISL", "NATO", 1949, None),
    ("ITA", "NATO", 1949, None), ("LUX", "NATO", 1949, None),
    ("NLD", "NATO", 1949, None), ("NOR", "NATO", 1949, None),
    ("PRT", "NATO", 1949, None), ("GBR", "NATO", 1949, None),
    ("GRC", "NATO", 1952, None), ("TUR", "NATO", 1952, None),
    ("DEU", "NATO", 1955, None), ("ESP", "NATO", 1982, None),
    ("CZE", "NATO", 1999, None), ("HUN", "NATO", 1999, None),
    ("POL", "NATO", 1999, None), ("BGR", "NATO", 2004, None),
    ("EST", "NATO", 2004, None), ("LVA", "NATO", 2004, None),
    ("LTU", "NATO", 2004, None), ("ROU", "NATO", 2004, None),
    ("SVK", "NATO", 2004, None), ("SVN", "NATO", 2004, None),
    ("ALB", "NATO", 2009, None), ("HRV", "NATO", 2009, None),
    ("MNE", "NATO", 2017, None), ("MKD", "NATO", 2020, None),
    ("FIN", "NATO", 2023, None), ("SWE", "NATO", 2024, None),
]
