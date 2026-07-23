import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Events",
  description: "A curated timeline of European crises, memberships and policy milestones, with before/after event studies.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
