"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";

import { Eyebrow, Panel, SignedValue, formatWhen } from "@/components/Meta";
import { RangePicker } from "@/components/RangePicker";
import { TraceChart } from "@/components/TraceChart";
import { fetchModel, type DocumentRef } from "@/lib/api";

export default function ModelPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [hours, setHours] = useState(168);
  const { data, isLoading, error } = useQuery({
    queryKey: ["model", slug, hours],
    queryFn: () => fetchModel(slug, hours),
  });

  const model = data?.model;

  return (
    <main className="mx-auto max-w-6xl px-5 pb-24 pt-6 sm:px-8">
      <Link
        href="/"
        className="font-mono text-[11px] uppercase tracking-[0.12em] text-graphite hover:text-ink"
      >
        ← All models
      </Link>

      <header className="mt-6 flex flex-wrap items-end justify-between gap-6 border-b border-hairline pb-8">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-graphite">
            {model?.company ?? "—"}
          </p>
          <h1 className="mt-1 font-display text-4xl tracking-tight sm:text-5xl">
            {model?.name ?? slug}
          </h1>
        </div>
        <RangePicker hours={hours} onChange={setHours} />
      </header>

      {error ? (
        <Panel className="mt-8">
          <Eyebrow>Cannot reach the API</Eyebrow>
          <p className="mt-3 text-sm text-graphite">{(error as Error).message}</p>
        </Panel>
      ) : null}

      <div className="mt-8 grid gap-5 sm:grid-cols-3">
        <Figure label="Mentions" value={model ? String(model.mentions) : "—"} />
        <Figure
          label="Sentiment"
          value={model ? undefined : "—"}
          node={model ? <SignedValue value={model.sentiment} /> : undefined}
        />
        <Figure
          label="Momentum vs prior window"
          value={
            model?.momentum === null || model?.momentum === undefined
              ? "no history yet"
              : `${model.momentum >= 0 ? "+" : "−"}${Math.abs(model.momentum * 100).toFixed(0)}%`
          }
        />
      </div>

      <Panel className="mt-5">
        <Eyebrow>Sentiment and volume over time</Eyebrow>
        <div className="mt-4">
          <TraceChart
            series={data?.timeseries ?? []}
            label={`Sentiment over time for ${model?.name ?? slug}`}
          />
        </div>
      </Panel>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Panel>
          <Eyebrow>Top praise</Eyebrow>
          <DocumentList documents={data?.praise ?? []} loading={isLoading} empty="No praise found in this window." />
        </Panel>
        <Panel>
          <Eyebrow>Top complaints</Eyebrow>
          <DocumentList
            documents={data?.complaints ?? []}
            loading={isLoading}
            empty="No complaints found in this window."
          />
        </Panel>
      </div>
    </main>
  );
}

function Figure({
  label,
  value,
  node,
}: {
  label: string;
  value?: string;
  node?: React.ReactNode;
}) {
  return (
    <div className="border border-hairline bg-panel p-5">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-graphite">{label}</p>
      <p className="tnum mt-2 font-display text-3xl">{node ?? value}</p>
    </div>
  );
}

function DocumentList({
  documents,
  loading,
  empty,
}: {
  documents: DocumentRef[];
  loading: boolean;
  empty: string;
}) {
  if (loading) {
    return <p className="py-8 font-mono text-xs text-graphite">Loading…</p>;
  }
  if (!documents.length) {
    return <p className="py-8 font-mono text-xs text-graphite">{empty}</p>;
  }

  return (
    <ul className="mt-3">
      {documents.slice(0, 8).map((doc, index) => (
        <li key={`${doc.url}-${index}`} className="border-b border-hairline py-3 last:border-0">
          <div className="flex items-baseline justify-between gap-3">
            <a
              href={doc.url ?? "#"}
              target="_blank"
              rel="noreferrer noopener"
              className="min-w-0 flex-1 text-sm leading-snug underline-offset-2 hover:underline"
            >
              {doc.title || doc.excerpt.slice(0, 90) || "Untitled"}
            </a>
            <SignedValue value={doc.sentiment} />
          </div>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.1em] text-graphite">
            {doc.source} · {doc.author ?? "unknown"} · {formatWhen(doc.published_at)}
          </p>
        </li>
      ))}
    </ul>
  );
}
