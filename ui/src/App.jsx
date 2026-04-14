import React, { useState, useEffect, useCallback } from 'react';
import './dashboard.css';

// ── helpers ──────────────────────────────────────────────────────────────────

function fmt(isoStr, fallback = '—') {
  if (!isoStr) return fallback;
  // If the string is naive (from sync_engine), assume it's already in server's local time (NY).
  // If we append 'Z' or something, Date will treat it as UTC.
  // Instead, we'll parse it and then format with the America/New_York timezone.

  let dt;
  if (isoStr.includes('T') || isoStr.includes(' ')) {
    // If it lacks timezone info, we might need to be careful.
    // Most browsers treat 'YYYY-MM-DD HH:MM:SS' as local. 
    // If we want it to be NY time specifically:
    dt = new Date(isoStr);
  } else {
    dt = new Date(isoStr);
  }

  if (isNaN(dt)) return isoStr;

  return dt.toLocaleString('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
}

function num(v, decimals = 0) {
  if (v === null || v === undefined) return '—';
  return decimals > 0 ? Number(v).toFixed(decimals) : Number(v).toLocaleString();
}

function RelativeTime({ timestamp, serverTime }) {
  const [text, setText] = useState('—');

  useEffect(() => {
    if (!timestamp || !serverTime) {
      setText('—');
      return;
    }

    const update = () => {
      const ts = new Date(timestamp).getTime();
      const server = new Date(serverTime).getTime();
      const localAtFetch = Date.now();
      
      const now = server + (Date.now() - localAtFetch);
      const diffSec = Math.floor((now - ts) / 1000);

      if (diffSec < 60) {
        setText('just now');
      } else if (diffSec < 3600) {
        const m = Math.floor(diffSec / 60);
        setText(`${m}m ago`);
      } else {
        const h = Math.floor(diffSec / 3600);
        const m = Math.floor((diffSec % 3600) / 60);
        setText(`${h}h ${m}m ago`);
      }
    };

    update();
    const timer = setInterval(update, 30000); // update every 30s
    return () => clearInterval(timer);
  }, [timestamp, serverTime]);

  return <span>{text}</span>;
}

// ── sub-components ───────────────────────────────────────────────────────────

function MetricCard({ label, value, accent }) {
  return (
    <div className={`metric-card${accent ? ' metric-card--accent' : ''}`}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}


function ElapsedTimer({ startTime, serverTime, isRunning }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!startTime || !serverTime) return;

    const start = new Date(startTime).getTime();
    const server = new Date(serverTime).getTime();
    const localAtFetch = Date.now();

    const update = () => {
      const now = Date.now();
      const timeSinceFetch = now - localAtFetch;
      const currentServerTime = server + timeSinceFetch;
      const diff = Math.max(0, Math.floor((currentServerTime - start) / 1000));
      setElapsed(diff);
    };

    update();
    if (isRunning) {
      const timer = setInterval(update, 1000);
      return () => clearInterval(timer);
    }
  }, [startTime, serverTime, isRunning]);

  if (!startTime) return '—';

  const h = Math.floor(elapsed / 3600);
  const m = Math.floor((elapsed % 3600) / 60);
  const s = elapsed % 60;

  return (
    <span className="elapsed-value">
      {h.toString().padStart(2, '0')}:{m.toString().padStart(2, '0')}:{s.toString().padStart(2, '0')}
    </span>
  );
}

function ServerTimeClock({ serverTime }) {
  const [now, setNow] = useState(null);

  useEffect(() => {
    if (!serverTime) return;
    const base = new Date(serverTime).getTime();
    const localAtFetch = Date.now();

    const tick = () => {
      const elapsed = Date.now() - localAtFetch;
      setNow(new Date(base + elapsed));
    };

    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [serverTime]);

  if (!now) return null;

  return (
    <div className="server-time-display">
      <span className="server-time-label">SERVER TIME (NY)</span>
      <span className="server-time-value">
        {now.toLocaleString('en-US', {
          timeZone: 'America/New_York',
          hour: '2-digit', minute: '2-digit', second: '2-digit',
          hour12: false
        })}
      </span>
    </div>
  );
}

function StatusCircle({ status, isRunning }) {
  let state = 'idle';
  if (status === 'error') state = 'error';
  else if (isRunning) state = 'running';
  else if (status === 'online') state = 'online';

  return (
    <div className={`status-circle status-circle--${state}`} title={`Status: ${state}`}>
      {state === 'running' && <div className="status-circle__pulse" />}
    </div>
  );
}

function RunInfoStrip({ run, serverTime }) {
  if (!run) return <p className="no-run">No active run data.</p>;
  const isRunning = !run.EndTime;

  return (
    <div className="run-strip">
      <div className="run-strip__main">
        <div className="run-identity">
          <div className="run-field">
            <span className="run-field-label">RUN</span>
            <span className="run-field-value">{run.RunId ?? '—'}</span>
          </div>
          <div className="run-field">
            <span className="run-field-label">PRODUCT</span>
            <span className="run-field-value">{run.ProductId || '—'}</span>
          </div>
        </div>

        <div className="run-timer">
          <span className="run-field-label">ELAPSED TIME</span>
          <ElapsedTimer startTime={run.StartTime} serverTime={serverTime} isRunning={isRunning} />
        </div>
      </div>

      <div className="run-stats-grid">
        <div className="stat-item">
          <span className="stat-label">DETECTED</span>
          <span className="stat-value">{num(run.nDetected)}</span>
        </div>
        <div className="stat-item stat-item--good">
          <span className="stat-label">PASSED</span>
          <span className="stat-value">{num(run.nPassed)}</span>
          <span className="stat-pct">{run.nDetected ? num((run.nPassed / run.nDetected) * 100, 1) : 0}%</span>
        </div>
        <div className="stat-item stat-item--marginal">
          <span className="stat-label">MARGINAL</span>
          <span className="stat-value">{num(run.nMarginal)}</span>
          <span className="stat-pct">{run.nDetected ? num((run.nMarginal / run.nDetected) * 100, 1) : 0}%</span>
        </div>
        <div className="stat-item stat-item--bad">
          <span className="stat-label">REJECTED</span>
          <span className="stat-value">{num(run.nRejected)}</span>
          <span className="stat-pct">{run.nDetected ? num((run.nRejected / run.nDetected) * 100, 1) : 0}%</span>
        </div>
      </div>

      <div className="run-times-footer">
        <div className="footer-left">
          <span>Started: {fmt(run.StartTime)}</span>
          <span>Last Sample: {fmt(run.LastTime)}</span>
        </div>
        <div className="footer-right">
          {run.LastUpdate && (
            <span className="last-update-tag">
              Last Value Change: <RelativeTime timestamp={run.LastUpdate} serverTime={serverTime} />
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function VncModal({ vncConfig, lineData, onClose }) {
  if (!vncConfig) return null;
  const { host, port, password } = vncConfig;
  const viewerUrl = `/vnc_viewer.html?host=${host}&port=${port}&password=${password}`;

  // Metrics for the QC panel
  const run = lineData?.run;
  const minuteStats = lineData?.minuteStats;
  const serverTime = lineData?.serverTime;
  const isRunning = run && !run.EndTime;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content vnc-qc-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-header__title">
            <div className="vnc-label">VNC REMOTE</div>
            <h3>{lineData?.lineName || 'Machine'}: {host}</h3>
          </div>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        
        <div className="modal-body qc-split-layout">
          <div className="qc-vnc-panel">
            <iframe 
              src={viewerUrl} 
              title="VNC Viewer"
              className="vnc-iframe"
            />
          </div>
          
          <aside className="qc-side-panel">
            <div className="qc-section-header">LIVE QUALITY CONTROL</div>
            
            <div className="qc-run-info">
              <div className="qc-run-id">
                <span className="qc-label">RUN ID</span>
                <span className="qc-value">{run?.RunId || '—'}</span>
              </div>
              <div className="qc-run-timer">
                <span className="qc-label">ELAPSED</span>
                <ElapsedTimer startTime={run?.StartTime} serverTime={serverTime} isRunning={isRunning} />
              </div>
            </div>

            <div className="qc-stats-grid">
              <div className="qc-stat-box">
                <span className="qc-label">DETECTED</span>
                <span className="qc-value">{num(run?.nDetected)}</span>
              </div>
              <div className="qc-stat-box qc-stat-box--good">
                <span className="qc-label">PASSED</span>
                <span className="qc-value">{num(run?.nPassed)}</span>
                <span className="qc-pct">{run?.nDetected ? num((run.nPassed / run.nDetected) * 100, 1) : 0}%</span>
              </div>
              <div className="qc-stat-box qc-stat-box--bad">
                <span className="qc-label">REJECTED</span>
                <span className="qc-value">{num(run?.nRejected)}</span>
                <span className="qc-pct">{run?.nDetected ? num((run.nRejected / run.nDetected) * 100, 1) : 0}%</span>
              </div>
            </div>

            {minuteStats && (
              <div className="qc-minute-section">
                <div className="qc-section-header">LAST MINUTE PERFORMANCE</div>
                <div className="qc-min-stats">
                  <div className="qc-min-item">
                    <span className="qc-label">DET</span>
                    <span className="qc-value">{num(minuteStats.nDetected)}</span>
                  </div>
                  <div className="qc-min-item">
                    <span className="qc-label">PASS</span>
                    <span className="qc-value text-green">{num(minuteStats.nPassed)}</span>
                  </div>
                  <div className="qc-min-item">
                    <span className="qc-label">REJ</span>
                    <span className="qc-value text-red">{num(minuteStats.nRejected)}</span>
                  </div>
                </div>
              </div>
            )}

            <div className="qc-footer">
              <div className="qc-tag">QC MODE ACTIVE</div>
              {run?.LastUpdate && (
                <div className="qc-last-update">
                  Update: <RelativeTime timestamp={run.LastUpdate} serverTime={serverTime} />
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function VncCard({ host, port, password, lineData, onOpen }) {
  if (!host) return null;
  
  return (
    <div className="vnc-card">
      <div className="vnc-card__header">
        <h3>REMOTE ACCESS <span className="vnc-label">VNC</span></h3>
      </div>
      <div className="vnc-card__body">
        <div className="vnc-info">
          <div className="vnc-field">
            <span className="vnc-field-label">IP</span>
            <span className="vnc-field-value">{host}</span>
          </div>
          <div className="vnc-field">
            <span className="vnc-field-label">PORT</span>
            <span className="vnc-field-value">{port}</span>
          </div>
        </div>
        <button onClick={() => onOpen({ vncConfig: { host, port, password }, lineData })} className="vnc-link-btn">
          OPEN SCREEN
        </button>
      </div>
    </div>
  );
}

function MinuteStatsCard({ lineName, stats }) {
  if (!stats) return null;
  
  return (
    <div className="minute-card">
      <div className="minute-card__header">
        <h3>{lineName} <span className="minute-label">LAST MINUTE</span></h3>
      </div>
      <div className="minute-card__body">
        <div className="min-stat">
          <span className="min-stat-label">DET</span>
          <span className="min-stat-value">{num(stats.nDetected)}</span>
        </div>
        <div className="min-stat">
          <span className="min-stat-label">PASS</span>
          <span className="min-stat-value text-green">{num(stats.nPassed)}</span>
        </div>
        <div className="min-stat">
          <span className="min-stat-label">REJ</span>
          <span className="min-stat-value text-red">{num(stats.nRejected)}</span>
        </div>
      </div>
    </div>
  );
}

function LineCard({ lineName, status, run, minuteStats, serverTime, vncPort, vncPassword, onVncOpen }) {
  const isOnline = status?.status === 'online';
  const hasError = status?.status === 'error';
  const isRunning = run && !run.EndTime;

  const lineData = { lineName, status, run, minuteStats, serverTime };

  return (
    <div className="line-container">
      <section className={`line-card ${hasError ? 'line-card--error' : ''} ${isRunning ? 'line-card--running' : ''}`}>
        <header className="line-card__header">
          <div className="line-card__title">
            <StatusCircle status={status?.status} isRunning={isRunning} />
            <h2>{lineName}</h2>
            {isRunning && <span className="running-tag">RUNNING</span>}
          </div>
          <div className="line-card__meta">
            {status?.last_sync && (
              <span className="last-contact">Synced {fmt(status.last_sync)}</span>
            )}
          </div>
        </header>

        {hasError && (
          <div className="error-banner">⚠ {status.error || 'Sync Error'}</div>
        )}

        <RunInfoStrip run={run} serverTime={serverTime} />
      </section>
      
      <div className="line-extra-row">
        {minuteStats && <MinuteStatsCard lineName={lineName} stats={minuteStats} />}
        <VncCard 
          host={status?.host} 
          port={vncPort} 
          password={vncPassword} 
          lineData={lineData}
          onOpen={onVncOpen} 
        />
      </div>
    </div>
  );
}

// ── countdown ring ────────────────────────────────────────────────────────────

function Countdown({ seconds, total }) {
  const pct = seconds / total;
  const r = 16;
  const circ = 2 * Math.PI * r;
  const dash = circ * pct;
  return (
    <div className="countdown" title={`Next refresh in ${seconds}s`}>
      <svg width="40" height="40" viewBox="0 0 40 40">
        <circle cx="20" cy="20" r={r} className="countdown-track" />
        <circle
          cx="20" cy="20" r={r}
          className="countdown-arc"
          strokeDasharray={`${dash} ${circ}`}
          strokeDashoffset={circ / 4}
        />
      </svg>
      <span className="countdown-text">{seconds}s</span>
    </div>
  );
}

// ── main app ──────────────────────────────────────────────────────────────────

const REFRESH_INTERVAL = 60; // seconds

export default function App() {
  const [status, setStatus] = useState({ lines: {}, last_sync: null });
  const [runs, setRuns] = useState({});
  const [minuteStats, setMinuteStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeVnc, setActiveVnc] = useState(null);
  const [error, setError] = useState(null);
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL);

  const fetchAll = useCallback(() => {
    setCountdown(REFRESH_INTERVAL);
    Promise.all([
      fetch('/api/status').then(r => r.json()),
      fetch('/api/runs').then(r => r.json()),
      fetch('/api/minute_stats').then(r => r.json()),
    ])
      .then(([s, ru, ms]) => {
        setStatus(s);
        setRuns(ru);
        setMinuteStats(ms);
        setError(null);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Initial fetch + 60-second interval
  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, REFRESH_INTERVAL * 1000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  // Countdown tick
  useEffect(() => {
    const tick = setInterval(() => {
      setCountdown(c => (c > 0 ? c - 1 : 0));
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  // Merge all known lines from both sources
  const allLines = Array.from(
    new Set([...Object.keys(status.lines), ...Object.keys(runs)])
  ).sort();

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="dashboard-header__left">
          <div className="dashboard-logo">VX</div>
          <div>
            <h1 className="dashboard-title">VisionX Control Dashboard</h1>
            <p className="dashboard-subtitle">
              Production Line Monitor — auto-refresh 60s
            </p>
          </div>
        </div>

        <ServerTimeClock serverTime={status.serverTime} />

        <div className="dashboard-header__right">
          <Countdown seconds={countdown} total={REFRESH_INTERVAL} />
          <button className="refresh-btn" onClick={fetchAll} title="Refresh now">↻</button>
          {status.last_sync && (
            <span className="global-sync">
              Last cycle: {fmt(status.last_sync)}
            </span>
          )}
        </div>
      </header>

      <main className="dashboard-main">
        {loading && <div className="spinner-wrap"><div className="spinner" /></div>}
        {error && <div className="global-error">⚠ API error: {error}</div>}
        {!loading && allLines.length === 0 && (
          <div className="empty-state">
            <p>⏳ Initial sync in progress — waiting for first cycle…</p>
          </div>
        )}
        <div className="lines-list">
          {allLines.map(line => (
            <LineCard
              key={line}
              lineName={line}
              status={status.lines[line]}
              run={runs[line]}
              minuteStats={minuteStats[line]}
              serverTime={status.serverTime}
              vncPort={status.vnc_port}
              vncPassword={status.vnc_password}
              onVncOpen={setActiveVnc}
            />
          ))}
        </div>
      </main>

      <VncModal 
        vncConfig={activeVnc?.vncConfig} 
        lineData={activeVnc?.lineData}
        onClose={() => setActiveVnc(null)} 
      />
    </div>
  );
}
