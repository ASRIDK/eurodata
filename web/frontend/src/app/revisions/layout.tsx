import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Revisions",
  description: "How official European statistics changed across data vintages: the largest revisions and most-revised indicators.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
