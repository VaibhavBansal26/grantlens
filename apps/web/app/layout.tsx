import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "GrantLens", description: "Search research funding" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="top">
          <Link href="/" className="brand">GrantLens</Link>
          <span className="muted">Semantic search over research funding</span>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
