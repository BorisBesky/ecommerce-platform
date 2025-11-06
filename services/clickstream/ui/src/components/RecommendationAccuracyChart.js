import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, } from 'recharts';
import { fetchRecommendationAccuracy } from '../lib/api';
function formatPercent(value) {
    return `${(value * 100).toFixed(1)}%`;
}
function RecommendationAccuracyChart() {
    const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
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
        return _jsx("div", { children: "Loading accuracy metrics\u2026" });
    }
    if (isError) {
        return (_jsxs("div", { className: "empty-state", children: ["Unable to load metrics: ", error.message, _jsx("div", { style: { marginTop: '0.75rem' }, children: _jsx("button", { className: "secondary-button", onClick: () => refetch(), disabled: isFetching, children: "Retry" }) })] }));
    }
    if (!data || data.metrics.length === 0) {
        return _jsx("div", { className: "empty-state", children: "No evaluation metrics are available yet." });
    }
    return (_jsxs("div", { children: [_jsx(ResponsiveContainer, { width: "100%", height: 260, className: "chart-container", children: _jsxs(LineChart, { data: chartData, children: [_jsx(CartesianGrid, { strokeDasharray: "3 3", opacity: 0.15 }), _jsx(XAxis, { dataKey: "name", stroke: "#475569" }), _jsx(YAxis, { stroke: "#475569", domain: [0, 1], tickFormatter: (value) => `${Math.round(value * 100)}%` }), _jsx(Tooltip, { formatter: (value) => formatPercent(value) }), _jsx(Legend, {}), _jsx(Line, { type: "monotone", dataKey: "precision", stroke: "#2563eb", strokeWidth: 2.5, dot: true }), _jsx(Line, { type: "monotone", dataKey: "recall", stroke: "#f97316", strokeWidth: 2.5, dot: true }), _jsx(Line, { type: "monotone", dataKey: "map", stroke: "#0ea5e9", strokeWidth: 2.5, dot: true }), _jsx(Line, { type: "monotone", dataKey: "ndcg", stroke: "#10b981", strokeWidth: 2.5, dot: true })] }) }), _jsxs("table", { style: { width: '100%', marginTop: '1.35rem', borderCollapse: 'collapse', fontSize: '0.92rem' }, children: [_jsx("thead", { children: _jsxs("tr", { style: { textAlign: 'left', borderBottom: '1px solid rgba(15, 23, 42, 0.08)' }, children: [_jsx("th", { style: { padding: '0.35rem 0.5rem' }, children: "Top-K" }), _jsx("th", { style: { padding: '0.35rem 0.5rem' }, children: "Precision" }), _jsx("th", { style: { padding: '0.35rem 0.5rem' }, children: "Recall" }), _jsx("th", { style: { padding: '0.35rem 0.5rem' }, children: "MAP" }), _jsx("th", { style: { padding: '0.35rem 0.5rem' }, children: "NDCG" })] }) }), _jsx("tbody", { children: data.metrics.map((metric) => (_jsxs("tr", { style: { borderBottom: '1px solid rgba(15, 23, 42, 0.05)' }, children: [_jsxs("td", { style: { padding: '0.4rem 0.5rem' }, children: ["Top-", metric.top_k] }), _jsx("td", { style: { padding: '0.4rem 0.5rem' }, children: formatPercent(metric.precision_at_k) }), _jsx("td", { style: { padding: '0.4rem 0.5rem' }, children: formatPercent(metric.recall_at_k) }), _jsx("td", { style: { padding: '0.4rem 0.5rem' }, children: formatPercent(metric.map_at_k) }), _jsx("td", { style: { padding: '0.4rem 0.5rem' }, children: formatPercent(metric.ndcg_at_k) })] }, metric.top_k))) })] }), _jsxs("div", { style: { marginTop: '1rem', color: '#475569', fontSize: '0.9rem' }, children: ["Evaluation ID ", _jsx("code", { children: data.evaluation_id }), " \u00B7 Generated ", new Date(data.generated_at).toLocaleString(), " \u00B7 Sampled ", data.sampled_users.toLocaleString(), " users"] })] }));
}
export default RecommendationAccuracyChart;
