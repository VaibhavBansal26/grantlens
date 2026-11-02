"use client";

import { useState } from "react";
import { API, Paper, getJson } from "@/lib/api";

export default function PapersPage() {
  const [q, setQ] = useState("");
  const [recent, setRecent] = useState(true);
  const [papers, setPapers] = useState<Paper[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setLoading(true);
    setError("");
    try {
      const u = new URLSearchParams({ q, k: "15" });
      if (recent) u.set("year_from", String(new Date().getFullYear() - 5));
      setPapers((await getJson<{ results: Paper[] }>(`${API}/literature/search?${u}`)).results);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h1>Papers</h1>
      <p className="muted">Search the scholarly literature (OpenAlex) to see what is being published in your area.</p>
      <form className="searchbar" onSubmit={run}>
        <input aria-label="Search papers" placeholder="e.g. deep learning for tumor segmentation" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="primary" disabled={loading || !q.trim()}>{loading ? "Searching…" : "Search"}</button>
      </form>
      <label className="check"><input type="checkbox" checked={recent} onChange={(e) => setRecent(e.target.checked)} /> Last five years only</label>
      {error && <p className="error">{error}</p>}
      {papers && papers.length === 0 && <p className="empty">No papers found.</p>}
      {papers?.map((p) => (
        <article className="result" key={p.id}>
          <h3>{p.url ? <a href={p.url} target="_blank" rel="noreferrer">{p.title}</a> : p.title}</h3>
          <div className="meta">
            {p.year && <span>{p.year}</span>}
            {p.venue && <span>{p.venue}</span>}
            <span>{p.cited_by} citation{p.cited_by === 1 ? "" : "s"}</span>
            {p.authors.length > 0 && <span>{p.authors.slice(0, 3).join(", ")}{p.authors.length > 3 ? " et al." : ""}</span>}
          </div>
          {p.abstract && (
            <p className="snippet">
              {open === p.id || p.abstract.length < 320 ? p.abstract : `${p.abstract.slice(0, 320)}… `}
              {p.abstract.length >= 320 && (
                <button className="link" onClick={() => setOpen(open === p.id ? null : p.id)}>{open === p.id ? "less" : "more"}</button>
              )}
            </p>
          )}
        </article>
      ))}
    </>
  );
}
