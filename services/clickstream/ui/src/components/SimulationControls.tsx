import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';

import { getSimulationStatus, triggerSimulation } from '../lib/api';
import type { SimulationMode, SimulationParameters, SimulationRun, SimulationStatusResponse } from '../types/api';

const defaultParams: SimulationParameters = {
  mode: 'full',
  batches: 1,
  batch_size: 1000,
  user_count: 150,
  product_count: 500,
  seed: undefined,
};

const pollingStatuses = new Set(['pending', 'running']);

function SimulationControls(): JSX.Element {
  const [formValues, setFormValues] = useState<SimulationParameters>(defaultParams);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const simulationMutation = useMutation({
    mutationFn: triggerSimulation,
    onSuccess: ({ run_id }) => {
      setActiveRunId(run_id);
    },
  });

  const simulationStatusQuery = useQuery<SimulationStatusResponse | null>({
    queryKey: ['simulation-status', activeRunId],
    queryFn: () => (activeRunId ? getSimulationStatus(activeRunId) : Promise.resolve(null)),
    enabled: Boolean(activeRunId),
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
      return status && pollingStatuses.has(status) ? 4000 : false;
    },
  });

  const currentRun: SimulationRun | undefined = simulationStatusQuery.data?.run;

  const onChange = (field: keyof SimulationParameters) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const value = event.target.value;
    setFormValues((prev) => ({
      ...prev,
      [field]: field === 'mode' ? (value as SimulationMode) : value === '' ? undefined : Number(value),
    }));
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();

    const payload: SimulationParameters = {
      ...formValues,
      batches: Number(formValues.batches),
      batch_size: Number(formValues.batch_size),
      user_count: Number(formValues.user_count),
      product_count: Number(formValues.product_count),
      seed: formValues.seed ? Number(formValues.seed) : undefined,
    };

    simulationMutation.mutate(payload);
  };

  const runStatus = currentRun?.status ?? (simulationMutation.isPending ? 'pending' : null);
  const statusClass = runStatus ? `status-pill ${runStatus}` : 'status-pill';

  const artifactEntries = useMemo(() => {
    if (!currentRun?.artifact_paths) {
      return [] as Array<[string, string]>;
    }
    return Object.entries(currentRun.artifact_paths);
  }, [currentRun?.artifact_paths]);

  return (
    <div>
      <form onSubmit={handleSubmit} className="form-grid">
        <div className="form-group">
          <label htmlFor="mode">Mode</label>
          <select id="mode" value={formValues.mode} onChange={onChange('mode')}>
            <option value="full">Full refresh</option>
            <option value="incremental">Incremental</option>
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="batches">Batches</label>
          <input
            id="batches"
            type="number"
            min={1}
            value={formValues.batches}
            onChange={onChange('batches')}
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="batch_size">Events per batch</label>
          <input
            id="batch_size"
            type="number"
            min={1}
            value={formValues.batch_size}
            onChange={onChange('batch_size')}
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="user_count">User count</label>
          <input
            id="user_count"
            type="number"
            min={1}
            value={formValues.user_count}
            onChange={onChange('user_count')}
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="product_count">Product count</label>
          <input
            id="product_count"
            type="number"
            min={1}
            value={formValues.product_count}
            onChange={onChange('product_count')}
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="seed">Seed (optional)</label>
          <input
            id="seed"
            type="number"
            value={formValues.seed ?? ''}
            onChange={onChange('seed')}
            placeholder="Random"
          />
        </div>

        <div className="button-row">
          <button className="primary-button" type="submit" disabled={simulationMutation.isPending}>
            {simulationMutation.isPending ? 'Launching simulation…' : 'Start simulation'}
          </button>
          {activeRunId && (
            <button
              className="secondary-button"
              type="button"
              onClick={() => simulationStatusQuery.refetch()}
              disabled={simulationStatusQuery.isLoading}
            >
              Refresh status
            </button>
          )}
        </div>
      </form>

      <div style={{ marginTop: '1.8rem' }}>
        <h3>Latest run</h3>
        {!activeRunId && <div className="empty-state">Trigger a simulation to view run progress and outputs.</div>}
        {activeRunId && (
          <div className="status-grid">
            <div>
              <dt>Run identifier</dt>
              <dd>
                <code>{activeRunId}</code>
              </dd>
            </div>
            {runStatus && (
              <div>
                <dt>Status</dt>
                <dd>
                  <span className={statusClass}>{runStatus.toUpperCase()}</span>
                </dd>
              </div>
            )}
            {currentRun && (
              <>
                <div>
                  <dt>Events generated</dt>
                  <dd>{currentRun.event_count.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Users × Products</dt>
                  <dd>
                    {currentRun.user_count.toLocaleString()} users × {currentRun.product_count.toLocaleString()} products
                  </dd>
                </div>
                {currentRun.started_at && (
                  <div>
                    <dt>Started</dt>
                    <dd>{new Date(currentRun.started_at).toLocaleString()}</dd>
                  </div>
                )}
                {currentRun.finished_at && (
                  <div>
                    <dt>Finished</dt>
                    <dd>{new Date(currentRun.finished_at).toLocaleString()}</dd>
                  </div>
                )}
                {currentRun.error_message && (
                  <div>
                    <dt>Error</dt>
                    <dd>{currentRun.error_message}</dd>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {artifactEntries.length > 0 && (
          <div className="artifacts-list">
            <h4>Artifacts</h4>
            {artifactEntries.map(([label, uri]) => (
              <a key={label} href={uri} target="_blank" rel="noreferrer">
                {label}: {uri}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default SimulationControls;

