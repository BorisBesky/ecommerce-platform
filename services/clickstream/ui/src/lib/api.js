const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? '/api/v1';
async function request(path, init) {
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
    return response.json();
}
/**
 * Trigger data generation using the new unified endpoint.
 * Note: This endpoint doesn't accept parameters and generates a default dataset.
 * Returns a Response object for streaming output.
 */
export async function triggerDataGeneration() {
    const response = await fetch(`${API_BASE_URL}/data/generate`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    });
    if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Data generation failed with status ${response.status}`);
    }
    return response; // Return the Response object for streaming
}
export function fetchFraudSummary() {
    return request('/analytics/fraud');
}
export function fetchRecommendationAccuracy() {
    return request('/analytics/recommendations/accuracy');
}
export function submitRayJob(body) {
    return request('/ray/jobs', {
        method: 'POST',
        body: JSON.stringify(body),
    });
}
export function fetchRayJobStatus(jobId, includeLogs = true, logLines = 200) {
    const params = new URLSearchParams();
    if (!includeLogs) {
        params.set('include_logs', 'false');
    }
    if (logLines) {
        params.set('log_lines', String(logLines));
    }
    const query = params.toString();
    const suffix = query ? `?${query}` : '';
    return request(`/ray/jobs/${encodeURIComponent(jobId)}${suffix}`);
}
