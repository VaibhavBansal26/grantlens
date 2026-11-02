"use client";

import { useEffect, useState } from "react";
import { API, sendJson } from "@/lib/api";

export default function UnsubscribePage() {
  const [token, setToken] = useState<string | null>(null);
  const [state, setState] = useState<"ask" | "busy" | "done" | "error">("ask");
  const [message, setMessage] = useState("");

  useEffect(() => { setToken(new URLSearchParams(window.location.search).get("token")); }, []);

  async function confirm() {
    setState("busy");
    try {
      await sendJson("POST", `${API}/alerts/unsubscribe`, { token });
      setState("done");
    } catch (e) {
      setMessage((e as Error).message);
      setState("error");
    }
  }

  if (token === null) return <p className="muted">Loading…</p>;
  if (!token) return <p className="error">This unsubscribe link is incomplete. Use the link from the email.</p>;
  return (
    <section className="authform">
      <h1>Email alerts</h1>
      {state === "done" ? (
        <p>You will no longer get GrantLens emails. You can turn alerts back on from Saved searches and Watchlist.</p>
      ) : (
        <>
          <p>Stop all GrantLens email alerts (new-match emails and deadline reminders)?</p>
          {state === "error" && <p className="error" role="alert">{message}</p>}
          <button className="primary" onClick={confirm} disabled={state === "busy"}>Stop all alerts</button>
        </>
      )}
    </section>
  );
}
