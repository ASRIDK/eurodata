import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Chat",
  description: "Ask the eurodata AI analyst questions over official European statistics; every answer is grounded in the dataset.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
