import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // Question crops are served by the API; proxy them so pages can use the API's relative /assets URLs.
  async rewrites() {
    return [{ source: "/assets/:path*", destination: `${API_URL}/assets/:path*` }];
  },
};

export default nextConfig;
