import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SSC CGL Tier-1 Practice",
  description: "Quant and Reasoning section mocks from the 2024 SSC CGL Tier-1 papers",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-100">
        <main className="mx-auto max-w-4xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
