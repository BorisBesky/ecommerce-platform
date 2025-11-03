import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { fetchFraudSummary } from '../lib/api';
import type { FraudSummaryResponse } from '../types/api';

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function FraudDashboard(): JSX.Element {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery<FraudSummaryResponse>({
    queryKey: ['fraud-summary'],
    queryFn: fetchFraudSummary,
    refetchInterval: 60000,
  });

  if (isLoading) {
    return <div>Loading fraud metrics…</div>;
  }

  if (isError) {
    return (
      <div className="empty-state">
        Unable to load fraud summary: {(error as Error).message}
        <div style={{ marginTop: '0.75rem' }}>
          <button className="secondary-button" onClick={() => refetch()} disabled={isFetching}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return <div className="empty-state">No fraud telemetry is available yet.</div>;
  }

  const suspicionMetric = data.metrics.find((metric) => metric.name === 'suspicion_rate');
  const paymentFailureMetric = data.metrics.find((metric) => metric.name === 'payment_failure_rate');
  const avgEventsMetric = data.metrics.find((metric) => metric.name === 'avg_events_per_user');

  const barData = [
    { name: 'Suspicious', count: data.suspicious_transactions },
    { name: 'Healthy', count: Math.max(data.total_transactions - data.suspicious_transactions, 0) },
  ];

  return (
    <div>
      <div className="metric-cards">
        <div className="metric-card">
          <h3>Suspicion Rate</h3>
          <p>{suspicionMetric ? formatPercent(suspicionMetric.value) : '0.00%'}</p>
          <small>
            Threshold {suspicionMetric?.threshold ? formatPercent(suspicionMetric.threshold) : formatPercent(0.02)}
          </small>
        </div>
        <div className="metric-card">
          <h3>Payment Failures</h3>
          <p>{paymentFailureMetric ? formatPercent(paymentFailureMetric.value) : '0.00%'}</p>
          <small>{data.suspicious_transactions.toLocaleString()} suspicious events</small>
        </div>
        <div className="metric-card">
          <h3>Avg. Events per User</h3>
          <p>{avgEventsMetric ? avgEventsMetric.value.toFixed(1) : '0.0'}</p>
          <small>{data.total_transactions.toLocaleString()} events in window</small>
        </div>
      </div>

      <div style={{ marginTop: '1.5rem' }}>
        <ResponsiveContainer width="100%" height={260} className="chart-container">
          <BarChart data={barData}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
            <XAxis dataKey="name" stroke="#475569" />
            <YAxis stroke="#475569" allowDecimals={false} />
            <Tooltip formatter={(value: number) => value.toLocaleString()} />
            <Bar dataKey="count" fill="#2563eb" radius={[12, 12, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ marginTop: '1rem', fontSize: '0.9rem', color: '#475569' }}>
        Window: {new Date(data.window_start).toLocaleString()} → {new Date(data.window_end).toLocaleString()}
      </div>
    </div>
  );
}

export default FraudDashboard;

