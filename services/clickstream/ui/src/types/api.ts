export type SimulationMode = 'full' | 'incremental';

export interface SimulationParameters {
  mode: SimulationMode;
  batches: number;
  batch_size: number;
  user_count: number;
  product_count: number;
  seed?: number | null;
}

export type SimulationStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface SimulationRun {
  run_id: string;
  mode: SimulationMode;
  status: SimulationStatus;
  batches: number;
  batch_size: number;
  user_count: number;
  product_count: number;
  event_count: number;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  artifact_paths?: Record<string, string> | null;
}

export interface SimulationTriggerResponse {
  run_id: string;
  status: SimulationStatus | string;
}

export interface SimulationStatusResponse {
  run: SimulationRun;
}

export interface FraudMetric {
  name: string;
  value: number;
  delta?: number | null;
  threshold?: number | null;
}

export interface FraudSummaryResponse {
  window_start: string;
  window_end: string;
  total_transactions: number;
  suspicious_transactions: number;
  metrics: FraudMetric[];
}

export interface RecommendationAccuracy {
  model_version: string;
  top_k: number;
  precision_at_k: number;
  recall_at_k: number;
  map_at_k: number;
  ndcg_at_k: number;
}

export interface RecommendationAccuracyResponse {
  evaluation_id: string;
  evaluation_type: 'full' | 'incremental';
  sampled_users: number;
  generated_at: string;
  metrics: RecommendationAccuracy[];
}

export type RayJobType = 'full_refresh' | 'incremental_refresh' | 'batch_inference';

export interface RayJobSubmissionRequest {
  job_type: RayJobType;
  entrypoint?: string | null;
  runtime_env?: Record<string, unknown> | null;
  metadata?: Record<string, string> | null;
}

export type RayJobStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'STOPPED' | 'FAILED' | 'UNKNOWN';

export interface RayJobInfo {
  job_id: string;
  job_type: RayJobType;
  status: RayJobStatus;
  submission_id?: string | null;
  message?: string | null;
  details?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export interface RayJobSubmissionResponse {
  job: RayJobInfo;
}

export interface RayJobStatusResponse {
  job: RayJobInfo;
  logs?: string[] | null;
  dashboard_url?: string | null;
}

