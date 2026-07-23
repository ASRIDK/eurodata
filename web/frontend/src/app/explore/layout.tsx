import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Explore",
  description: "Chart and compare European indicators across countries and regions, with forecasts, events and source provenance.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
