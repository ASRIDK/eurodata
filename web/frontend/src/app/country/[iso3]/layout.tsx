import type { Metadata } from "next";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ iso3: string }>;
}): Promise<Metadata> {
  const { iso3 } = await params;
  const code = (iso3 || "").toUpperCase();
  return {
    title: `${code} profile`,
    description: `Country profile for ${code}: indicators, bloc memberships, events and its own strongest indicator correlations.`,
  };
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
