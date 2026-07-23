import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Correlations",
  description: "Growth-rate correlations between European indicators, pooled across countries and corrected for multiple comparisons.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
