"use client";

import { useEffect, useState } from "react";

/** Adds `.intro-active` to <html> on the first page-load of a session.
 * Other components (nav logo, main content) read this class via CSS to
 * play a one-time entrance. Subsequent navigations within the session
 * skip the animation so it feels reserved for "arrival." */
export function AppIntro() {
  const [_, force] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const KEY = "intro_v1_seen";
    if (sessionStorage.getItem(KEY)) return;
    sessionStorage.setItem(KEY, "1");

    document.documentElement.classList.add("intro-active");
    force(1); // ensure re-render so any conditional readers update
    const t = setTimeout(() => {
      document.documentElement.classList.remove("intro-active");
    }, 900);
    return () => clearTimeout(t);
  }, []);

  return null;
}
