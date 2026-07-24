"use client";

import type { CountryProfile, HeadlineFact, MoverFact } from "@/lib/api";

const ORD = ["th", "st", "nd", "rd"];
function ordinal(n: number): string {
  const v = n % 100;
  return n + (ORD[(v - 20) % 10] ?? ORD[v] ?? ORD[0]);
}

function fmt(value: number, unit: string | null): string {
  if (unit === "%") return `${value.toFixed(1)}%`;
  if (unit === "USD") {
    const a = Math.abs(value);
    if (a >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (a >= 1e9) return `$${(value / 1e9).toFixed(0)}B`;
    if (a >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
    return `$${value.toLocaleString()}`;
  }
  if (unit === "persons") {
    const a = Math.abs(value);
    if (a >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
    if (a >= 1e3) return `${(value / 1e3).toFixed(0)}k`;
    return value.toLocaleString();
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ""}`;
}

// A percentage-unit change is stated in points; anything else in its own unit.
function moverPhrase(m: MoverFact): string {
  const dir = m.change >= 0 ? "rose" : "fell";
  const mag =
    m.unit === "%"
      ? `${Math.abs(m.change).toFixed(1)}pp`
      : fmt(Math.abs(m.change), m.unit);
  // The percentile is what makes the claim honest: "most in Europe" only when
  // it really is, otherwise a softer framing.
  const rank =
    m.percentile >= 98
      ? m.change >= 0 ? " — the largest rise in Europe" : " — the steepest fall in Europe"
      : m.percentile >= 80
        ? m.change >= 0 ? ", among the largest rises in Europe" : ", among the steepest falls in Europe"
        : "";
  return `${m.indicator} ${dir} ${mag} (${m.from_year}–${m.to_year})${rank}`;
}

export function CountrySummary({ profile }: { profile: CountryProfile }) {
  const by = (name: string): HeadlineFact | undefined =>
    profile.headline.find((h) => h.indicator === name);
  const parts: string[] = [];

  const gdp = by("GDP");
  const pop = by("Population");
  if (gdp) {
    let s = `${profile.name} is the ${ordinal(gdp.rank)} largest of ${gdp.of} European economies by GDP (${fmt(gdp.value, gdp.unit)}, ${gdp.period})`;
    if (pop) s += `, with ${fmt(pop.value, pop.unit)} people`;
    parts.push(s + ".");
  } else if (pop) {
    parts.push(`${profile.name} has a population of ${fmt(pop.value, pop.unit)} (${pop.period}).`);
  }

  const current = profile.blocs.filter((b) => b.until_year == null);
  if (current.length) {
    const names = current
      .map((b) => (b.since_year ? `${b.name} since ${b.since_year}` : b.name))
      .join(", ");
    parts.push(`A member of ${names}.`);
  }

  // One headline vs the European median, for a sense of standing.
  const unemp = by("Unemployment Rate");
  if (unemp) {
    const rel =
      unemp.value > unemp.median ? "above" : unemp.value < unemp.median ? "below" : "at";
    parts.push(
      `Unemployment is ${fmt(unemp.value, unemp.unit)}, ${rel} the European median of ${fmt(unemp.median, unemp.unit)}.`,
    );
  }

  const { fastest_rising: rising, fastest_falling: falling } = profile;
  if (rising || falling) {
    const clauses: string[] = [];
    if (rising) clauses.push(moverPhrase(rising));
    if (falling) clauses.push(moverPhrase(falling));
    parts.push(
      `Across ${profile.n_indicators} tracked indicators, ${clauses.join("; ")}.`,
    );
  }

  if (!parts.length) {
    return (
      <p className="text-sm text-black/50 dark:text-white/50">
        Limited data is available for {profile.name}.
      </p>
    );
  }

  return (
    <p className="max-w-prose text-sm leading-relaxed text-black/70 dark:text-white/70">
      {parts.join(" ")}
    </p>
  );
}
