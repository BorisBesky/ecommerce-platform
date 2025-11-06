import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { triggerDataGeneration } from '../lib/api';
function SimulationControls() {
    const [status, setStatus] = useState('idle');
    const [output, setOutput] = useState([]);
    const [startTime, setStartTime] = useState(null);
    const [endTime, setEndTime] = useState(null);
    const generationMutation = useMutation({
        mutationFn: async () => {
            setStatus('running');
            setOutput([]);
            setStartTime(new Date());
            setEndTime(null);
            const response = await triggerDataGeneration();
            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            if (!reader) {
                throw new Error('Response body is not readable');
            }
            const lines = [];
            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done)
                        break;
                    const text = decoder.decode(value, { stream: true });
                    const newLines = text.split('\n').filter(line => line.trim());
                    lines.push(...newLines);
                    // Update output state
                    setOutput(prev => [...prev, ...newLines]);
                }
                setStatus('completed');
                setEndTime(new Date());
            }
            catch (error) {
                setStatus('failed');
                setEndTime(new Date());
                throw error;
            }
        },
        onError: (error) => {
            setStatus('failed');
            setEndTime(new Date());
            setOutput(prev => [...prev, `❌ Error: ${error instanceof Error ? error.message : String(error)}`]);
        },
    });
    const handleGenerate = () => {
        generationMutation.mutate();
    };
    const statusClass = `status-pill ${status}`;
    const duration = startTime && endTime
        ? Math.round((endTime.getTime() - startTime.getTime()) / 1000)
        : null;
    return (_jsxs("div", { children: [_jsxs("div", { className: "button-row", style: { marginBottom: '1.5rem' }, children: [_jsx("button", { className: "primary-button", onClick: handleGenerate, disabled: status === 'running', children: status === 'running' ? 'Generating data…' : 'Generate Data' }), status !== 'idle' && (_jsxs("span", { className: statusClass, children: [status === 'running' && '⏳ RUNNING', status === 'completed' && '✅ COMPLETED', status === 'failed' && '❌ FAILED'] }))] }), (startTime || endTime) && (_jsxs("div", { className: "status-grid", style: { marginBottom: '1.5rem' }, children: [startTime && (_jsxs("div", { children: [_jsx("dt", { children: "Started" }), _jsx("dd", { children: startTime.toLocaleString() })] })), endTime && (_jsxs("div", { children: [_jsx("dt", { children: "Finished" }), _jsx("dd", { children: endTime.toLocaleString() })] })), duration !== null && (_jsxs("div", { children: [_jsx("dt", { children: "Duration" }), _jsxs("dd", { children: [duration, "s"] })] }))] })), output.length > 0 && (_jsxs("div", { children: [_jsx("h3", { children: "Generation Output" }), _jsxs("div", { style: {
                            backgroundColor: '#1e1e1e',
                            color: '#d4d4d4',
                            padding: '1rem',
                            borderRadius: '4px',
                            maxHeight: '400px',
                            overflow: 'auto',
                            fontSize: '0.85rem',
                            fontFamily: 'monospace',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word'
                        }, children: [output.map((line, index) => (_jsx("div", { children: line }, index))), status === 'running' && (_jsx("div", { style: { marginTop: '0.5rem', color: '#4caf50' }, children: "\u25B6 Generating... (streaming output)" }))] })] })), status === 'idle' && (_jsx("div", { className: "empty-state", children: "Click \"Generate Data\" to create users, products, and clickstream events. This will generate data and upload it to MinIO." }))] }));
}
export default SimulationControls;
