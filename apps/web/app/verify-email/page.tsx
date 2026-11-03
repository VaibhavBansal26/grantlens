"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function VerifyEmailPage() {
  const { user, updateUser } = useAuth();
  const [state, setState] = useState<"busy" | "done" | "failed">("busy");
  const [error, setError] = useState("");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) { setError("This confirmation link is incomplete."); setState("failed"); return; }
    sendJson<{ email: string }>("POST", `${API}/auth/verify`, { token })
      .then((r) => { setState("done"); if (user && user.email === r.email) updateUser({ email_verified: true }); })
      .catch((e) => { setError((e as Error).message); setState("failed"); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (state === "busy") return <p className="muted">Confirming…</p>;
  if (state === "failed") {
    return <section className="authform"><h1>Could not confirm</h1><p className="error" role="alert">{error}</p>
      <p>{user ? "Use “Send it again” at the top of the page for a new link." : <><Link href="/login">Sign in</Link> to ask for a new link.</>}</p></section>;
  }
  return <section className="authform"><h1>Email confirmed</h1>
    <p>You can now turn on email alerts for <Link href="/saved">saved searches</Link> and <Link href="/watchlist">watched deadlines</Link>.</p></section>;
}
