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

function rejectPct(rejected, detected) {
  if (!detected || detected === 0) return '0%';
  const pct = (rejected / detected) * 100;
  return pct.toFixed(1) + '%';
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

function StatusCircle({ status, isRunning, isStopped }) {
  let state = 'idle';
  if (status === 'error') state = 'error';
  else if (isStopped) state = 'error';
  else if (isRunning) state = 'running';
  else if (status === 'online') state = 'online';
  else state = 'idle';

  return (
    <div className={`status-circle status-circle--${state}`} title={`Status: ${state}`}>
      {state === 'running' && <div className="status-circle__pulse" />}
    </div>
  );
}

function RunInfoStrip({ run, serverTime, isRunning }) {
  if (!run) return <p className="no-run">No active run data.</p>;
  const isActuallyStopped = !run.EndTime && !isRunning;

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
  const hourStats = lineData?.hourStats;
  const serverTime = lineData?.serverTime;
  const isRunning = run && !run.EndTime;

  const handleClose = (e) => {
    if (e) e.stopPropagation();
    const iframe = document.getElementById('vnc-frame');
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage({ type: 'DISCONNECT' }, '*');
    }
    setTimeout(onClose, 100);
  };

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content vnc-qc-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-header__title">
            <div className="vnc-label">VNC REMOTE</div>
            <div className="vnc-header-line">
              <h3>{lineData?.lineName || 'Machine'}{host !== lineData?.lineName ? ` (${host})` : ''}</h3>
            </div>
            <div className="vnc-header-meta">
              <div className="vnc-meta-item">
                <span className="meta-label">RUN</span>
                <span className="meta-value">{run?.RunId || '—'}</span>
              </div>
              <div className="vnc-meta-item vnc-meta-item--accent">
                <span className="meta-label">ELAPSED</span>
                <span className="meta-value">
                  <ElapsedTimer startTime={run?.StartTime} serverTime={serverTime} isRunning={isRunning} />
                </span>
              </div>
            </div>
          </div>
          <button className="modal-close" onClick={handleClose}>×</button>
        </div>
        
        <div className="modal-body">
          <div className="qc-stats-bar">
            {/* Cumulative Stats */}
            <div className="qc-stats-group">
              <div className="qc-group-label">STATS</div>
              <div className="qc-stat-card">
                <span className="qc-label">DETECTED</span>
                <span className="qc-value">{num(run?.nDetected)}</span>
              </div>
              <div className="qc-stat-card qc-stat-card--good">
                <span className="qc-label">PASSED</span>
                <span className="qc-value">
                  {num(run?.nPassed)} <span style={{opacity: 0.6}}>({run?.nDetected ? num((run.nPassed / run.nDetected) * 100, 1) : 0}%)</span>
                </span>
              </div>
              <div className="qc-stat-card qc-stat-card--bad">
                <span className="qc-label">REJECTED</span>
                <span className="qc-value">
                  {num(run?.nRejected)} <span style={{opacity: 0.6}}>({run?.nDetected ? num((run.nRejected / run.nDetected) * 100, 1) : 0}%)</span>
                </span>
              </div>
            </div>

            {/* Hour Stats */}
            {hourStats && (
              <div className="qc-stats-group">
                <div className="qc-group-label">L.HOUR</div>
                <div className="qc-stat-card">
                  <span className="qc-label">DET / PASS</span>
                  <span className="qc-value">
                    {num(hourStats.nDetected)} / <span className="text-green">{num(hourStats.nPassed)}</span>
                  </span>
                </div>
                <div className="vnc-stat-group">
                  <div className="vnc-stat">
                    <span className="vnc-stat-label">LAST HOUR REJECTED</span>
                    <span className="vnc-stat-value vnc-stat-value--rejected">
                      {num(lineData.hourStats?.nRejected)} ({rejectPct(lineData.hourStats?.nRejected, lineData.hourStats?.nDetected)})
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Sync Info */}
            <div className="qc-stats-group">
              <div className="qc-group-label">SYNC</div>
              <div className="qc-stat-card">
                <span className="qc-label">LAST UPDATE</span>
                <span className="qc-value">
                  {run?.LastUpdate ? <RelativeTime timestamp={run.LastUpdate} serverTime={serverTime} /> : '—'}
                </span>
              </div>
            </div>
          </div>

          <iframe 
            id="vnc-frame"
            src={viewerUrl} 
            title="VNC Viewer"
            className="vnc-iframe"
          />
        </div>
      </div>
    </div>
  );
}

function VncCard({ lineName, host, port, password, lineData, onOpen }) {
  const vncHost = host || lineName;
  if (!vncHost) return null;
  
  return (
    <div className="vnc-card">
      <div className="vnc-card__header">
        <h3>REMOTE ACCESS <span className="vnc-label">VNC</span></h3>
      </div>
      <div className="vnc-card__body">
        <div className="vnc-info">
          <div className="vnc-field">
            <span className="vnc-field-label">IP / HOST</span>
            <span className="vnc-field-value">{host || lineName}</span>
          </div>
          <div className="vnc-field">
            <span className="vnc-field-label">PORT</span>
            <span className="vnc-field-value">{port || '5900'}</span>
          </div>
        </div>
        <button 
          onClick={() => onOpen({ vncConfig: { host: vncHost, port: port || '5900', password: password || '1043' }, lineData })} 
          className="vnc-link-btn"
        >
          OPEN SCREEN
        </button>
      </div>
    </div>
  );
}

function HourStatsCard({ lineName, stats }) {
  if (!stats) return null;
  return (
    <div className="hour-stats-card">
      <div className="hour-stats-title">LAST HOUR</div>
      <div className="hour-stats-grid">
        <div className="hs-item">
          <div className="hs-val">{num(stats.nDetected)}</div>
          <div className="hs-lab">DETECTED</div>
        </div>
        <div className="hs-item">
          <div className="hs-val hs-val--rejected">{num(stats.nRejected)}</div>
          <div className="hs-lab">REJECTED ({rejectPct(stats.nRejected, stats.nDetected)})</div>
        </div>
      </div>
    </div>
  );
}

function LineCard({ lineName, status, run, hourStats, serverTime, vncPort, vncPassword, onVncOpen }) {
  const minutesThreshold = status?.minutes_last_update || 10;
  const hasError = status?.status === 'error';
  const lastUpdateMs = run?.LastUpdate ? new Date(run.LastUpdate).getTime() : 0;
  const serverNowMs = serverTime ? new Date(serverTime).getTime() : Date.now();
  const diffMinutes = (serverNowMs - lastUpdateMs) / 60000;
  
  const isStale = run?.LastUpdate && diffMinutes > minutesThreshold;
  const isRunning = run?.isRunning || false;
  const isStopped = !isRunning && run && !run.EndTime;

  const lineData = { lineName, status, run, hourStats, serverTime, isRunning };

  return (
    <div className="line-container">
      <section className={`line-card ${hasError ? 'line-card--error' : ''} ${isRunning ? 'line-card--running' : ''} ${isStopped ? 'line-card--stopped' : ''}`}>
        <header className="line-card__header">
          <div className="line-card__title">
            <StatusCircle status={status?.status} isRunning={isRunning} isStopped={isStopped} />
            <h2>{lineName}</h2>
            {isRunning && <span className="running-tag">RUNNING</span>}
            {isStopped && <span className="running-tag running-tag--stopped">STOPPED</span>}
          </div>
          <div className="line-card__meta">
            {status?.ping !== undefined && (
              <span className={`ping-dot ${status.ping ? 'ping-dot--ok' : 'ping-dot--fail'}`} title={status.ping ? 'Host is pinging reliably' : 'Host is not responding to ping'}>
                {status.ping ? 'PING OK' : 'PING FAIL'}
              </span>
            )}
            {status?.last_sync && (
              <span className="last-contact">Synced {fmt(status.last_sync)}</span>
            )}
          </div>
        </header>

        {hasError && (
          <div className="error-banner">
            <span className="error-label">Error Message</span>
            <span className="error-message">{status.error || 'Sync Error'}</span>
          </div>
        )}

        <RunInfoStrip run={run} serverTime={serverTime} isRunning={isRunning} />
      </section>
      
      <div className="line-extra-row">
        {hourStats && <HourStatsCard lineName={lineName} stats={hourStats} />}
        <VncCard 
          lineName={lineName}
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
  const [hourStats, setHourStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeVnc, setActiveVnc] = useState(null);
  const [error, setError] = useState(null);
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL);

  const fetchStatusOnly = useCallback(() => {
    fetch('/api/status').then(r => r.json())
      .then(s => setStatus(prev => ({ ...prev, ...s })))
      .catch(err => console.error("Ping sync error:", err));
  }, []);

  const fetchAll = useCallback(() => {
    setCountdown(REFRESH_INTERVAL);
    Promise.all([
      fetch('/api/status').then(r => r.json()),
      fetch('/api/runs').then(r => r.json()),
      fetch('/api/minute_stats').then(r => r.json()),
    ])
      .then(([s, ru, hs]) => {
        setStatus(s);
        setRuns(ru);
        setHourStats(hs);
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

  // Ping update 10-second interval
  useEffect(() => {
    const pingInterval = setInterval(fetchStatusOnly, 10000);
    return () => clearInterval(pingInterval);
  }, [fetchStatusOnly]);

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
        {error && (
          <div className="global-error">
            <span className="error-label" style={{ borderRadius: '4px' }}>API ERROR</span>
            <span className="error-message">{error}</span>
          </div>
        )}
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
              hourStats={hourStats[line]}
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
