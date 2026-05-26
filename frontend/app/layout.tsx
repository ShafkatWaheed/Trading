import type { Metadata } from "next";
import { Inter, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Nav } from "@/components/nav";
import { AppIntro } from "@/components/app-intro";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

// Display face — distinctive without being odd. Tech-startup feel.
const plex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

// Mono for numerics, tabular price/share columns, and code-ish chips.
// IBM Plex Mono pairs with the IBM Plex Sans display face.
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Trading — Stock Analysis Platform",
  description: "AI-powered stock research with 8 personality agents and 16 deep-dive indicators.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${plex.variable} ${plexMono.variable}`}>
      <body className="bg-bg-base text-text-primary font-sans antialiased min-h-screen flex flex-col">
        <Providers>
          <AppIntro />
          <Nav />
          <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 lg:py-10 intro-rise">
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
