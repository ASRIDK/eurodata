import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Ranking",
  description: "Rank European countries by any indicator on its most recent value, Europe-wide or within a bloc.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
