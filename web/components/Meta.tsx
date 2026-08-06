export function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-graphite">
      {children}
    </h2>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`border border-hairline bg-panel p-5 ${className}`}>{children}</section>
  );
}

/** Signed sentiment, always with an explicit sign so 0.04 never reads as -0.04. */
export function SignedValue({ value }: { value: number }) {
  const tone = value > 0.02 ? "text-pos" : value < -0.02 ? "text-neg" : "text-graphite";
  return (
    <span className={`tnum font-mono text-sm ${tone}`}>
      {value >= 0 ? "+" : "−"}
      {Math.abs(value).toFixed(3)}
    </span>
  );
}

export function formatWhen(iso: string): string {
  const then = new Date(iso).getTime();
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 60) return `${Math.max(minutes, 0)}m ago`;
  if (minutes < 1440) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / 1440)}d ago`;
}
