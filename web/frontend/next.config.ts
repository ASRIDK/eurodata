import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A stray package-lock.json in $HOME otherwise wins workspace-root inference.
  turbopack: { root: __dirname },
};

export default nextConfig;
