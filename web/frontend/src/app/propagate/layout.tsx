import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Propagate",
  description:
    "Trace how a shock to one European indicator ripples through the others, along the correlation graph.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
