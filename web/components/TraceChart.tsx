"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { Chart } from "./Chart";
import { usePalette } from "@/lib/theme";
import type { SeriesPoint } from "@/lib/api";

/**
 * Sentiment over time, drawn against the same zero datum as the leaderboard
 * bars. The area is split at zero and filled in the polarity colours, so the
 * trace reads as the same instrument as the rows above it.
 */
export function TraceChart({
  series,
  height = 240,
  label,
}: {
  series: SeriesPoint[];
  height?: number;
  label: string;
}) {
  const palette = usePalette();

  const option = useMemo<EChartsOption>(() => {
    const points = series.map((p) => [p.bucket, p.sentiment] as [string, number]);
    const volume = series.map((p) => [p.bucket, p.mentions] as [string, number]);

    return {
      animation: false,
      grid: { top: 16, right: 46, bottom: 26, left: 46 },
      tooltip: {
        trigger: "axis",
        backgroundColor: palette.panel,
        borderColor: palette.hairline,
        textStyle: { color: palette.ink, fontFamily: "var(--font-plex-mono)", fontSize: 11 },
      },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: palette.hairline } },
        axisTick: { show: false },
        axisLabel: {
          color: palette.graphite,
          fontFamily: "var(--font-plex-mono)",
          fontSize: 10,
        },
        splitLine: { show: false },
      },
      yAxis: [
        {
          type: "value",
          name: "sentiment",
          nameTextStyle: {
            color: palette.graphite,
            fontFamily: "var(--font-plex-mono)",
            fontSize: 10,
            align: "left",
          },
          min: -0.5,
          max: 0.5,
          axisLabel: {
            color: palette.graphite,
            fontFamily: "var(--font-plex-mono)",
            fontSize: 10,
          },
          splitLine: { lineStyle: { color: palette.hairline, type: "dotted" } },
        },
        {
          type: "value",
          name: "mentions",
          nameTextStyle: {
            color: palette.graphite,
            fontFamily: "var(--font-plex-mono)",
            fontSize: 10,
            align: "right",
          },
          // Headroom keeps the tallest bar in the bottom half of the plot.
          max: Math.max(...series.map((p) => p.mentions), 1) * 2,
          axisLabel: {
            color: palette.graphite,
            fontFamily: "var(--font-plex-mono)",
            fontSize: 10,
          },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          // Volume sits behind, uncoloured — mindshare is not an opinion.
          // Capped to the lower half of the plot so a single busy bucket cannot
          // visually bury the trace that the chart exists to show.
          name: "mentions",
          type: "bar",
          yAxisIndex: 1,
          data: volume,
          itemStyle: { color: palette.hairline, opacity: 0.9 },
          barMaxWidth: 22,
          z: 1,
        },
        {
          name: "sentiment",
          type: "line",
          yAxisIndex: 0,
          data: points,
          showSymbol: series.length < 40,
          symbolSize: 6,
          lineStyle: { width: 2 },
          // Fill down to zero rather than to the axis floor, so the shaded area
          // reads as distance from the datum instead of "amount".
          areaStyle: { origin: 0, opacity: 0.16 },
          z: 3,
          markLine: {
            silent: true,
            symbol: "none",
            data: [{ yAxis: 0 }],
            lineStyle: { color: palette.ink, width: 1, type: "solid", opacity: 0.55 },
            label: { show: false },
          },
        },
      ],
      // Colour the trace by the sign of the value it is passing through, so the
      // line itself carries polarity the same way the leaderboard bars do.
      visualMap: {
        show: false,
        seriesIndex: 1,
        dimension: 1,
        pieces: [
          { lte: -0.02, color: palette.neg },
          { gt: -0.02, lt: 0.02, color: palette.graphite },
          { gte: 0.02, color: palette.pos },
        ],
      },
    };
  }, [series, palette]);

  if (!series.length) {
    return (
      <p className="py-10 text-center font-mono text-xs text-graphite">
        No sentiment recorded in this window.
      </p>
    );
  }

  return <Chart option={option} height={height} ariaLabel={label} />;
}
