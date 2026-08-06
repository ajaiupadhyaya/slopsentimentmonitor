"use client";

import * as echarts from "echarts";
import { useEffect, useRef } from "react";

/**
 * Minimal ECharts binding.
 *
 * Written by hand rather than pulled from a wrapper package so the instance
 * lifecycle, resize handling and theme changes stay explicit — a chart that
 * silently fails to dispose leaks a canvas on every route change.
 */
export function Chart({
  option,
  height = 260,
  ariaLabel,
}: {
  option: echarts.EChartsOption;
  height?: number;
  ariaLabel: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!container.current) return;
    instance.current = echarts.init(container.current, undefined, { renderer: "canvas" });

    const observer = new ResizeObserver(() => instance.current?.resize());
    observer.observe(container.current);

    return () => {
      observer.disconnect();
      instance.current?.dispose();
      instance.current = null;
    };
  }, []);

  useEffect(() => {
    // notMerge, so a palette or series change replaces rather than layers.
    instance.current?.setOption(option, true);
  }, [option]);

  return (
    <div
      ref={container}
      role="img"
      aria-label={ariaLabel}
      style={{ height, width: "100%" }}
    />
  );
}
