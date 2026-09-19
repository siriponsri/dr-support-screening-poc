export interface GlobalResult {
  model_id: string;
  model_version: string;
  modality: string;
  state: string;
  grade: number | null;
  probabilities: number[];
  confidence: number | null;
  warnings: string[];
}

export interface Lesion {
  source_label: string;
  canonical_label: string;
  rectangle: [number, number, number, number];
  score: number;
  state: string;
}

export interface LesionResult {
  model_id: string;
  model_version: string;
  modality: string;
  state: string;
  width: number;
  height: number;
  lesions: Lesion[];
  warnings: string[];
}

export interface CaseRecord {
  image_id: string;
  display_name: string;
  filename: string | null;
  source_type: string;
  source: string;
  modality: string;
  width: number;
  height: number;
  image_url: string;
  state: string;
  revision: number;
  global: GlobalResult | null;
  lesion: LesionResult | null;
  warnings?: string[];
}

export interface ModelDescriptor {
  model_id: string;
  task: string;
  runtime?: string;
  status?: string;
  warnings?: string[];
}

export async function apiJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const body = await response.json().catch(() => null) as { detail?: string } | null;
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed with HTTP ${response.status}`);
  }
  return body as T;
}
