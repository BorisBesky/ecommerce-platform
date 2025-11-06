import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, } from 'recharts';
import { fetchFraudSummary } from '../lib/api';
function formatPercent(value) {
    return `${(value * 100).toFixed(2)}%`;
}
function FraudDashboard() {
    const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
        queryKey: ['fraud-summary'],
        queryFn: fetchFraudSummary,
        refetchInterval: 60000,
    });
    if (isLoading) {
        return _jsx("div", { children: "Loading fraud metrics\u2026" });
    }
    if (isError) {
        return (_jsxs("div", { className: "empty-state", children: ["Unable to load fraud summary: ", error.message, _jsx("div", { style: { marginTop: '0.75rem' }, children: _jsx("button", { className: "secondary-button", onClick: () => refetch(), disabled: isFetching, children: "Retry" }) })] }));
    }
    if (!data) {
        return _jsx("div", { className: "empty-state", children: "No fraud telemetry is available yet." });
    }
    const suspicionMetric = data.metrics.find((metric) => metric.name === 'suspicion_rate');
    const paymentFailureMetric = data.metrics.find((metric) => metric.name === 'payment_failure_rate');
    const avgEventsMetric = data.metrics.find((metric) => metric.name === 'avg_events_per_user');
    const barData = [
        { name: 'Suspicious', count: data.suspicious_transactions },
        { name: 'Healthy', count: Math.max(data.total_transactions - data.suspicious_transactions, 0) },
    ];
    return (_jsxs("div", { children: [_jsxs("div", { className: "metric-cards", children: [_jsxs("div", { className: "metric-card", children: [_jsx("h3", { children: "Suspicion Rate" }), _jsx("p", { children: suspicionMetric ? formatPercent(suspicionMetric.value) : '0.00%' }), _jsxs("small", { children: ["Threshold ", suspicionMetric?.threshold ? formatPercent(suspicionMetric.threshold) : formatPercent(0.02)] })] }), _jsxs("div", { className: "metric-card", children: [_jsx("h3", { children: "Payment Failures" }), _jsx("p", { children: paymentFailureMetric ? formatPercent(paymentFailureMetric.value) : '0.00%' }), _jsxs("small", { children: [data.suspicious_transactions.toLocaleString(), " suspicious events"] })] }), _jsxs("div", { className: "metric-card", children: [_jsx("h3", { children: "Avg. Events per User" }), _jsx("p", { children: avgEventsMetric ? avgEventsMetric.value.toFixed(1) : '0.0' }), _jsxs("small", { children: [data.total_transactions.toLocaleString(), " events in window"] })] })] }), _jsx("div", { style: { marginTop: '1.5rem' }, children: _jsx(ResponsiveContainer, { width: "100%", height: 260, className: "chart-container", children: _jsxs(BarChart, { data: barData, children: [_jsx(CartesianGrid, { strokeDasharray: "3 3", opacity: 0.2 }), _jsx(XAxis, { dataKey: "name", stroke: "#475569" }), _jsx(YAxis, { stroke: "#475569", allowDecimals: false }), _jsx(Tooltip, { formatter: (value) => value.toLocaleString() }), _jsx(Bar, { dataKey: "count", fill: "#2563eb", radius: [12, 12, 0, 0] })] }) }) }), _jsxs("div", { style: { marginTop: '1rem', fontSize: '0.9rem', color: '#475569' }, children: ["Window: ", new Date(data.window_start).toLocaleString(), " \u2192 ", new Date(data.window_end).toLocaleString()] })] }));
}
export default FraudDashboard;
