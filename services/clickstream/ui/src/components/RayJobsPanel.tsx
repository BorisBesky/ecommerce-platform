import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';

import { fetchRayJobStatus, submitRayJob } from '../lib/api';
import type { RayJobStatusResponse, RayJobSubmissionRequest } from '../types/api';

const pollingStatuses = new Set(['PENDING', 'RUNNING']);

function RayJobsPanel(): JSX.Element {
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [inputJobId, setInputJobId] = useState('');

  const submitMutation = useMutation({
    mutationFn: (payload: RayJobSubmissionRequest) => submitRayJob(payload),
    onSuccess: ({ job }) => {
      setTrackedJobId(job.job_id);
      setInputJobId(job.job_id);
    },
  });

  const jobStatusQuery = useQuery<RayJobStatusResponse | null>({
    queryKey: ['ray-job-status', trackedJobId],
    queryFn: () => (trackedJobId ? fetchRayJobStatus(trackedJobId) : Promise.resolve(null)),
    enabled: Boolean(trackedJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.job.status;
      return status && pollingStatuses.has(status) ? 5000 : false;
    },
  });

  const handleSubmitJob = (job_type: 'full_refresh' | 'incremental_refresh') => {
    const payload: RayJobSubmissionRequest = { job_type };
    if (job_type === 'incremental_refresh') {
      payload.runtime_env = {
        env_vars: {
          INCREMENTAL_MODE: 'true',
        },
      };
    }
    submitMutation.mutate(payload);
  };

  const handleLookup = () => {
    if (inputJobId.trim().length > 0) {
      setTrackedJobId(inputJobId.trim());
      jobStatusQuery.refetch();
    }
  };

  const currentStatus = jobStatusQuery.data?.job.status;
  const logs = jobStatusQuery.data?.logs;
  const dashboardUrl = jobStatusQuery.data?.dashboard_url;

  return (
    <div>
      <div className="button-row">
        <button
          className="primary-button"
          type="button"
          onClick={() => handleSubmitJob('full_refresh')}
          disabled={submitMutation.isPending}
        >
          Launch full training
        </button>
        <button
          className="secondary-button"
          type="button"
          onClick={() => handleSubmitJob('incremental_refresh')}
          disabled={submitMutation.isPending}
        >
          Launch incremental update
        </button>
        {submitMutation.isPending && <span>Submitting job…</span>}
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <label htmlFor="job-id-input" style={{ display: 'block', fontWeight: 600, marginBottom: '0.3rem' }}>
          Track job
        </label>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <input
            id="job-id-input"
            type="text"
            value={inputJobId}
            onChange={(event) => setInputJobId(event.target.value)}
            placeholder="Enter Ray job ID"
            style={{ flex: '1 1 260px', padding: '0.6rem 0.8rem', borderRadius: '10px', border: '1px solid rgba(15,23,42,0.1)' }}
          />
          <button className="secondary-button" type="button" onClick={handleLookup} disabled={jobStatusQuery.isFetching}>
            Fetch status
          </button>
        </div>
      </div>

      {trackedJobId && (
        <div style={{ marginTop: '1.5rem' }}>
          <h3 style={{ marginBottom: '0.6rem' }}>Job status</h3>
          {jobStatusQuery.isLoading && <div>Loading job status…</div>}
          {jobStatusQuery.isError && (
            <div className="empty-state">Unable to fetch job status: {(jobStatusQuery.error as Error).message}</div>
          )}
          {jobStatusQuery.data && (
            <div className="status-grid">
              <div>
                <dt>Job ID</dt>
                <dd>
                  <code>{jobStatusQuery.data.job.job_id}</code>
                </dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  <span className={`status-pill ${currentStatus?.toLowerCase() ?? 'pending'}`}>
                    {currentStatus}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Type</dt>
                <dd>{jobStatusQuery.data.job.job_type}</dd>
              </div>
              {jobStatusQuery.data.job.message && (
                <div>
                  <dt>Message</dt>
                  <dd>{jobStatusQuery.data.job.message}</dd>
                </div>
              )}
              {dashboardUrl && (
                <div>
                  <dt>Dashboard</dt>
                  <dd>
                    <a href={dashboardUrl} target="_blank" rel="noreferrer">
                      Open Ray dashboard
                    </a>
                  </dd>
                </div>
              )}
            </div>
          )}

          {logs && logs.length > 0 && (
            <div style={{ marginTop: '1.25rem' }}>
              <h4 style={{ marginBottom: '0.5rem' }}>Recent logs</h4>
              <div className="log-viewer">
                {logs.map((line, index) => (
                  <div key={index}>{line}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default RayJobsPanel;

