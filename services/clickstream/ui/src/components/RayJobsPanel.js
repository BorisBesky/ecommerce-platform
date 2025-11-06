import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { fetchRayJobStatus, submitRayJob } from '../lib/api';
const pollingStatuses = new Set(['PENDING', 'RUNNING']);
function RayJobsPanel() {
    const [trackedJobId, setTrackedJobId] = useState(null);
    const [inputJobId, setInputJobId] = useState('');
    const submitMutation = useMutation({
        mutationFn: (payload) => submitRayJob(payload),
        onSuccess: ({ job }) => {
            setTrackedJobId(job.job_id);
            setInputJobId(job.job_id);
        },
    });
    const jobStatusQuery = useQuery({
        queryKey: ['ray-job-status', trackedJobId],
        queryFn: () => (trackedJobId ? fetchRayJobStatus(trackedJobId) : Promise.resolve(null)),
        enabled: Boolean(trackedJobId),
        refetchInterval: (query) => {
            const status = query.state.data?.job.status;
            return status && pollingStatuses.has(status) ? 5000 : false;
        },
    });
    const handleSubmitJob = (job_type) => {
        const payload = { job_type };
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
    return (_jsxs("div", { children: [_jsxs("div", { className: "button-row", children: [_jsx("button", { className: "primary-button", type: "button", onClick: () => handleSubmitJob('full_refresh'), disabled: submitMutation.isPending, children: "Launch full training" }), _jsx("button", { className: "secondary-button", type: "button", onClick: () => handleSubmitJob('incremental_refresh'), disabled: submitMutation.isPending, children: "Launch incremental update" }), submitMutation.isPending && _jsx("span", { children: "Submitting job\u2026" })] }), _jsxs("div", { style: { marginTop: '1.5rem' }, children: [_jsx("label", { htmlFor: "job-id-input", style: { display: 'block', fontWeight: 600, marginBottom: '0.3rem' }, children: "Track job" }), _jsxs("div", { style: { display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }, children: [_jsx("input", { id: "job-id-input", type: "text", value: inputJobId, onChange: (event) => setInputJobId(event.target.value), placeholder: "Enter Ray job ID", style: { flex: '1 1 260px', padding: '0.6rem 0.8rem', borderRadius: '10px', border: '1px solid rgba(15,23,42,0.1)' } }), _jsx("button", { className: "secondary-button", type: "button", onClick: handleLookup, disabled: jobStatusQuery.isFetching, children: "Fetch status" })] })] }), trackedJobId && (_jsxs("div", { style: { marginTop: '1.5rem' }, children: [_jsx("h3", { style: { marginBottom: '0.6rem' }, children: "Job status" }), jobStatusQuery.isLoading && _jsx("div", { children: "Loading job status\u2026" }), jobStatusQuery.isError && (_jsxs("div", { className: "empty-state", children: ["Unable to fetch job status: ", jobStatusQuery.error.message] })), jobStatusQuery.data && (_jsxs("div", { className: "status-grid", children: [_jsxs("div", { children: [_jsx("dt", { children: "Job ID" }), _jsx("dd", { children: _jsx("code", { children: jobStatusQuery.data.job.job_id }) })] }), _jsxs("div", { children: [_jsx("dt", { children: "Status" }), _jsx("dd", { children: _jsx("span", { className: `status-pill ${currentStatus?.toLowerCase() ?? 'pending'}`, children: currentStatus }) })] }), _jsxs("div", { children: [_jsx("dt", { children: "Type" }), _jsx("dd", { children: jobStatusQuery.data.job.job_type })] }), jobStatusQuery.data.job.message && (_jsxs("div", { children: [_jsx("dt", { children: "Message" }), _jsx("dd", { children: jobStatusQuery.data.job.message })] })), dashboardUrl && (_jsxs("div", { children: [_jsx("dt", { children: "Dashboard" }), _jsx("dd", { children: _jsx("a", { href: dashboardUrl, target: "_blank", rel: "noreferrer", children: "Open Ray dashboard" }) })] }))] })), logs && logs.length > 0 && (_jsxs("div", { style: { marginTop: '1.25rem' }, children: [_jsx("h4", { style: { marginBottom: '0.5rem' }, children: "Recent logs" }), _jsx("div", { className: "log-viewer", children: logs.map((line, index) => (_jsx("div", { children: line }, index))) })] }))] }))] }));
}
export default RayJobsPanel;
