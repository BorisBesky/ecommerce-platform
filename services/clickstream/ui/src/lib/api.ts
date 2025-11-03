import type {
  FraudSummaryResponse,
  RecommendationAccuracyResponse,
  RayJobStatusResponse,
  RayJobSubmissionRequest,
  RayJobSubmissionResponse,
  SimulationParameters,
  SimulationStatusResponse,
  SimulationTriggerResponse,
} from '../types/api';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request to ${path} failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function triggerSimulation(params: SimulationParameters): Promise<SimulationTriggerResponse> {
  return request<SimulationTriggerResponse>('/simulations', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export function getSimulationStatus(runId: string): Promise<SimulationStatusResponse> {
  return request<SimulationStatusResponse>(`/simulations/${encodeURIComponent(runId)}`);
}

export function fetchFraudSummary(): Promise<FraudSummaryResponse> {
  return request<FraudSummaryResponse>('/analytics/fraud');
}

export function fetchRecommendationAccuracy(): Promise<RecommendationAccuracyResponse> {
  return request<RecommendationAccuracyResponse>('/analytics/recommendations/accuracy');
}

export function submitRayJob(body: RayJobSubmissionRequest): Promise<RayJobSubmissionResponse> {
  return request<RayJobSubmissionResponse>('/ray/jobs', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function fetchRayJobStatus(jobId: string, includeLogs = true, logLines = 200): Promise<RayJobStatusResponse> {
  const params = new URLSearchParams();
  if (!includeLogs) {
    params.set('include_logs', 'false');
  }
  if (logLines) {
    params.set('log_lines', String(logLines));
  }

  const query = params.toString();
  const suffix = query ? `?${query}` : '';

  return request<RayJobStatusResponse>(`/ray/jobs/${encodeURIComponent(jobId)}${suffix}`);
}

