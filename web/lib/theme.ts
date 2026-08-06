"use client";

import { useEffect, useState } from "react";

export interface Palette {
  ink: string;
  graphite: string;
  hairline: string;
  panel: string;
  pos: string;
  neg: string;
}

const LIGHT: Palette = {
  ink: "#12161a",
  graphite: "#59636d",
  hairline: "#dde2e6",
  panel: "#ffffff",
  pos: "#0e7c6b",
  neg: "#c0562f",
};

const DARK: Palette = {
  ink: "#e7ebee",
  graphite: "#8a949e",
  hairline: "#252c33",
  panel: "#161b20",
  pos: "#2fb89e",
  neg: "#e0794a",
};

/**
 * ECharts draws to canvas and cannot read CSS custom properties, so the palette
 * has to reach it as plain values. Mirrors the tokens in globals.css.
 */
export function usePalette(): Palette {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    setDark(query.matches);
    const onChange = (event: MediaQueryListEvent) => setDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return dark ? DARK : LIGHT;
}

/** Sentiment colour. Near-zero stays grey so faint signal is not overstated. */
export function sentimentColor(value: number, palette: Palette): string {
  if (value > 0.02) return palette.pos;
  if (value < -0.02) return palette.neg;
  return palette.graphite;
}
