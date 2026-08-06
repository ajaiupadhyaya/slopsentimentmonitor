"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Leaderboard } from "@/components/Leaderboard";
import { Eyebrow, Panel } from "@/components/Meta";
import { RangePicker } from "@/components/RangePicker";
import { TraceChart } from "@/components/TraceChart";
import { fetchOverview } from "@/lib/api";

export default function Home() {
  const [hours, setHours] = useState(168);
  const { data, isLoading, error } = useQuery({
    queryKey: ["overview", hours],
    queryFn: () => fetchOverview(hours),
  });

  return (
    <main className="mx-auto max-w-6xl px-5 pb-24 pt-6 sm:px-8">
      <StatusRail summary={data?.summary} />

      <header className="mt-12 flex flex-wrap items-end justify-between gap-6 border-b border-hairline pb-8">
        <h1 className="max-w-2xl font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl">
          What the internet said about language models
        </h1>
        <RangePicker hours={hours} onChange={setHours} />
      </header>

      {error ? (
        <Panel className="mt-8">
          <Eyebrow>Cannot reach the API</Eyebrow>
          <p className="mt-3 max-w-prose text-sm text-graphite">
            {(error as Error).message}. Start it with{" "}
            <span className="font-mono text-ink">make api</span>.
          </p>
        </Panel>
      ) : null}

      <Panel className="mt-8">
        <Eyebrow>Sentiment and volume across every tracked model</Eyebrow>
        <div className="mt-4">
          <TraceChart
            series={data?.timeseries ?? []}
            height={200}
            label="Sentiment and mention volume over the selected window"
          />
        </div>
      </Panel>

      <div className="mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel>
          <Eyebrow>Mindshare and sentiment</Eyebrow>
          <div className="mt-4">
            {isLoading ? <Skeleton rows={8} /> : <Leaderboard models={data?.models ?? []} />}
          </div>
        </Panel>

        <div className="grid content-start gap-5 lg:sticky lg:top-5">
          <Panel>
            <Eyebrow>Where it came from</Eyebrow>
            <dl className="mt-4">
              {(data?.sources ?? []).map((source) => (
                <div
                  key={source.source}
                  className="flex items-baseline justify-between border-b border-hairline py-2 last:border-0"
                >
                  <dt className="font-mono text-xs">{source.source}</dt>
                  <dd className="tnum font-mono text-xs text-graphite">
                    {source.documents} docs · {source.mentions} mentions
                  </dd>
                </div>
              ))}
              {!isLoading && !data?.sources.length ? (
                <p className="py-6 font-mono text-xs text-graphite">Nothing collected yet.</p>
              ) : null}
            </dl>
          </Panel>

          <Panel>
            <Eyebrow>How this is measured</Eyebrow>
            <p className="mt-3 text-sm leading-relaxed text-graphite">
              Every document is stripped of machine-generated attribution, matched against a
              catalog of {data?.summary.models_tracked ?? 33} models, then scored only on the
              text surrounding each model&rsquo;s own mentions — so a comparison counts
              separately for each side.
            </p>
            <p className="mt-3 text-sm leading-relaxed text-graphite">
              Sentiment runs from −1 to +1. Bars are drawn on a fixed ±0.4 scale, so the same
              value always occupies the same width.
            </p>
          </Panel>
        </div>
      </div>
    </main>
  );
}

function StatusRail({ summary }: { summary?: { documents: number; mentions: number; pending: number; latest_document: string | null } }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-hairline pb-3 font-mono text-[11px] uppercase tracking-[0.12em] text-graphite">
      <span className="text-ink">PulseAI</span>
      <span className="tnum">{summary?.documents ?? "—"} documents</span>
      <span className="tnum">{summary?.mentions ?? "—"} mentions</span>
      {summary?.pending ? <span className="tnum">{summary.pending} pending</span> : null}
      <span className="ml-auto tnum">
        {summary?.latest_document
          ? `latest ${new Date(summary.latest_document).toLocaleString()}`
          : "no data"}
      </span>
    </div>
  );
}

function Skeleton({ rows }: { rows: number }) {
  return (
    <div aria-hidden className="space-y-3">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="h-6 bg-ground" />
      ))}
    </div>
  );
}
