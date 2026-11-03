"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API, ApiError, Facets, Hit, SearchParams, getJson, money, searchUrl, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import WatchButton from "./WatchButton";

// Most of the corpus is closed or archived (91% at the time of writing), and people searching for funding
// want grants they can still apply to. Those are the default; older ones are one switch away.
const OPEN = ["posted", "forecasted"];
const ALL = [...OPEN, "closed", "archived"];
const EMPTY: SearchParams = { q: "", mode: "hybrid", status: OPEN, agency: "", closesAfter: "", minAmount: "" };
const includesOld = (status: string[]) => status.includes("closed") || status.includes("archived");

function whyMatched(h: Hit): string {
  const parts = [];
  if (h.ranks.bm25) parts.push(`keyword #${h.ranks.bm25}`);
  if (h.ranks.dense) parts.push(`semantic #${h.ranks.dense}`);
  return parts.join(" · ");
}

export default function SearchPage() {
  const [p, setP] = useState<SearchParams>(EMPTY);
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    getJson<Facets>(`${API}/facets`).then(setFacets).catch(() => {});
    const u = new URLSearchParams(window.location.search);
    if (u.get("q")) {
      const init: SearchParams = {
        q: u.get("q") ?? "", mode: (u.get("mode") as SearchParams["mode"]) ?? "hybrid",
        status: u.getAll("status").length ? u.getAll("status") : OPEN, agency: u.get("agency") ?? "",
        closesAfter: u.get("closes_after") ?? "", minAmount: u.get("min_amount") ?? "",
      };
      setP(init);
      run(init);
    }
  }, []);

  async function run(params: SearchParams) {
    if (!params.q.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await getJson<{ results: Hit[] }>(searchUrl(params));
      setHits(data.results);
      const u = searchUrl(params).split("?")[1];
      window.history.replaceState(null, "", `?${u}`);
    } catch (e) {
      setError(`Search failed (${(e as Error).message}). Is the API running at ${API}?`);
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    if (!user) { router.push(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`); return; }
    const name = window.prompt("Name this search", p.q.slice(0, 60));
    if (!name?.trim()) return;
    const params: Record<string, string | string[]> = { q: p.q, mode: p.mode, status: p.status };
    if (p.agency) params.agency = p.agency;
    if (p.closesAfter) params.closes_after = p.closesAfter;
    if (p.minAmount) params.min_amount = p.minAmount;
    try {
      await sendJson("POST", `${API}/saved-searches`, { name, params });
      setNotice("Saved. You can find it under Saved searches.");
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "Could not save this search.");
    }
  }

  const set = <K extends keyof SearchParams>(k: K, v: SearchParams[K]) => setP((s) => ({ ...s, [k]: v }));
  const older = (facets?.statuses ?? []).filter((x) => x.value === "closed" || x.value === "archived").reduce((n, x) => n + x.count, 0);
  const withOld = includesOld(p.status);
  // Changing the switch re-runs the current search at once, so the results always match what is shown.
  function setOld(on: boolean) {
    const next = { ...p, status: on ? ALL : OPEN };
    setP(next);
    if (p.q.trim()) run(next);
  }

  return (
    <>
      <form className="searchbar" onSubmit={(e) => { e.preventDefault(); run(p); }}>
        <input
          aria-label="Search grants" placeholder="e.g. early-career funding for AI in cancer imaging"
          value={p.q} onChange={(e) => set("q", e.target.value)} autoFocus
        />
        <button className="primary" disabled={loading || !p.q.trim()}>{loading ? "Searching…" : "Search"}</button>
      </form>

      <div className="filters">
        <label className="check">
          <input type="checkbox" checked={withOld} onChange={(e) => setOld(e.target.checked)} />
          Include closed and archived grants{older > 0 ? ` (${older.toLocaleString("en-US")} more)` : ""}
        </label>
        <label>Agency
          <select value={p.agency} onChange={(e) => set("agency", e.target.value)}>
            <option value="">Any</option>
            {facets?.agencies.map((a) => <option key={a.value} value={a.value}>{a.value} ({a.count})</option>)}
          </select>
        </label>
        <label>Closes on/after
          <input type="date" value={p.closesAfter} onChange={(e) => set("closesAfter", e.target.value)} />
        </label>
        <label>Award of at least ($)
          <input type="number" min={0} step={10000} value={p.minAmount} onChange={(e) => set("minAmount", e.target.value)} />
        </label>
        <label>Method
          <select value={p.mode} onChange={(e) => set("mode", e.target.value as SearchParams["mode"])}>
            <option value="hybrid">Hybrid (recommended)</option>
            <option value="bm25">Keyword only</option>
            <option value="dense">Semantic only</option>
          </select>
        </label>
      </div>

      {error && <p className="error">{error}</p>}
      {hits && hits.length > 0 && (
        <p className="actions"><button className="link" onClick={save}>Save this search</button>{notice && <span className="muted">{notice}</span>}</p>
      )}
      {hits && hits.length === 0 && (
        <p className="empty">
          No grants matched. Try fewer filters{!withOld && older > 0 ? <> or <button className="link" onClick={() => setOld(true)}>include closed and archived grants</button></> : ""}.
        </p>
      )}
      {hits && hits.length > 0 && !withOld && <p className="muted">Showing grants you can still apply to (open or forecasted).</p>}
      {hits?.map((h) => (
        <article className="result" key={h.id}>
          <h3><Link href={`/opportunity/${h.id}`}>{h.title}</Link></h3>
          <div className="meta">
            {h.status && <span className={`badge ${h.status}`}>{h.status}</span>}
            {h.agency && <span>{h.agency}</span>}
            <span>{h.close_date ? `closes ${h.close_date}` : "no close date listed"}</span>
            {h.amount_max != null && <span>up to {money(h.amount_max)}</span>}
          </div>
          <p className="snippet">{h.snippet}</p>
          <div className="why">matched by {whyMatched(h)}</div>
          <div className="actions"><WatchButton id={h.id} /></div>
        </article>
      ))}
    </>
  );
}
