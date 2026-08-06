"use client";

import { RANGES } from "@/lib/api";

export function RangePicker({
  hours,
  onChange,
}: {
  hours: number;
  onChange: (hours: number) => void;
}) {
  return (
    <div className="flex items-center border border-hairline" role="group" aria-label="Time range">
      {RANGES.map((range) => {
        const active = range.hours === hours;
        return (
          <button
            key={range.hours}
            type="button"
            onClick={() => onChange(range.hours)}
            aria-pressed={active}
            className={`px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.1em] transition-colors ${
              active ? "bg-ink text-panel" : "text-graphite hover:text-ink"
            }`}
          >
            {range.label}
          </button>
        );
      })}
    </div>
  );
}
