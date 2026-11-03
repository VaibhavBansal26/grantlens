/** @type {import("next").NextConfig} */
module.exports = {
  agentRules: false,
  // AI requests (building a review, checking fit) can take well over Next's 30 s default proxy timeout,
  // which would return a 500 to the browser for work the API had finished.
  experimental: { proxyTimeout: 150_000 },
  // The browser only talks to this origin; Next forwards /api/* to Flask, so the session
  // cookie stays same-origin (no CORS credentials, SameSite=Lax works).
  async rewrites() {
    const api = process.env.API_INTERNAL_URL ?? "http://localhost:5055";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};
