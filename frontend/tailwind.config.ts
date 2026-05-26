import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Layered surfaces — each tone is +1 brightness from the previous
        bg: {
          base:    "#08080a",
          surface: "#0d0d10",   // subtle elevation
          card:    "#111114",
          card2:   "#16161a",   // hovered card
          card3:   "#1c1c21",   // pressed / active
          border:  "#26262c",
          borderHi: "#34343a",  // emphasized border
          divider: "#1d1d22",
        },
        // Narrowed 4-color palette. The legacy violet/cyan/pink class names are
        // preserved as ALIASES so existing call sites keep compiling — they now
        // resolve to the 4 approved colors. New code should prefer the 4 names.
        accent: {
          // ── Approved palette ────────────────────────────────────────
          green: "#22c55e",       // gains, positive financials
          greenSoft: "#4ade80",
          greenMuted: "#16a34a",
          red: "#ef4444",         // losses, errors
          redSoft: "#f87171",
          redMuted: "#dc2626",
          amber: "#f59e0b",       // warnings, caution, highlight
          amberSoft: "#fbbf24",
          blue: "#3b82f6",        // brand / informational / neutral active
          blueSoft: "#60a5fa",
          // ── Aliases (legacy → palette) ──────────────────────────────
          // violet / cyan both collapse to blue (the "info" family).
          violet: "#3b82f6",
          violetSoft: "#60a5fa",
          cyan: "#3b82f6",
          cyanSoft: "#60a5fa",
          // pink → amber (warm decorative accent).
          pink: "#f59e0b",
          pinkSoft: "#fbbf24",
        },
        text: {
          primary: "#fafafa",
          secondary: "#a1a1aa",
          muted: "#71717a",
          dim:     "#52525b",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "InterVariable", "Inter",
          "ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "sans-serif",
        ],
        mono: [
          "var(--font-mono)",
          "IBM Plex Mono", "JetBrains Mono", "ui-monospace", "Menlo", "monospace",
        ],
        display: [
          "var(--font-display)",
          "IBM Plex Sans",
          "ui-sans-serif", "system-ui", "-apple-system", "BlinkMacSystemFont", "sans-serif",
        ],
      },
      fontSize: {
        // Slightly tightened scale for a denser pro look
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      letterSpacing: {
        tightest: "-0.025em",
      },
      boxShadow: {
        card:     "0 1px 0 0 rgba(255,255,255,0.02) inset, 0 1px 3px 0 rgba(0,0,0,0.4)",
        cardHi:   "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 4px 12px -2px rgba(0,0,0,0.5)",
        glow:     "0 0 0 1px rgba(59,130,246,0.18), 0 8px 24px -8px rgba(59,130,246,0.28)",
        focus:    "0 0 0 2px rgba(59,130,246,0.4)",
      },
      backgroundImage: {
        "card-gradient": "linear-gradient(180deg, #111114 0%, #14141a 100%)",
        "card-elevated": "linear-gradient(180deg, #16161a 0%, #1c1c21 100%)",
        "page-glow":
          "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(59,130,246,0.06), transparent 70%)",
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "slide-down": {
          from: { opacity: "0", transform: "translateY(-8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "shimmer": {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in":   "fade-in 0.2s ease-out",
        "slide-down": "slide-down 0.18s cubic-bezier(0.16, 1, 0.3, 1)",
        "shimmer":   "shimmer 1.6s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
