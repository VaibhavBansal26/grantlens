"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API, ReviewResult, ReviewSummary, getJson, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ReviewsPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [list, setList] = useState<ReviewSummary[] | null>(null);
  const [topic, setTopic] = useState("");
  const [recent, setRecent] = useState(true);
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ready) return;
    if (!user) { router.replace("/login?next=/reviews"); return; }
    getJson<{ reviews: ReviewSummary[] }>(`${API}/reviews`).then((r) => setList(r.reviews)).catch((e) => setError((e as Error).message));
  }, [ready, user, router]);

  async function build(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setReview(null);
    try {
      const body: Record<string, unknown> = { topic };
      if (recent) body.year_from = new Date().getFullYear() - 5;
      const r = await sendJson<ReviewResult>("POST", `${API}/reviews`, body);
      setReview(r);
      setList((cur) => [{ id: r.id, topic: r.topic, created_at: r.created_at, papers: r.papers.length }, ...(cur ?? [])]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function open(id: number) {
    setError("");
    try { setReview(await getJson<ReviewResult>(`${API}/reviews/${id}`)); } catch (err) { setError((err as Error).message); }
  }

  async function remove(id: number) {
    if (!window.confirm("Delete this review?")) return;
    await sendJson("DELETE", `${API}/reviews/${id}`);
    setList((cur) => cur && cur.filter((r) => r.id !== id));
    if (review?.id === id) setReview(null);
  }

  if (!list) return error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>;
  const byId = new Map(review?.papers.map((p) => [p.id, p]));

  return (
    <>
      <h1>Literature reviews</h1>
      <p className="muted">Enter a topic. We find recent papers, group them into themes and annotate each one from its abstract. Every annotation carries a quote from the abstract, and ones we cannot verify are left blank.</p>
      <form onSubmit={build}>
        <div className="searchbar">
          <input aria-label="Review topic" placeholder="e.g. deep learning for tumor segmentation" maxLength={300} value={topic} onChange={(e) => setTopic(e.target.value)} />
          <button className="primary" disabled={busy || topic.trim().length < 3}>{busy ? "Reading papers…" : "Build review"}</button>
        </div>
        <label className="check"><input type="checkbox" checked={recent} onChange={(e) => setRecent(e.target.checked)} /> Last five years only</label>
      </form>
      {busy && <p className="muted">This takes up to a minute: searching, reading abstracts and organising themes.</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {list.length > 0 && (
        <details className="profile" open={!review}>
          <summary>Your saved reviews ({list.length})</summary>
          <ul>
            {list.map((r) => (
              <li key={r.id}>
                <button className="link" onClick={() => open(r.id)}>{r.topic}</button>
                <span className="muted"> · {r.papers} papers · {new Date(r.created_at).toLocaleDateString()} </span>
                <button className="link" onClick={() => remove(r.id)}>Delete</button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {review && (
        <article className="review">
          <h2>{review.topic}</h2>
          <div className="actions">
            <a href={`${API}/reviews/${review.id}.bib`}>Download BibTeX</a>
            <a href={`${API}/reviews/${review.id}.md`}>Download Markdown</a>
          </div>
          <p className="muted">Drafted from abstracts only. Read the papers before you cite them.</p>
          {review.themes.map((t, i) => (
            <section key={i}>
              <h3>{t.title}</h3>
              {t.summary && <p>{t.summary}</p>}
              <ul className="reading">
                {t.papers.map((id) => {
                  const p = byId.get(id);
                  if (!p) return null;
                  return (
                    <li key={id}>
                      <span className="muted">{id}</span>{" "}
                      {p.url ? <a href={p.url} target="_blank" rel="noreferrer">{p.title}</a> : p.title}
                      <span className="muted"> ({p.year ?? "n.d."}{p.venue ? `, ${p.venue}` : ""}{p.authors.length ? `; ${p.authors.slice(0, 3).join(", ")}${p.authors.length > 3 ? " et al." : ""}` : ""})</span>
                      {p.annotation && <div>{p.annotation}</div>}
                      {p.evidence_quote && <div className="muted">“{p.evidence_quote}”</div>}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
          {review.open_questions.length > 0 && (<><h3>Open questions</h3><ul>{review.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></>)}
          {review.unverified_annotations > 0 && <p className="muted">{review.unverified_annotations} annotation{review.unverified_annotations === 1 ? "" : "s"} could not be checked against the abstract, so the text was left out.</p>}
          {review.removed_citations > 0 && <p className="muted">{review.removed_citations} reference{review.removed_citations === 1 ? "" : "s"} to papers we did not retrieve {review.removed_citations === 1 ? "was" : "were"} removed.</p>}
          {review.skipped_no_abstract > 0 && <p className="muted">{review.skipped_no_abstract} paper{review.skipped_no_abstract === 1 ? " was" : "s were"} left out because no abstract was available.</p>}
        </article>
      )}
    </>
  );
}
