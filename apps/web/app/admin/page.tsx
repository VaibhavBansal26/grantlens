"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { API, SyncOverview, SyncParams, SyncRun, getJson, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const LABEL: Record<string, string> = { grants_gov: "Grants.gov (open funding calls)", nih_reporter: "NIH RePORTER (awards)", nsf: "NSF (awards)" };
const EVERY = [[6, "6 hours"], [12, "12 hours"], [24, "day"], [72, "3 days"], [168, "week"]] as const;

function describe(source: string, p: SyncParams): string {
  const parts = [LABEL[source]?.split(" (")[0] ?? source];
  if (p.query) parts.push(`“${p.query}”`);
  if (p.statuses) parts.push(p.statuses.replaceAll("|", " + "));
  if (p.days) parts.push(`last ${p.days} days`);
  parts.push(p.limit ? `up to ${p.limit}` : "all records");
  return parts.join(" · ");
}

function ago(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 1440) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} d ago`;
}

function progress(r: SyncRun): string {
  if (r.status === "queued") return "waiting to start";
  if (r.status === "running") return r.inserted + r.updated + r.unchanged > 0 ? `embedding… ${r.embedded} done` : `fetching… ${r.fetched} records`;
  if (r.status === "failed") return r.error ?? "failed";
  return `${r.inserted} new, ${r.updated} changed, ${r.unchanged} unchanged · ${r.embedded} embedded`;
}

export default function AdminPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<SyncOverview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("grants_gov");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState("200");
  const [days, setDays] = useState("30");
  const [statuses, setStatuses] = useState<string[]>(["posted", "forecasted"]);
  const [every, setEvery] = useState(24);

  const load = useCallback(() => getJson<SyncOverview>(`${API}/admin/sync`).then(setData).catch((e) => setError((e as Error).message)), []);

  useEffect(() => {
    if (!ready) return;
    if (!user) { router.replace("/login?next=/admin"); return; }
    if (!user.is_admin) { setError("This page is for administrators."); return; }
    load();
  }, [ready, user, router, load]);

  const active = data?.runs.some((r) => r.status === "queued" || r.status === "running") ?? false;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [active, load]);

  function params(): SyncParams {
    const p: SyncParams = {};
    if (query.trim()) p.query = query.trim();
    if (limit.trim()) p.limit = Number(limit);
    if (source === "grants_gov") { if (statuses.length) p.statuses = statuses.join("|"); }
    else if (days.trim()) p.days = Number(days);
    return p;
  }

  async function act(fn: () => Promise<unknown>) {
    setError(""); setBusy(true);
    try { await fn(); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (error && !data) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  const toggle = (s: string) => setStatuses((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  return (
    <>
      <h1>Load grants</h1>
      <p className="muted">
        {data.corpus.opportunities.toLocaleString()} funding opportunities and {data.corpus.awards.toLocaleString()} awards loaded
        {data.corpus.waiting_for_embedding > 0 && ` · ${data.corpus.waiting_for_embedding.toLocaleString()} still waiting to be embedded for meaning-based search`}
      </p>
      {error && <p className="error" role="alert">{error}</p>}

      <section className="result">
        <h3>What to load</h3>
        <p>
          <label>Source{" "}
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              {data.sources.map((s) => <option key={s} value={s}>{LABEL[s] ?? s}</option>)}
            </select>
          </label>
        </p>
        <p>
          <label>Keyword (optional){" "}
            <input value={query} maxLength={200} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. cancer" />
          </label>{" "}
          <label>Max records{" "}
            <input type="number" min={1} value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="all" style={{ width: 100 }} />
          </label>{" "}
          {source !== "grants_gov" && (
            <label>From the last (days){" "}
              <input type="number" min={1} value={days} onChange={(e) => setDays(e.target.value)} style={{ width: 80 }} />
            </label>
          )}
        </p>
        {source === "grants_gov" && (
          <p>{data.statuses.map((s) => (
            <label className="check" key={s} style={{ display: "inline-flex", marginRight: 14 }}>
              <input type="checkbox" checked={statuses.includes(s)} onChange={() => toggle(s)} /> {s}
            </label>
          ))}</p>
        )}
        <p className="muted">Leave “Max records” empty to load everything. Grants.gov fetches each grant’s details one by one, so a large load takes a long time; try 200 first.</p>
        <div className="actions">
          <button className="primary" disabled={busy || active} onClick={() => act(() => sendJson("POST", `${API}/admin/sync/run`, { source, params: params() }))}>
            {active ? "A load is running…" : "Load now"}
          </button>
          <span>or every{" "}
            <select value={every} onChange={(e) => setEvery(Number(e.target.value))}>
              {EVERY.map(([h, l]) => <option key={h} value={h}>{l}</option>)}
            </select>{" "}
            <button disabled={busy} onClick={() => act(() => sendJson("POST", `${API}/admin/sync/schedules`, { source, params: params(), interval_hours: every }))}>
              Schedule it
            </button>
          </span>
        </div>
      </section>

      <h2>Schedules</h2>
      {!data.scheduler && data.schedules.length > 0 && (
        <p className="error">No background worker is running, so schedules will not fire. Start one with <code>flask worker</code> (it runs automatically in the production stack).</p>
      )}
      {data.schedules.length === 0 && <p className="empty">No schedules. Use “Schedule it” above to repeat a load automatically.</p>}
      {data.schedules.map((s) => (
        <article className="result" key={s.id}>
          <strong>{describe(s.source, s.params)}</strong>
          <div className="meta">
            <span>every {EVERY.find(([h]) => h === s.interval_hours)?.[1] ?? `${s.interval_hours} hours`}</span>
            <span>last started {ago(s.last_run_at)}</span>
            <span>{s.enabled ? "on" : "paused"}</span>
          </div>
          <div className="actions">
            <button disabled={busy} onClick={() => act(() => sendJson("PATCH", `${API}/admin/sync/schedules/${s.id}`, { enabled: !s.enabled }))}>{s.enabled ? "Pause" : "Resume"}</button>
            <button disabled={busy} onClick={() => act(() => sendJson("DELETE", `${API}/admin/sync/schedules/${s.id}`))}>Delete</button>
          </div>
        </article>
      ))}

      <h2>Recent loads</h2>
      {data.runs.length === 0 && <p className="empty">Nothing loaded yet.</p>}
      {data.runs.map((r) => (
        <article className="result" key={r.id}>
          <strong>{describe(r.source, r.params)}</strong>
          <div className="meta">
            <span className={`badge ${r.status === "done" ? "posted" : r.status === "failed" ? "st-not_met" : "forecasted"}`}>{r.status}</span>
            <span>{r.trigger === "schedule" ? "scheduled" : "started by hand"}</span>
            <span>{ago(r.created_at)}</span>
          </div>
          <div className={r.status === "failed" ? "error" : "muted"}>{progress(r)}</div>
        </article>
      ))}
    </>
  );
}
