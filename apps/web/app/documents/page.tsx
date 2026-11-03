"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { API, Answer, Doc, getJson, sendJson, uploadFile } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function DocumentsPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState<"" | "upload" | "ask">("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ready) return;
    if (!user) { router.replace("/login?next=/documents"); return; }
    getJson<{ documents: Doc[] }>(`${API}/documents`)
      .then((r) => { setDocs(r.documents); setSelected((cur) => cur ?? r.documents[0]?.id ?? null); })
      .catch((e) => setError((e as Error).message));
  }, [ready, user, router]);

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy("upload");
    setError("");
    try {
      const doc = await uploadFile<Doc>(`${API}/documents`, file);
      setDocs((cur) => [doc, ...(cur ?? [])]);
      setSelected(doc.id);
      setAnswer(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (selected === null) return;
    setBusy("ask");
    setError("");
    setAnswer(null);
    try {
      setAnswer(await sendJson<Answer>("POST", `${API}/documents/${selected}/ask`, { question }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function remove(id: number) {
    if (!window.confirm("Delete this document and its extracted text?")) return;
    await sendJson("DELETE", `${API}/documents/${id}`);
    setDocs((cur) => cur && cur.filter((d) => d.id !== id));
    if (selected === id) { setSelected(null); setAnswer(null); }
  }

  if (!docs) return error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>;
  const current = docs.find((d) => d.id === selected);

  return (
    <>
      <h1>Documents</h1>
      <p className="muted">
        Upload a paper or a funding notice as a PDF and ask questions about it. Every answer is backed by quotes
        from the document, and quotes we cannot find in the text are removed.
      </p>
      <p>
        <label className="download" style={{ marginLeft: 0, cursor: "pointer" }}>
          {busy === "upload" ? "Reading and indexing…" : "Upload a PDF"}
          <input ref={fileRef} type="file" accept="application/pdf,.pdf" onChange={upload} disabled={busy !== ""} hidden />
        </label>
        <span className="muted"> up to 15 MB and 150 pages, text-based PDFs only</span>
      </p>
      {error && <p className="error" role="alert">{error}</p>}

      {docs.length === 0 && <p className="empty">No documents yet.</p>}
      {docs.map((d) => (
        <article className={`result${d.id === selected ? " picked" : ""}`} key={d.id}>
          <h3>{d.title}</h3>
          <div className="meta"><span>{d.pages} page{d.pages === 1 ? "" : "s"}</span>{d.expires_at && <span>deleted automatically on {new Date(d.expires_at).toLocaleDateString()}</span>}</div>
          <div className="actions">
            <button className="watch" onClick={() => { setSelected(d.id); setAnswer(null); }} aria-pressed={d.id === selected}>
              {d.id === selected ? "Selected" : "Ask about this"}
            </button>
            <button className="link" onClick={() => remove(d.id)}>Delete</button>
          </div>
        </article>
      ))}

      {current && (
        <form onSubmit={ask}>
          <h2>Ask about “{current.title}”</h2>
          <div className="searchbar">
            <input aria-label="Your question" placeholder="e.g. What sample size did they use?" maxLength={500}
              value={question} onChange={(e) => setQuestion(e.target.value)} />
            <button className="primary" disabled={busy !== "" || !question.trim()}>{busy === "ask" ? "Reading…" : "Ask"}</button>
          </div>
        </form>
      )}

      {answer && (
        <section className="answer" aria-live="polite">
          <p style={{ whiteSpace: "pre-wrap" }}>{answer.answer}</p>
          {answer.citations.length > 0 && (
            <>
              <h3>Sources</h3>
              <ul>
                {answer.citations.map((c, i) => (
                  <li key={i}><span className="muted">[{c.n}] page {c.page}:</span> “{c.quote}”</li>
                ))}
              </ul>
            </>
          )}
          {answer.removed_citations > 0 && (
            <p className="muted">{answer.removed_citations} citation{answer.removed_citations === 1 ? "" : "s"} could not be found in the document and {answer.removed_citations === 1 ? "was" : "were"} removed.</p>
          )}
        </section>
      )}
    </>
  );
}
