BLOCS = [
    {"code": "EU", "name": "European Union"},
    {"code": "EUROZONE", "name": "Eurozone"},
    {"code": "SCHENGEN", "name": "Schengen Area"},
    {"code": "EFTA", "name": "European Free Trade Association"},
    {"code": "EEA", "name": "European Economic Area"},
]

# (iso3, bloc_code, since_year, until_year|None)
MEMBERSHIPS = [
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
    ("DEU", "EUROZONE", 1999, None), ("FRA", "EUROZONE", 1999, None),
    ("HRV", "EUROZONE", 2023, None),
    ("NOR", "EFTA", 1960, None), ("CHE", "EFTA", 1960, None),
    ("ISL", "EFTA", 1970, None), ("LIE", "EFTA", 1991, None),
    ("NOR", "EEA", 1994, None), ("ISL", "EEA", 1994, None), ("LIE", "EEA", 1995, None),
]
