// Marker catalog for the home-page globe: every capital of the 50 countries
// in the eurodata geography table, plus six non-capital economic hubs (which
// share their country's iso3 so clicking them selects that country).
// `labeled` limits the HTML label overlay to the major cities — all markers
// stay clickable. `id` is the cobe anchor id (--cobe-{id} / --cobe-visible-{id}).

export type CountryMarker = {
  id: string;
  iso3: string;
  iso2: string;
  name: string; // country display name
  city: string; // capital, or hub city name
  location: [number, number]; // [lat, lng]
  size: number;
  labeled?: boolean;
};

export const EUROPEAN_MARKERS: CountryMarker[] = [
  // -- capitals ------------------------------------------------------------
  { id: "tirana", iso3: "ALB", iso2: "AL", name: "Albania", city: "Tirana", location: [41.33, 19.82], size: 0.035 },
  { id: "andorra", iso3: "AND", iso2: "AD", name: "Andorra", city: "Andorra la Vella", location: [42.51, 1.52], size: 0.02 },
  { id: "yerevan", iso3: "ARM", iso2: "AM", name: "Armenia", city: "Yerevan", location: [40.18, 44.51], size: 0.035 },
  { id: "vienna", iso3: "AUT", iso2: "AT", name: "Austria", city: "Vienna", location: [48.21, 16.37], size: 0.05, labeled: true },
  { id: "baku", iso3: "AZE", iso2: "AZ", name: "Azerbaijan", city: "Baku", location: [40.41, 49.87], size: 0.035 },
  { id: "minsk", iso3: "BLR", iso2: "BY", name: "Belarus", city: "Minsk", location: [53.9, 27.56], size: 0.04 },
  { id: "brussels", iso3: "BEL", iso2: "BE", name: "Belgium", city: "Brussels", location: [50.85, 4.35], size: 0.05 },
  { id: "sarajevo", iso3: "BIH", iso2: "BA", name: "Bosnia and Herzegovina", city: "Sarajevo", location: [43.86, 18.41], size: 0.035 },
  { id: "sofia", iso3: "BGR", iso2: "BG", name: "Bulgaria", city: "Sofia", location: [42.7, 23.32], size: 0.04 },
  { id: "zagreb", iso3: "HRV", iso2: "HR", name: "Croatia", city: "Zagreb", location: [45.81, 15.98], size: 0.035 },
  { id: "nicosia", iso3: "CYP", iso2: "CY", name: "Cyprus", city: "Nicosia", location: [35.17, 33.36], size: 0.03 },
  { id: "prague", iso3: "CZE", iso2: "CZ", name: "Czechia", city: "Prague", location: [50.09, 14.42], size: 0.05 },
  { id: "copenhagen", iso3: "DNK", iso2: "DK", name: "Denmark", city: "Copenhagen", location: [55.68, 12.57], size: 0.045 },
  { id: "tallinn", iso3: "EST", iso2: "EE", name: "Estonia", city: "Tallinn", location: [59.44, 24.75], size: 0.035 },
  { id: "helsinki", iso3: "FIN", iso2: "FI", name: "Finland", city: "Helsinki", location: [60.17, 24.94], size: 0.045, labeled: true },
  { id: "paris", iso3: "FRA", iso2: "FR", name: "France", city: "Paris", location: [48.86, 2.35], size: 0.06, labeled: true },
  { id: "tbilisi", iso3: "GEO", iso2: "GE", name: "Georgia", city: "Tbilisi", location: [41.72, 44.79], size: 0.035 },
  { id: "berlin", iso3: "DEU", iso2: "DE", name: "Germany", city: "Berlin", location: [52.52, 13.4], size: 0.06, labeled: true },
  { id: "athens", iso3: "GRC", iso2: "GR", name: "Greece", city: "Athens", location: [37.98, 23.73], size: 0.045, labeled: true },
  { id: "budapest", iso3: "HUN", iso2: "HU", name: "Hungary", city: "Budapest", location: [47.5, 19.04], size: 0.045 },
  { id: "reykjavik", iso3: "ISL", iso2: "IS", name: "Iceland", city: "Reykjavík", location: [64.15, -21.94], size: 0.035 },
  { id: "dublin", iso3: "IRL", iso2: "IE", name: "Ireland", city: "Dublin", location: [53.35, -6.26], size: 0.045, labeled: true },
  { id: "rome", iso3: "ITA", iso2: "IT", name: "Italy", city: "Rome", location: [41.9, 12.5], size: 0.06, labeled: true },
  { id: "pristina", iso3: "XKX", iso2: "XK", name: "Kosovo", city: "Pristina", location: [42.66, 21.17], size: 0.03 },
  { id: "riga", iso3: "LVA", iso2: "LV", name: "Latvia", city: "Riga", location: [56.95, 24.11], size: 0.035 },
  { id: "vaduz", iso3: "LIE", iso2: "LI", name: "Liechtenstein", city: "Vaduz", location: [47.14, 9.52], size: 0.02 },
  { id: "vilnius", iso3: "LTU", iso2: "LT", name: "Lithuania", city: "Vilnius", location: [54.69, 25.28], size: 0.035 },
  { id: "luxembourg", iso3: "LUX", iso2: "LU", name: "Luxembourg", city: "Luxembourg", location: [49.61, 6.13], size: 0.03 },
  { id: "valletta", iso3: "MLT", iso2: "MT", name: "Malta", city: "Valletta", location: [35.9, 14.51], size: 0.025 },
  { id: "chisinau", iso3: "MDA", iso2: "MD", name: "Moldova", city: "Chișinău", location: [47.01, 28.86], size: 0.035 },
  { id: "monaco", iso3: "MCO", iso2: "MC", name: "Monaco", city: "Monaco", location: [43.74, 7.42], size: 0.02 },
  { id: "podgorica", iso3: "MNE", iso2: "ME", name: "Montenegro", city: "Podgorica", location: [42.44, 19.26], size: 0.03 },
  { id: "amsterdam", iso3: "NLD", iso2: "NL", name: "Netherlands", city: "Amsterdam", location: [52.37, 4.9], size: 0.05, labeled: true },
  { id: "skopje", iso3: "MKD", iso2: "MK", name: "North Macedonia", city: "Skopje", location: [42.0, 21.43], size: 0.03 },
  { id: "oslo", iso3: "NOR", iso2: "NO", name: "Norway", city: "Oslo", location: [59.91, 10.75], size: 0.045, labeled: true },
  { id: "warsaw", iso3: "POL", iso2: "PL", name: "Poland", city: "Warsaw", location: [52.23, 21.01], size: 0.05, labeled: true },
  { id: "lisbon", iso3: "PRT", iso2: "PT", name: "Portugal", city: "Lisbon", location: [38.72, -9.14], size: 0.045, labeled: true },
  { id: "bucharest", iso3: "ROU", iso2: "RO", name: "Romania", city: "Bucharest", location: [44.43, 26.1], size: 0.045 },
  { id: "moscow", iso3: "RUS", iso2: "RU", name: "Russia", city: "Moscow", location: [55.76, 37.62], size: 0.05, labeled: true },
  { id: "sanmarino", iso3: "SMR", iso2: "SM", name: "San Marino", city: "San Marino", location: [43.94, 12.45], size: 0.02 },
  { id: "belgrade", iso3: "SRB", iso2: "RS", name: "Serbia", city: "Belgrade", location: [44.79, 20.45], size: 0.04 },
  { id: "bratislava", iso3: "SVK", iso2: "SK", name: "Slovakia", city: "Bratislava", location: [48.15, 17.11], size: 0.035 },
  { id: "ljubljana", iso3: "SVN", iso2: "SI", name: "Slovenia", city: "Ljubljana", location: [46.06, 14.51], size: 0.03 },
  { id: "madrid", iso3: "ESP", iso2: "ES", name: "Spain", city: "Madrid", location: [40.42, -3.7], size: 0.06, labeled: true },
  { id: "stockholm", iso3: "SWE", iso2: "SE", name: "Sweden", city: "Stockholm", location: [59.33, 18.07], size: 0.045, labeled: true },
  { id: "bern", iso3: "CHE", iso2: "CH", name: "Switzerland", city: "Bern", location: [46.95, 7.45], size: 0.04 },
  { id: "ankara", iso3: "TUR", iso2: "TR", name: "Turkey", city: "Ankara", location: [39.93, 32.87], size: 0.05, labeled: true },
  { id: "kyiv", iso3: "UKR", iso2: "UA", name: "Ukraine", city: "Kyiv", location: [50.45, 30.52], size: 0.05, labeled: true },
  { id: "london", iso3: "GBR", iso2: "GB", name: "United Kingdom", city: "London", location: [51.51, -0.13], size: 0.06, labeled: true },
  { id: "vatican", iso3: "VAT", iso2: "VA", name: "Vatican City", city: "Vatican City", location: [41.9, 12.45], size: 0.02 },
  // -- economic hubs (non-capitals; select their country) --------------------
  { id: "frankfurt", iso3: "DEU", iso2: "DE", name: "Germany", city: "Frankfurt", location: [50.11, 8.68], size: 0.04, labeled: true },
  { id: "munich", iso3: "DEU", iso2: "DE", name: "Germany", city: "Munich", location: [48.14, 11.58], size: 0.04 },
  { id: "hamburg", iso3: "DEU", iso2: "DE", name: "Germany", city: "Hamburg", location: [53.55, 9.99], size: 0.04 },
  { id: "milan", iso3: "ITA", iso2: "IT", name: "Italy", city: "Milan", location: [45.46, 9.19], size: 0.04, labeled: true },
  { id: "barcelona", iso3: "ESP", iso2: "ES", name: "Spain", city: "Barcelona", location: [41.39, 2.17], size: 0.04 },
  { id: "zurich", iso3: "CHE", iso2: "CH", name: "Switzerland", city: "Zürich", location: [47.37, 8.54], size: 0.04, labeled: true },
];
