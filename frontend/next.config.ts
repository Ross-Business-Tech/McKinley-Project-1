import type { NextConfig } from "next";

// NEXT_STATIC_EXPORT=1 produces a static site in `out/` for the team's here.now pipeline
// (root `npm run build` -> `dist/`). Local development uses the normal Next.js server.
const staticExport = process.env.NEXT_STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  // Partial prerendering is not supported by static export, so it is enabled only for the server build.
  ...(staticExport
    ? // trailingSlash: /staff is exported as staff/index.html, which every static host (and SPA mode) serves.
      { output: "export" as const, images: { unoptimized: true }, trailingSlash: true }
    : { cacheComponents: true, partialPrefetching: true }),
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
