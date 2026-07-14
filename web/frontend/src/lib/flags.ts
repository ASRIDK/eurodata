// Generated from /api/countries — the 50-country catalog changes rarely,
// so it is baked in rather than fetched.

export const COUNTRIES: Record<string, { iso2: string; name: string }> = {
  ALB: { iso2: "AL", name: "Albania" },
  AND: { iso2: "AD", name: "Andorra" },
  ARM: { iso2: "AM", name: "Armenia" },
  AUT: { iso2: "AT", name: "Austria" },
  AZE: { iso2: "AZ", name: "Azerbaijan" },
  BLR: { iso2: "BY", name: "Belarus" },
  BEL: { iso2: "BE", name: "Belgium" },
  BIH: { iso2: "BA", name: "Bosnia and Herzegovina" },
  BGR: { iso2: "BG", name: "Bulgaria" },
  HRV: { iso2: "HR", name: "Croatia" },
  CYP: { iso2: "CY", name: "Cyprus" },
  CZE: { iso2: "CZ", name: "Czechia" },
  DNK: { iso2: "DK", name: "Denmark" },
  EST: { iso2: "EE", name: "Estonia" },
  FIN: { iso2: "FI", name: "Finland" },
  FRA: { iso2: "FR", name: "France" },
  GEO: { iso2: "GE", name: "Georgia" },
  DEU: { iso2: "DE", name: "Germany" },
  GRC: { iso2: "GR", name: "Greece" },
  HUN: { iso2: "HU", name: "Hungary" },
  ISL: { iso2: "IS", name: "Iceland" },
  IRL: { iso2: "IE", name: "Ireland" },
  ITA: { iso2: "IT", name: "Italy" },
  XKX: { iso2: "XK", name: "Kosovo" },
  LVA: { iso2: "LV", name: "Latvia" },
  LIE: { iso2: "LI", name: "Liechtenstein" },
  LTU: { iso2: "LT", name: "Lithuania" },
  LUX: { iso2: "LU", name: "Luxembourg" },
  MLT: { iso2: "MT", name: "Malta" },
  MDA: { iso2: "MD", name: "Moldova" },
  MCO: { iso2: "MC", name: "Monaco" },
  MNE: { iso2: "ME", name: "Montenegro" },
  NLD: { iso2: "NL", name: "Netherlands" },
  MKD: { iso2: "MK", name: "North Macedonia" },
  NOR: { iso2: "NO", name: "Norway" },
  POL: { iso2: "PL", name: "Poland" },
  PRT: { iso2: "PT", name: "Portugal" },
  ROU: { iso2: "RO", name: "Romania" },
  RUS: { iso2: "RU", name: "Russia" },
  SMR: { iso2: "SM", name: "San Marino" },
  SRB: { iso2: "RS", name: "Serbia" },
  SVK: { iso2: "SK", name: "Slovakia" },
  SVN: { iso2: "SI", name: "Slovenia" },
  ESP: { iso2: "ES", name: "Spain" },
  SWE: { iso2: "SE", name: "Sweden" },
  CHE: { iso2: "CH", name: "Switzerland" },
  TUR: { iso2: "TR", name: "Turkey" },
  UKR: { iso2: "UA", name: "Ukraine" },
  GBR: { iso2: "GB", name: "United Kingdom" },
  VAT: { iso2: "VA", name: "Vatican City" },
};

const NAME_TO_ISO3: Record<string, string> = Object.fromEntries(
  Object.entries(COUNTRIES).map(([iso3, c]) => [c.name, iso3]),
);

function lookup(value: unknown): { iso2: string; name: string } | undefined {
  const key = String(value);
  return COUNTRIES[key] ?? COUNTRIES[NAME_TO_ISO3[key]];
}

/** Real flag image URL (flagcdn.com) for an ISO-3 code or country name, or null. */
export function flagUrl(value: unknown, width: 20 | 40 | 80 = 40): string | null {
  const c = lookup(value);
  return c ? `https://flagcdn.com/w${width}/${c.iso2.toLowerCase()}.png` : null;
}

/** Display name for an ISO-3 code or country name ("FRA" -> "France"), or null. */
export function countryName(value: unknown): string | null {
  return lookup(value)?.name ?? null;
}
