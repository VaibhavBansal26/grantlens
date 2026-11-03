"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";

export default function Nav() {
  const { user, ready, signOut } = useAuth();
  return (
    <nav className="nav">
      <Link href="/match">Find grants for my work</Link>
      <Link href="/papers">Papers</Link>
      <Link href="/deadlines">Deadlines</Link>
      {ready && user && (
        <>
          <Link href="/reviews">Reviews</Link>
          <Link href="/documents">Documents</Link>
          <Link href="/watchlist">Watchlist</Link>
          <Link href="/saved">Saved searches</Link>
          {user.is_admin && <Link href="/admin">Admin</Link>}
          <Link href="/account" className="muted">{user.email}</Link>
          <button className="link" onClick={signOut}>Sign out</button>
        </>
      )}
      {ready && !user && <Link href="/login">Sign in</Link>}
    </nav>
  );
}
