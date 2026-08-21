import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The production Ingress exposes the app below this prefix. The Docker
  // build sets RDHS_BASE_PATH; local Cloudflare/Sites builds keep the root.
  basePath: process.env.RDHS_BASE_PATH || "",
};

export default nextConfig;
