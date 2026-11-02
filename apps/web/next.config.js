/** @type {import("next").NextConfig} */
module.exports = {
  agentRules: false,
  // The browser only talks to this origin; Next forwards /api/* to Flask, so the session
  // cookie stays same-origin (no CORS credentials, SameSite=Lax works).
  async rewrites() {
    const api = process.env.API_INTERNAL_URL ?? "http://localhost:5055";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};
