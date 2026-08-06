"use client";

import Link from "next/link";
import { useState } from "react";

import { SentimentBar } from "./SentimentBar";
import { SignedValue } from "./Meta";
import type { ModelStat } from "@/lib/api";

/**
 * Below this, a sentiment score is one or two documents dressed up as a
 * measurement. Those models are still listed, but behind a toggle, so the
 * default view is only figures worth reading.
 */
const MIN_MENTIONS = 3;

/**
 * Mindshare and sentiment for every tracked model.
 *
 * Volume is a grey rule and sentiment is a coloured bar, because they answer
 * different questions: how much a model is discussed, and how that discussion
 * went. Sorting is by volume — the loudest conversation first — with sentiment
 * read across, so a heavily-discussed model with a negative bar is immediately
 * the story on the page.
 */
export function Leaderboard({ models }: { models: ModelStat[] }) {
  const [showThin, setShowThin] = useState(false);

  if (!models.length) {
    return (
      <p className="py-12 text-center font-mono text-xs text-graphite">
        No mentions yet. Run <span className="text-ink">make pipeline</span> to collect.
      </p>
    );
  }

  const measurable = models.filter((m) => m.mentions >= MIN_MENTIONS);
  const thin = models.filter((m) => m.mentions < MIN_MENTIONS);
  const visible = showThin ? models : measurable;
  const loudest = Math.max(...models.map((m) => m.mentions), 1);

  return (
    <div>
      <div className="grid grid-cols-[1fr_auto] items-end gap-4 border-b border-hairline pb-2 sm:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)_minmax(0,1.4fr)_auto]">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-graphite">
          Model
        </span>
        <span className="hidden font-mono text-[10px] uppercase tracking-[0.14em] text-graphite sm:block">
          Mentions
        </span>
        <span className="hidden text-center font-mono text-[10px] uppercase tracking-[0.14em] text-graphite sm:block">
          Negative · Positive
        </span>
        <span className="text-right font-mono text-[10px] uppercase tracking-[0.14em] text-graphite">
          Score
        </span>
      </div>

      <ol>
        {visible.map((model) => (
          <li key={model.slug} className="border-b border-hairline last:border-0">
            <Link
              href={`/models/${model.slug}`}
              className="grid grid-cols-[1fr_auto] items-center gap-4 py-2.5 transition-colors hover:bg-ground sm:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)_minmax(0,1.4fr)_auto]"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{model.name}</span>
                <span className="block truncate font-mono text-[10px] uppercase tracking-[0.1em] text-graphite">
                  {model.company}
                </span>
              </span>

              <span className="hidden items-center gap-2 sm:flex">
                <span
                  className="h-[3px] bg-graphite"
                  style={{ width: `${(model.mentions / loudest) * 100}%` }}
                />
                <span className="tnum font-mono text-xs text-graphite">{model.mentions}</span>
              </span>

              <span className="hidden sm:block">
                <SentimentBar value={model.sentiment} />
              </span>

              <span className="text-right">
                <SignedValue value={model.sentiment} />
              </span>
            </Link>
          </li>
        ))}
      </ol>

      {thin.length ? (
        <button
          type="button"
          onClick={() => setShowThin((open) => !open)}
          className="mt-3 font-mono text-[11px] uppercase tracking-[0.12em] text-graphite hover:text-ink"
        >
          {showThin
            ? "Hide models under 3 mentions"
            : `Show ${thin.length} models under 3 mentions`}
        </button>
      ) : null}
    </div>
  );
}
