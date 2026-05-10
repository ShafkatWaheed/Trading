import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Nav } from "@/components/nav";

export const metadata: Metadata = {
  title: "Trading — Stock Analysis Platform",
  description: "AI-powered stock research with 8 personality agents and 16 deep-dive indicators.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-bg-base text-text-primary font-sans antialiased min-h-screen flex flex-col">
        <Providers>
          <Nav />
          <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 lg:py-10">
            {children}
          </main>
          <footer className="border-t border-bg-divider mt-16">
            <div className="max-w-7xl mx-auto px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-text-muted">
              <div className="flex items-center gap-3">
                <div className="w-1.5 h-1.5 rounded-full bg-accent-greenSoft animate-pulse" />
                <span>Trading Analysis Platform</span>
                <span className="text-text-dim">·</span>
                <span>8 AI agents</span>
                <span className="text-text-dim">·</span>
                <span>36 backtestable signals</span>
              </div>
              <span className="text-text-dim">
                AI-generated analysis. Not financial advice.
              </span>
            </div>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
