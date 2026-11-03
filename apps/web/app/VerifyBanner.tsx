"use client";

import { useState } from "react";
import { API, sendJson } from "@/lib/api";
import { useAuth } from "@/lib/auth";

// Alert and reminder emails only go to confirmed addresses, so say so until the link has been followed.
export default function VerifyBanner() {
  const { user, ready } = useAuth();
  const [state, setState] = useState<"idle" | "busy" | "sent" | "failed">("idle");
  if (!ready || !user || user.email_verified !== false) return null;

  async function resend() {
    setState("busy");
    try {
      await sendJson("POST", `${API}/auth/resend-verification`);
      setState("sent");
    } catch {
      setState("failed");
    }
  }

  return (
    <p className="banner" role="status">
      Confirm {user.email} to turn on email alerts: follow the link we emailed you.{" "}
      {state === "sent" ? "Sent again; check your inbox." : state === "failed" ? "Could not send; try again later." : (
        <button className="link" onClick={resend} disabled={state === "busy"}>Send it again</button>
      )}
    </p>
  );
}
