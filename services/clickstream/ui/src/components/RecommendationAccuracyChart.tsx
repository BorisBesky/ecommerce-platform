import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { fetchRecommendationAccuracy } from '../lib/api';
import type { RecommendationAccuracyResponse } from '../types/api';

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function RecommendationAccuracyChart(): JSX.Element {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery<RecommendationAccuracyResponse>({
    queryKey: ['recommendation-accuracy'],
    queryFn: fetchRecommendationAccuracy,
    refetchInterval: 90000,
  });

  const chartData = useMemo(() => {
    if (!data) {
      return [];
    }
    return data.metrics.map((metric) => ({
      name: `Top-${metric.top_k}`,
      precision: metric.precision_at_k,
      recall: metric.recall_at_k,
      map: metric.map_at_k,
      ndcg: metric.ndcg_at_k,
    }));
  }, [data]);

  if (isLoading) {
    return <div>Loading accuracy metrics…</div>;
  }

  if (isError) {
    return (
      <div className="empty-state">
        Unable to load metrics: {(error as Error).message}
        <div style={{ marginTop: '0.75rem' }}>
          <button className="secondary-button" onClick={() => refetch()} disabled={isFetching}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data || data.metrics.length === 0) {
    return <div className="empty-state">No evaluation metrics are available yet.</div>;
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={260} className="chart-container">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
          <XAxis dataKey="name" stroke="#475569" />
          <YAxis stroke="#475569" domain={[0, 1]} tickFormatter={(value) => `${Math.round(value * 100)}%`} />
          <Tooltip formatter={(value: number) => formatPercent(value)} />
          <Legend />
          <Line type="monotone" dataKey="precision" stroke="#2563eb" strokeWidth={2.5} dot />
          <Line type="monotone" dataKey="recall" stroke="#f97316" strokeWidth={2.5} dot />
          <Line type="monotone" dataKey="map" stroke="#0ea5e9" strokeWidth={2.5} dot />
          <Line type="monotone" dataKey="ndcg" stroke="#10b981" strokeWidth={2.5} dot />
        </LineChart>
      </ResponsiveContainer>

      <table style={{ width: '100%', marginTop: '1.35rem', borderCollapse: 'collapse', fontSize: '0.92rem' }}>
        <thead>
          <tr style={{ textAlign: 'left', borderBottom: '1px solid rgba(15, 23, 42, 0.08)' }}>
            <th style={{ padding: '0.35rem 0.5rem' }}>Top-K</th>
            <th style={{ padding: '0.35rem 0.5rem' }}>Precision</th>
            <th style={{ padding: '0.35rem 0.5rem' }}>Recall</th>
            <th style={{ padding: '0.35rem 0.5rem' }}>MAP</th>
            <th style={{ padding: '0.35rem 0.5rem' }}>NDCG</th>
          </tr>
        </thead>
        <tbody>
          {data.metrics.map((metric) => (
            <tr key={metric.top_k} style={{ borderBottom: '1px solid rgba(15, 23, 42, 0.05)' }}>
              <td style={{ padding: '0.4rem 0.5rem' }}>Top-{metric.top_k}</td>
              <td style={{ padding: '0.4rem 0.5rem' }}>{formatPercent(metric.precision_at_k)}</td>
              <td style={{ padding: '0.4rem 0.5rem' }}>{formatPercent(metric.recall_at_k)}</td>
              <td style={{ padding: '0.4rem 0.5rem' }}>{formatPercent(metric.map_at_k)}</td>
              <td style={{ padding: '0.4rem 0.5rem' }}>{formatPercent(metric.ndcg_at_k)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ marginTop: '1rem', color: '#475569', fontSize: '0.9rem' }}>
        Evaluation ID <code>{data.evaluation_id}</code> · Generated {new Date(data.generated_at).toLocaleString()} ·
        Sampled {data.sampled_users.toLocaleString()} users
      </div>
    </div>
  );
}

export default RecommendationAccuracyChart;

