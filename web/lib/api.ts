export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

export interface ModelStat {
  slug: string;
  name: string;
  company: string;
  mentions: number;
  documents: number;
  sentiment: number;
  positive_share: number;
  negative_share: number;
  /** null when there is no prior window to compare against yet. */
  momentum: number | null;
}

export interface SeriesPoint {
  bucket: string;
  mentions: number;
  sentiment: number;
}

export interface SourceStat {
  source: string;
  documents: number;
  mentions: number;
}

export interface CorpusSummary {
  documents: number;
  enriched: number;
  pending: number;
  mentions: number;
  models_tracked: number;
  latest_document: string | null;
}

export interface Overview {
  summary: CorpusSummary;
  models: ModelStat[];
  sources: SourceStat[];
  timeseries: SeriesPoint[];
  window_hours: number;
}

export interface DocumentRef {
  title: string | null;
  url: string | null;
  author: string | null;
  published_at: string;
  score: number | null;
  source: string;
  sentiment: number;
  confidence: number;
  excerpt: string;
}

export interface ModelDetail {
  model: ModelStat;
  timeseries: SeriesPoint[];
  praise: DocumentRef[];
  complaints: DocumentRef[];
  recent: DocumentRef[];
  window_hours: number;
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} — ${path}`);
  }
  return response.json() as Promise<T>;
}

export const fetchOverview = (hours: number) =>
  request<Overview>(`/overview?hours=${hours}`);

export const fetchModel = (slug: string, hours: number) =>
  request<ModelDetail>(`/models/${slug}?hours=${hours}`);

/** Trailing windows offered in the UI, in hours. */
export const RANGES = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "30d", hours: 720 },
  { label: "90d", hours: 2160 },
] as const;
