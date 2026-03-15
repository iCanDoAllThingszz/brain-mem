import { useEffect, useState } from 'react';
import { Terminal, X, Zap, ArrowRight, BrainCircuit } from 'lucide-react';
import './ActivityStream.css'; // We'll create this next

interface LogEntry {
  time: string;
  type: string;
  summary: string;
  details?: any;
}

export default function ActivityStream({ onClose }: { onClose: () => void }) {
  const [logs, setLogs] = useState<LogEntry[]>([]);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const res = await fetch('http://localhost:8100/logs?n=50');
        const json = await res.json();
        
        if (json.logs) {
          const parsedLogs = json.logs.split('\n')
            .filter(Boolean)
            .map((line: string) => {
              const match = line.match(/^\[(.*?)\] (.*?): (.*?)(?: \| (.*))?$/);
              if (match) {
                return {
                  time: match[1],
                  type: match[2],
                  summary: match[3],
                  details: match[4]
                };
              }
              return { time: '', type: 'info', summary: line };
            })
            .reverse();
            
          setLogs(parsedLogs);
        }
      } catch (e) {
        console.error("Failed to fetch logs", e);
      }
    };
    
    fetchLogs();
    const int = setInterval(fetchLogs, 5000);
    return () => clearInterval(int);
  }, []);

  const getLogIcon = (type: string) => {
    if (type.includes('encoder')) return <BrainCircuit size={16} className="icon-procedural" />;
    if (type.includes('retriever')) return <ArrowRight size={16} className="icon-semantic" />;
    if (type.includes('perceiver')) return <Zap size={16} className="icon-concept" />;
    return <Terminal size={16} className="icon-default" />;
  };

  const getLogClass = (type: string) => {
    if (type.includes('encoder')) return 'log-item procedural';
    if (type.includes('retriever')) return 'log-item semantic';
    if (type.includes('perceiver')) return 'log-item concept';
    return 'log-item default';
  };

  return (
    <div className="activity-stream-panel">
      <div className="activity-header">
        <h2>
          <Terminal size={16} className="header-icon-primary" />
          Processing Path Stream
        </h2>
        <button onClick={onClose} className="close-btn">
          <X size={20} />
        </button>
      </div>
      
      <div className="activity-content">
        {logs.map((log, i) => (
          <div 
            key={i} 
            className={getLogClass(log.type)}
            style={{ animationDelay: `${i * 0.05}s` }}
          >
            <div className="log-meta">
              {getLogIcon(log.type)}
              <span className="log-type">{log.type}</span>
              <span className="log-time">{log.time.split(' ')[1]}</span>
            </div>
            <p className="log-summary">{log.summary}</p>
            {log.details && (
              <p className="log-details">
                {log.details}
              </p>
            )}
          </div>
        ))}
        {logs.length === 0 && (
          <div className="empty-state">
            <Terminal size={32} />
            <p>Waiting for neural activity...</p>
          </div>
        )}
      </div>
    </div>
  );
}
