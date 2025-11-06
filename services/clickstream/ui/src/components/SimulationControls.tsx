import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';

import { triggerDataGeneration } from '../lib/api';

type GenerationStatus = 'idle' | 'running' | 'completed' | 'failed';

function SimulationControls(): JSX.Element {
  const [status, setStatus] = useState<GenerationStatus>('idle');
  const [output, setOutput] = useState<string[]>([]);
  const [startTime, setStartTime] = useState<Date | null>(null);
  const [endTime, setEndTime] = useState<Date | null>(null);

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

      const lines: string[] = [];
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const text = decoder.decode(value, { stream: true });
          const newLines = text.split('\n').filter(line => line.trim());
          lines.push(...newLines);
          
          // Update output state
          setOutput(prev => [...prev, ...newLines]);
        }
        
        setStatus('completed');
        setEndTime(new Date());
      } catch (error) {
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

  return (
    <div>
      <div className="button-row" style={{ marginBottom: '1.5rem' }}>
        <button 
          className="primary-button" 
          onClick={handleGenerate} 
          disabled={status === 'running'}
        >
          {status === 'running' ? 'Generating data…' : 'Generate Data'}
        </button>
        
        {status !== 'idle' && (
          <span className={statusClass}>
            {status === 'running' && '⏳ RUNNING'}
            {status === 'completed' && '✅ COMPLETED'}
            {status === 'failed' && '❌ FAILED'}
          </span>
        )}
      </div>

      {(startTime || endTime) && (
        <div className="status-grid" style={{ marginBottom: '1.5rem' }}>
          {startTime && (
            <div>
              <dt>Started</dt>
              <dd>{startTime.toLocaleString()}</dd>
            </div>
          )}
          {endTime && (
            <div>
              <dt>Finished</dt>
              <dd>{endTime.toLocaleString()}</dd>
            </div>
          )}
          {duration !== null && (
            <div>
              <dt>Duration</dt>
              <dd>{duration}s</dd>
            </div>
          )}
        </div>
      )}

      {output.length > 0 && (
        <div>
          <h3>Generation Output</h3>
          <div 
            style={{ 
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
            }}
          >
            {output.map((line, index) => (
              <div key={index}>{line}</div>
            ))}
            {status === 'running' && (
              <div style={{ marginTop: '0.5rem', color: '#4caf50' }}>
                ▶ Generating... (streaming output)
              </div>
            )}
          </div>
        </div>
      )}

      {status === 'idle' && (
        <div className="empty-state">
          Click "Generate Data" to create users, products, and clickstream events.
          This will generate data and upload it to MinIO.
        </div>
      )}
    </div>
  );
}

export default SimulationControls;

