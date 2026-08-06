"use client";

/**
 * The page's signature: a bar that grows out of a shared zero datum.
 *
 * Length encodes sentiment magnitude, direction encodes sign, and the centre
 * line sits at exactly the same x-position in every row — so the column of
 * baselines reads as one continuous rule down the page.
 */

/**
 * Fixed domain rather than one normalised to the current data. Auto-scaling
 * would make a quiet week look as dramatic as a loud one, and bars would jump
 * every time the window changed.
 */
const DOMAIN = 0.4;

export function SentimentBar({ value }: { value: number }) {
  const clamped = Math.max(-DOMAIN, Math.min(DOMAIN, value));
  const magnitude = (Math.abs(clamped) / DOMAIN) * 50;
  const positive = clamped >= 0;

  return (
    <div className="datum relative h-4 w-full">
      <div
        className={positive ? "absolute h-4 bg-pos" : "absolute h-4 bg-neg"}
        style={{
          left: positive ? "50%" : `${50 - magnitude}%`,
          width: `${Math.max(magnitude, value === 0 ? 0 : 0.6)}%`,
        }}
      />
    </div>
  );
}
