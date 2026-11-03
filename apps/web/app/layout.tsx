import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { AuthProvider } from "@/lib/auth";
import { WatchProvider } from "@/lib/watch";
import Nav from "./Nav";
import VerifyBanner from "./VerifyBanner";

export const metadata: Metadata = { title: "GrantLens", description: "Search research funding" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <WatchProvider>
          <header className="top">
            <Link href="/" className="brand">GrantLens</Link>
            <span className="muted">Semantic search over research funding</span>
            <Nav />
          </header>
          <VerifyBanner />
          <main>{children}</main>
          </WatchProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
