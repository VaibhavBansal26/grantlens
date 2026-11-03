"use client";

import Link from "next/link";
import { useState } from "react";
import { API, FitResult, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ORCID = /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/;
const LABEL = { met: "Looks met", unclear: "Unclear", not_met: "Not met" } as const;

export default function FitPanel({ id }: { id: number }) {
  const { user, ready } = useAuth();
  const [how, setHow] = useState<"text" | "orcid">("text");
  const [text, setText] = useState("");
  const [orcid, setOrcid] = useState("");
  const [fit, setFit] = useState<FitResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!ready) return null;
  if (!user) {
    return (
      <section className="fit">
        <h2>Check my fit</h2>
        <p><Link href={`/login?next=/opportunity/${id}`}>Sign in</Link> to compare your work with this grant and get a draft aims outline.</p>
      </section>
    );
  }

  const ok = how === "text" ? text.trim().length >= 40 : ORCID.test(orcid.trim());

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setFit(null);
    try {
      setFit(await sendJson<FitResult>("POST", `${API}/opportunities/${id}/fit`, how === "text" ? { text } : { orcid: orcid.trim() }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="fit">
      <h2>Check my fit</h2>
      <p className="muted">Describe your work (or use your ORCID iD) and we compare it with this grant. This is a drafting aid: check every point against the official notice before you rely on it.</p>
      <div className="filters">
        <label className="check"><input type="radio" checked={how === "text"} onChange={() => setHow("text")} /> Describe myself</label>
        <label className="check"><input type="radio" checked={how === "orcid"} onChange={() => setHow("orcid")} /> Use my ORCID iD</label>
      </div>
      <form onSubmit={run}>
        {how === "text" ? (
          <textarea className="bigtext" aria-label="About you and your project" rows={5} maxLength={4000} value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Career stage, institution, your research and any preliminary results. Anything you leave out will be marked unclear, not guessed." />
        ) : (
          <input className="orcid" aria-label="ORCID iD" placeholder="0000-0002-1825-0097" value={orcid} onChange={(e) => setOrcid(e.target.value)} />
        )}
        <p><button className="primary" disabled={busy || !ok}>{busy ? "Analyzing…" : "Check my fit"}</button></p>
      </form>
      {error && <p className="error" role="alert">{error}</p>}

      {fit && (
        <div className="fitresult" aria-live="polite">
          {fit.grant_closed && <p className="error">This opportunity is closed or archived, so treat this as practice for a future round.</p>}
          <p>{fit.summary}</p>

          <h3>Eligibility</h3>
          <ul className="elig">
            {fit.eligibility.map((e, i) => (
              <li key={i}>
                <span className={`badge st-${e.status}`}>{LABEL[e.status]}</span> {e.requirement}
                <div className="muted">grant says: “{e.requirement_quote}”</div>
                {e.researcher_quote && <div className="muted">you wrote: “{e.researcher_quote}”</div>}
                {e.note && <div className="muted">{e.note}</div>}
              </li>
            ))}
          </ul>
          {fit.dropped_requirements > 0 && <p className="muted">{fit.dropped_requirements} requirement{fit.dropped_requirements === 1 ? "" : "s"} the AI suggested {fit.dropped_requirements === 1 ? "is" : "are"} not in the grant text and {fit.dropped_requirements === 1 ? "was" : "were"} left out.</p>}
          {fit.downgraded > 0 && <p className="muted">{fit.downgraded} claim{fit.downgraded === 1 ? "" : "s"} could not be backed by a quote from your text, so {fit.downgraded === 1 ? "it was" : "they were"} marked unclear.</p>}

          {fit.strengths.length > 0 && (<><h3>Strengths</h3><ul>{fit.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul></>)}
          {fit.gaps.length > 0 && (<><h3>Gaps to address</h3><ul>{fit.gaps.map((s, i) => <li key={i}>{s}</li>)}</ul></>)}

          <h3>Draft aims outline</h3>
          <ol>
            {fit.aims.map((a, i) => (
              <li key={i}>
                <strong>{a.aim}</strong>
                <div>{a.rationale}{a.papers.length > 0 && <span className="muted"> [{a.papers.join(", ")}]</span>}</div>
              </li>
            ))}
          </ol>

          {fit.papers.length > 0 && (
            <details className="profile">
              <summary>Papers that can be cited above ({fit.papers.length})</summary>
              <ul>
                {fit.papers.map((p) => (
                  <li key={p.id}><span className="muted">{p.id}:</span> {p.url ? <a href={p.url} target="_blank" rel="noreferrer">{p.title}</a> : p.title}{p.year ? ` (${p.year})` : ""}</li>
                ))}
              </ul>
            </details>
          )}
          {fit.removed_citations > 0 && <p className="muted">{fit.removed_citations} citation{fit.removed_citations === 1 ? "" : "s"} to papers we did not retrieve {fit.removed_citations === 1 ? "was" : "were"} removed.</p>}
          {!fit.literature_available && <p className="muted">The literature service was unavailable, so no papers are cited.</p>}
        </div>
      )}
    </section>
  );
}
