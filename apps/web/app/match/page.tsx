"use client";

import Link from "next/link";
import { useState } from "react";
import { API, MatchResponse, money, sendJson } from "@/lib/api";
import WatchButton from "../WatchButton";

const ORCID = /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/;

export default function MatchPage() {
  const [how, setHow] = useState<"text" | "orcid">("text");
  const [text, setText] = useState("");
  const [orcid, setOrcid] = useState("");
  const [data, setData] = useState<MatchResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const ready = how === "text" ? text.trim().length >= 20 : ORCID.test(orcid.trim());

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setData(null);
    try {
      setData(await sendJson<MatchResponse>("POST", `${API}/match`, how === "text" ? { text } : { orcid: orcid.trim() }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h1>Find grants for my work</h1>
      <p className="muted">Paste an abstract or a research summary, or give your ORCID iD and we will use your most-cited papers. Only open and forecasted opportunities are shown.</p>
      <div className="filters">
        <label className="check"><input type="radio" checked={how === "text"} onChange={() => setHow("text")} /> Paste text</label>
        <label className="check"><input type="radio" checked={how === "orcid"} onChange={() => setHow("orcid")} /> Use my ORCID iD</label>
      </div>
      <form onSubmit={run}>
        {how === "text" ? (
          <textarea className="bigtext" aria-label="Your research" rows={7} maxLength={8000} value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Describe your research: methods, disease or topic, population, career stage…" />
        ) : (
          <input className="orcid" aria-label="ORCID iD" placeholder="0000-0002-1825-0097" value={orcid} onChange={(e) => setOrcid(e.target.value)} />
        )}
        <p><button className="primary" disabled={loading || !ready}>{loading ? "Matching…" : "Find matching grants"}</button></p>
      </form>

      {error && <p className="error" role="alert">{error}</p>}
      {data && (
        <>
          {data.profile.papers.length > 0 && (
            <details className="profile">
              <summary>Matched using {data.profile.papers.length} papers{data.profile.name ? ` by ${data.profile.name}` : ""}</summary>
              <ul>{data.profile.papers.map((p) => <li key={p.id}>{p.title}{p.year ? ` (${p.year})` : ""}</li>)}</ul>
            </details>
          )}
          {data.results.length === 0 && <p className="empty">No matching opportunities found.</p>}
          {data.results.map((h) => (
            <article className="result" key={h.id}>
              <h3><Link href={`/opportunity/${h.id}`}>{h.title}</Link></h3>
              <div className="meta">
                {h.status && <span className={`badge ${h.status}`}>{h.status}</span>}
                {h.agency && <span>{h.agency}</span>}
                <span>{h.close_date ? `closes ${h.close_date}` : "no close date listed"}</span>
                {h.amount_max != null && <span>up to {money(h.amount_max)}</span>}
              </div>
              <p className="snippet">{h.snippet}</p>
              {h.closest_paper && <div className="why">closest to your paper: {h.closest_paper}</div>}
              <div className="actions"><WatchButton id={h.id} /></div>
            </article>
          ))}
        </>
      )}
    </>
  );
}
