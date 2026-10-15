import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page reads the beatcut folder at request time; nothing here is worth caching.
  cacheComponents: false,
  serverExternalPackages: ["@anthropic-ai/claude-agent-sdk"],
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
