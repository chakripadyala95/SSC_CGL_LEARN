import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SSC CGL Tier-1 Practice",
  description: "Quant and Reasoning section mocks from the 2024 SSC CGL Tier-1 papers",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-100">
        <header className="mx-auto flex max-w-6xl gap-4 px-4 pt-4 text-sm">
          <Link href="/" className="hover:underline">
            Mocks
          </Link>
          <Link href="/questions" className="hover:underline">
            Question index
          </Link>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
