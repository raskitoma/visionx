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
      } else if (diffSec < 86400) {
        const h = Math.floor(diffSec / 3600);
        const m = Math.floor((diffSec % 3600) / 60);
        setText(`${h}h ${m}m ago`);
      } else {
        setText('More than 24h ago');
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
  const isRunning = lineData?.isRunning;

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
                <div className="qc-stat-card qc-stat-card--bad">
                  <span className="qc-label">REJECTED</span>
                  <span className="qc-value">
                    {num(hourStats.nRejected)} <span style={{opacity: 0.6}}>({rejectPct(hourStats.nRejected, hourStats.nDetected)})</span>
                  </span>
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
    <div className="hour-card">
      <div className="hour-card__header">
        <span className="hour-label">LAST HOUR</span>
      </div>
      <div className="hour-card__body">
        <div className="hs-item">
          <span className="hs-label">DETECTED</span>
          <span className="hs-value">{num(stats.nDetected)}</span>
        </div>
        <div className="hs-item">
          <span className="hs-label">REJECTED</span>
          <span className="hs-value hs-value--rejected">
            {num(stats.nRejected)} <span className="hs-pct">({rejectPct(stats.nRejected, stats.nDetected)})</span>
          </span>
        </div>
      </div>
    </div>
  );
}

function LineCard({ lineName, status, run, hourStats, serverTime, vncPort, vncPassword, onVncOpen, recentAlert, onAlertClick, onDismissAlert }) {
  const minutesThreshold = status?.minutes_last_update || 10;
  const hasError = status?.status === 'error';
  const lastUpdateMs = run?.LastUpdate ? new Date(run.LastUpdate).getTime() : 0;
  const serverNowMs = serverTime ? new Date(serverTime).getTime() : Date.now();
  const diffMinutes = (serverNowMs - lastUpdateMs) / 60000;
  
  const isStale = run?.LastUpdate && diffMinutes > minutesThreshold;
  // Use the backend isRunning status but override with local staleness check
  // to ensure immediate UI feedback when the threshold is crossed.
  const isRunning = run?.isRunning && !isStale;
  const isStopped = !isRunning && run && !run.EndTime;

  const lineData = { lineName, status, run, hourStats, serverTime, isRunning };

  return (
    <div className="line-container">
      <section className={`line-card ${hasError ? 'line-card--error' : ''} ${isRunning ? 'line-card--running' : ''} ${isStopped ? 'line-card--stopped' : ''} ${recentAlert ? 'line-card--alerted' : ''}`}>
        <header className="line-card__header">
          <div className="line-card__title">
            <StatusCircle status={status?.status} isRunning={isRunning} isStopped={isStopped} />
            <h2>{lineName}</h2>
            {isRunning && <span className="running-tag">RUNNING</span>}
            {isStopped && <span className="running-tag running-tag--stopped">STOPPED</span>}
            {recentAlert && (
              <div className="alarm-wrapper">
                <button 
                  className="alarmed-badge" 
                  onClick={(e) => {
                    e.stopPropagation();
                    onAlertClick(lineName, recentAlert.id);
                  }}
                  title="Active Specs Violation Alert in the last 30 minutes. Click to view alert log."
                >
                  ⚠️ ALARM ACTIVE
                </button>
                <button
                  className="alarm-dismiss-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDismissAlert(recentAlert.id);
                  }}
                  title="Dismiss this alert"
                >
                  ✕
                </button>
              </div>
            )}
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
        <Averages30mStrip averages={run?.averages_30m} />
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

function Averages30mStrip({ averages }) {
  if (!averages) {
    return (
      <div className="avg-30m-strip empty">
        <span className="avg-30m-label">LAST 30 MIN AVG</span>
        <span className="avg-30m-no-data">No sample data in the last 30 minutes</span>
      </div>
    );
  }

  const val = (v, dec = 2) => {
    if (v === null || v === undefined) return '—';
    return Number(v).toFixed(dec);
  };

  return (
    <div className="avg-30m-strip">
      <span className="avg-30m-label">LAST 30 MIN AVG</span>
      <div className="avg-30m-grid">
        <div className="avg-30m-item" title="Diameter Major/Minor/Average">
          <span className="avg-label">DIA (MAJ/MIN/AVG)</span>
          <span className="avg-val">{val(averages.DMajor)} / {val(averages.DMinor)} / {val(averages.DAvg)}</span>
        </div>
        <div className="avg-30m-item" title="Diameter Average Last vs Target Limits (TargetDMinorMin / TargetDMajorMax)">
          <span className="avg-label">DAvgLast (Min/Max Target)</span>
          <span className="avg-val">{val(averages.DAvgLast)} ({val(averages.TargetDMinorMin)} / {val(averages.TargetDMajorMax)})</span>
        </div>
        <div className="avg-30m-item" title="Edge Flatness Average">
          <span className="avg-label">FLATNESS (EF)</span>
          <span className="avg-val">{val(averages.EF)}</span>
        </div>
        <div className="avg-30m-item" title="Edge Defect Average">
          <span className="avg-label">DEFECT (ED)</span>
          <span className="avg-val">{val(averages.ED)}</span>
        </div>
        <div className="avg-30m-item" title="Hole Area Average">
          <span className="avg-label">HOLE AREA (HA)</span>
          <span className="avg-val">{val(averages.HA, 3)}</span>
        </div>
        <div className="avg-30m-item" title="Toast Average">
          <span className="avg-label">TOAST %</span>
          <span className="avg-val">{val(averages.Toast, 1)}%</span>
        </div>
        <div className="avg-30m-item" title="Raw Average">
          <span className="avg-label">RAW %</span>
          <span className="avg-val">{val(averages.Raw, 1)}%</span>
        </div>
        <div className="avg-30m-item" title="Translucent Average">
          <span className="avg-label">TRANS %</span>
          <span className="avg-val">{val(averages.Trans, 1)}%</span>
        </div>
      </div>
    </div>
  );
}

function ProductSpecsPanel({ products }) {
  const [expandedLines, setExpandedLines] = useState({});

  if (!products || Object.keys(products).length === 0) {
    return (
      <div className="empty-state">
        <p>No product specifications synced.</p>
      </div>
    );
  }

  const toggleLine = (line) => {
    setExpandedLines(prev => ({
      ...prev,
      [line]: !prev[line]
    }));
  };

  const val = (v, dec = 2) => {
    if (v === null || v === undefined) return '—';
    return Number(v).toFixed(dec);
  };

  return (
    <div className="specs-panel">
      {Object.keys(products).sort().map(line => {
        const list = products[line] || [];
        const isExpanded = !!expandedLines[line];
        const lastSync = list.length > 0 ? list[0].SyncUp : null;

        return (
          <div key={line} className="specs-accordion-card">
            <div className="specs-accordion-header" onClick={() => toggleLine(line)}>
              <div className="header-left">
                <span className="specs-arrow">{isExpanded ? '▼' : '▶'}</span>
                <h3>{line} Specifications</h3>
                <span className="specs-badge">{list.length} Products</span>
              </div>
              {lastSync && (
                <span className="specs-last-sync">Last Synced: {fmt(lastSync)}</span>
              )}
            </div>
            
            {isExpanded && (
              <div className="specs-accordion-body">
                <div className="specs-table-container">
                  <table className="specs-table">
                    <thead>
                      <tr>
                        <th>Product ID</th>
                        <th>Description</th>
                        <th>Type</th>
                        <th>D1 (Min/Target/Max)</th>
                        <th>D2 (Min/Target/Max)</th>
                        <th>DAvg (Min/Max)</th>
                        <th>Target DMinor Min</th>
                        <th>Target DMajor Max</th>
                        <th>EF Max</th>
                        <th>ED Max</th>
                        <th>HA Max</th>
                        <th>Toast Min</th>
                        <th>Raw Max</th>
                        <th>Trans Max</th>
                        <th>Last Sync</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map(p => (
                        <tr key={p.ProductId}>
                          <td style={{ fontWeight: 'bold', color: 'var(--text-bright)' }}>{p.ProductId}</td>
                          <td>{p.ProductDesc || '—'}</td>
                          <td>{p.Elliptic ? 'Elliptic' : 'Round'}</td>
                          <td>{val(p.D1Min)} / {val(p.D1Target)} / {val(p.D1Max)}</td>
                          <td>{p.Elliptic ? `${val(p.D2Min)} / ${val(p.D2Target)} / ${val(p.D2Max)}` : '—'}</td>
                          <td>{val(p.DAvgMin)} / {val(p.DAvgMax)}</td>
                          <td>{val(p.TargetDMinorMin)}</td>
                          <td>{val(p.TargetDMajorMax)}</td>
                          <td>{p.EFMax ?? '—'}</td>
                          <td>{p.EDMax ?? '—'}</td>
                          <td>{val(p.HAMax, 3)}</td>
                          <td>{p.ToastMin ?? '—'}%</td>
                          <td>{p.RawMax ?? '—'}%</td>
                          <td>{p.TransMax ?? '—'}%</td>
                          <td>{fmt(p.LastUpdate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function renderAlertDetails(details) {
  if (!details) return null;
  const violations = details.split('; ');
  const regex = /([A-Za-z0-9_]+)\s*\(([^)]+)\)\s*(is (?:above|below))\s*([A-Za-z0-9_]+)\s*\(([^)]+)\)/;

  return (
    <div className="violation-list">
      {violations.map((v, idx) => {
        const match = v.match(regex);
        if (match) {
          const [_, param, value, direction, limitName, limitVal] = match;
          return (
            <div key={idx} className="violation-item">
              <span className="violation-param">{param}</span>
              <span className="violation-val violation-val--faulty">{value}</span>
              <span className="violation-direction">{direction}</span>
              <span className="violation-limit-name">{limitName}</span>
              <span className="violation-val violation-val--limit">({limitVal})</span>
            </div>
          );
        }
        return <div key={idx} className="violation-item-raw">{v}</div>;
      })}
    </div>
  );
}

function AlertLogPanel({ alerts, filterText, setFilterText }) {
  const [sortField, setSortField] = useState('AlertTime');
  const [sortAsc, setSortAsc] = useState(false);

  // 1. Global Filtering
  const filteredAlerts = (alerts || []).filter(a => {
    if (!filterText.trim()) return true;
    const term = filterText.toLowerCase();
    
    const timeStr = a.AlertTime ? fmt(a.AlertTime).toLowerCase() : '';
    const lineStr = (a.SourceLine || '').toLowerCase();
    const runStr = String(a.RunId || '').toLowerCase();
    const prodStr = (a.ProductId || '').toLowerCase();
    const detailsStr = (a.Details || '').toLowerCase();
    const slackStr = a.SlackSentTime ? `sent ${fmt(a.SlackSentTime)}`.toLowerCase() : 'not sent';

    return (
      timeStr.includes(term) ||
      lineStr.includes(term) ||
      runStr.includes(term) ||
      prodStr.includes(term) ||
      detailsStr.includes(term) ||
      slackStr.includes(term)
    );
  });

  // 2. Sorting
  const sortedAlerts = [...filteredAlerts].sort((x, y) => {
    let valX, valY;
    if (sortField === 'AlertTime') {
      valX = x.AlertTime ? new Date(x.AlertTime).getTime() : 0;
      valY = y.AlertTime ? new Date(y.AlertTime).getTime() : 0;
    } else if (sortField === 'SourceLine') {
      valX = x.SourceLine || '';
      valY = y.SourceLine || '';
    } else if (sortField === 'RunId') {
      valX = Number(x.RunId) || 0;
      valY = Number(y.RunId) || 0;
    } else if (sortField === 'ProductId') {
      valX = x.ProductId || '';
      valY = y.ProductId || '';
    } else if (sortField === 'Details') {
      valX = x.Details || '';
      valY = y.Details || '';
    } else if (sortField === 'SlackSentTime') {
      valX = x.SlackSentTime ? new Date(x.SlackSentTime).getTime() : 0;
      valY = y.SlackSentTime ? new Date(y.SlackSentTime).getTime() : 0;
    }

    if (valX < valY) return sortAsc ? -1 : 1;
    if (valX > valY) return sortAsc ? 1 : -1;
    return 0;
  });

  const handleSort = (field) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  const renderSortIndicator = (field) => {
    if (sortField !== field) return <span className="sort-indicator-icon">⇅</span>;
    return sortAsc ? <span className="sort-indicator-icon active">▲</span> : <span className="sort-indicator-icon active">▼</span>;
  };

  return (
    <div className="alerts-panel">
      <div className="panel-header">
        <div className="panel-header-title">
          <h3>Alert History (Average in the Last 30 Minutes)</h3>
          <span className="alerts-info">Refreshed every 60s.</span>
        </div>
        <div className="alerts-search-box">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            placeholder="Search alerts..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            className="search-input"
          />
          {filterText && (
            <button onClick={() => setFilterText('')} className="clear-search-btn">
              ✕
            </button>
          )}
        </div>
      </div>

      <div className="alerts-table-container">
        {!alerts || alerts.length === 0 ? (
          <div className="empty-state">
            <p>⚠️ No alerts logged in history.</p>
          </div>
        ) : sortedAlerts.length === 0 ? (
          <div className="empty-search-state">
            <p>🔍 No alerts matching your search.</p>
          </div>
        ) : (
          <table className="alerts-table">
            <thead>
              <tr>
                <th onClick={() => handleSort('AlertTime')} style={{ width: '180px', cursor: 'pointer' }} className="sortable-th">
                  Alert Time (NY) {renderSortIndicator('AlertTime')}
                </th>
                <th onClick={() => handleSort('SourceLine')} style={{ width: '90px', cursor: 'pointer' }} className="sortable-th">
                  Line {renderSortIndicator('SourceLine')}
                </th>
                <th onClick={() => handleSort('RunId')} style={{ width: '90px', cursor: 'pointer' }} className="sortable-th">
                  Run ID {renderSortIndicator('RunId')}
                </th>
                <th onClick={() => handleSort('ProductId')} style={{ width: '120px', cursor: 'pointer' }} className="sortable-th">
                  Product ID {renderSortIndicator('ProductId')}
                </th>
                <th onClick={() => handleSort('Details')} style={{ cursor: 'pointer' }} className="sortable-th">
                  Details / Parameter Violations {renderSortIndicator('Details')}
                </th>
                <th onClick={() => handleSort('SlackSentTime')} style={{ width: '150px', cursor: 'pointer' }} className="sortable-th">
                  Slack Status {renderSortIndicator('SlackSentTime')}
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedAlerts.map(a => (
                <tr key={a.id} className="alert-row">
                  <td style={{ color: 'var(--text-bright)', fontFamily: 'JetBrains Mono, monospace' }}>{fmt(a.AlertTime)}</td>
                  <td>
                    <span className="alert-line-badge">{a.SourceLine}</span>
                  </td>
                  <td style={{ fontFamily: 'JetBrains Mono, monospace' }}>{a.RunId}</td>
                  <td style={{ fontWeight: 'bold' }}>{a.ProductId}</td>
                  <td className="alert-details-text">{renderAlertDetails(a.Details)}</td>
                  <td>
                    {a.SlackSentTime ? (
                      <span className="slack-status-badge slack-status-badge--sent" title={`Sent to Slack at ${fmt(a.SlackSentTime)}`}>
                        <span className="slack-status-icon">💬</span>
                        <span className="slack-status-text">Sent {fmt(a.SlackSentTime).split(' ')[1]}</span>
                      </span>
                    ) : (
                      <span className="slack-status-badge slack-status-badge--none" title="No Slack notification sent">
                        <span className="slack-status-icon">⚪</span>
                        <span className="slack-status-text">Not Sent</span>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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

function SettingsPanel() {
  const [webhookUrl, setWebhookUrl] = useState('');
  const [mentionTarget, setMentionTarget] = useState('');
  const [isEnabled, setIsEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    fetch('/api/settings/slack')
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch settings');
        return res.json();
      })
      .then(data => {
        setWebhookUrl(data.webhook_url || '');
        setMentionTarget(data.mention_target || '');
        setIsEnabled(!!data.is_enabled);
        setLoading(false);
      })
      .catch(err => {
        setMessage({ type: 'error', text: err.message });
        setLoading(false);
      });
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);

    fetch('/api/settings/slack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        webhook_url: webhookUrl,
        mention_target: mentionTarget,
        is_enabled: isEnabled
      })
    })
      .then(res => {
        if (!res.ok) throw new Error('Failed to save settings');
        return res.json();
      })
      .then(data => {
        setMessage({ type: 'success', text: 'Slack settings saved successfully.' });
        setSaving(false);
      })
      .catch(err => {
        setMessage({ type: 'error', text: err.message });
        setSaving(false);
      });
  };

  const handleTestConnection = () => {
    if (!webhookUrl) {
      setMessage({ type: 'error', text: 'Please enter a Webhook URL to test.' });
      return;
    }
    setTesting(true);
    setMessage(null);

    fetch('/api/settings/slack/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        webhook_url: webhookUrl,
        mention_target: mentionTarget
      })
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(data => {
            throw new Error(data.error || 'Failed to send test alert');
          });
        }
        return res.json();
      })
      .then(data => {
        setMessage({ type: 'success', text: 'Test alert sent successfully! Check your Slack channel.' });
        setTesting(false);
      })
      .catch(err => {
        setMessage({ type: 'error', text: err.message });
        setTesting(false);
      });
  };

  if (loading) {
    return (
      <div className="settings-loading-wrap">
        <div className="spinner" />
        <p>Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <h3>⚙️ Slack Notification Settings</h3>
        <p className="settings-desc">Configure Slack integration to receive specs violation alerts instantly.</p>
      </div>

      <form onSubmit={handleSubmit} className="settings-form">
        {message && (
          <div className={`settings-alert settings-alert--${message.type}`}>
            {message.type === 'error' ? '❌' : '✅'} {message.text}
          </div>
        )}

        <div className="form-group toggle-group">
          <label className="toggle-label-container">
            <span className="toggle-text">Enable Slack Alerts</span>
            <input 
              type="checkbox" 
              checked={isEnabled} 
              onChange={(e) => setIsEnabled(e.target.checked)} 
              className="toggle-checkbox"
            />
            <span className="toggle-slider"></span>
          </label>
          <span className="field-hint">Turn Slack alerting on or off. When enabled, alerts are sent once when a specs violation is first detected on a run.</span>
        </div>

        <div className="form-group">
          <label htmlFor="webhook_url">Slack Webhook URL</label>
          <input
            id="webhook_url"
            type="url"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            placeholder="https://hooks.slack.com/services/..."
            required={isEnabled}
            className="form-input"
          />
          <span className="field-hint">The incoming webhook URL provided by Slack for your channel or workspace.</span>
        </div>

        <div className="form-group">
          <label htmlFor="mention_target">Slack Member ID or Mention Target (Optional)</label>
          <input
            id="mention_target"
            type="text"
            value={mentionTarget}
            onChange={(e) => setMentionTarget(e.target.value)}
            placeholder="e.g. U12345678, here, channel"
            className="form-input"
          />
          <span className="field-hint">
            Specify a Slack Member ID (e.g. <code>U12345678</code>) to directly mention and notify a specific user, or enter <code>here</code> or <code>channel</code> to ping the active participants.
          </span>
        </div>

        <div className="form-actions">
          <button 
            type="button" 
            onClick={handleTestConnection} 
            disabled={saving || testing} 
            className="test-btn"
          >
            {testing ? 'Testing...' : '🧪 Test Connection'}
          </button>
          <button type="submit" disabled={saving || testing} className="save-btn">
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </form>
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
  const [activeTab, setActiveTab] = useState('lines');
  const [products, setProducts] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [alertFilter, setAlertFilter] = useState('');
  const [dismissedAlerts, setDismissedAlerts] = useState(() => {
    try {
      const saved = localStorage.getItem('vx_dismissed_alerts');
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      console.error('Failed to load dismissed alerts:', e);
      return [];
    }
  });

  const handleAlertDismiss = useCallback((alertId) => {
    setDismissedAlerts(prev => {
      const next = prev.includes(alertId) ? prev : [...prev, alertId];
      const pruned = next.slice(-100);
      try {
        localStorage.setItem('vx_dismissed_alerts', JSON.stringify(pruned));
      } catch (e) {
        console.error('Failed to save dismissed alerts:', e);
      }
      return pruned;
    });
  }, []);

  const handleAlertClick = useCallback((lineName, alertId) => {
    if (alertId) {
      handleAlertDismiss(alertId);
    }
    setAlertFilter(lineName);
    setActiveTab('alerts');
  }, [handleAlertDismiss]);

  const getRecentAlertForLine = useCallback((lineName, run, serverTime) => {
    if (!run || run.EndTime || !serverTime) return null;
    const lineAlerts = alerts.filter(a => a.SourceLine === lineName && a.RunId === run.RunId && !dismissedAlerts.includes(a.id));
    if (lineAlerts.length === 0) return null;
    
    const mostRecent = lineAlerts.reduce((latest, current) => {
      return new Date(current.AlertTime) > new Date(latest.AlertTime) ? current : latest;
    }, lineAlerts[0]);
    
    const alertTimeMs = new Date(mostRecent.AlertTime).getTime();
    const serverTimeMs = new Date(serverTime).getTime();
    
    if (serverTimeMs - alertTimeMs <= 30 * 60 * 1000) {
      return mostRecent;
    }
    return null;
  }, [alerts, dismissedAlerts]);

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
      fetch('/api/products').then(r => r.json()),
      fetch('/api/alerts').then(r => r.json()),
    ])
      .then(([s, ru, hs, pr, al]) => {
        setStatus(s);
        setRuns(ru);
        setHourStats(hs);
        setProducts(pr);
        setAlerts(al);
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
        <div className="dashboard-tabs">
          <button 
            className={`tab-btn ${activeTab === 'lines' ? 'active' : ''}`} 
            onClick={() => setActiveTab('lines')}
          >
            🖥️ Lines Monitor
          </button>
          <button 
            className={`tab-btn ${activeTab === 'products' ? 'active' : ''}`} 
            onClick={() => setActiveTab('products')}
          >
            📦 Product Specifications
          </button>
          <button 
            className={`tab-btn ${activeTab === 'alerts' ? 'active' : ''}`} 
            onClick={() => setActiveTab('alerts')}
          >
            ⚠️ Alert Log
          </button>
          <button 
            className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`} 
            onClick={() => setActiveTab('settings')}
          >
            ⚙️ Slack Settings
          </button>
        </div>

        {loading && <div className="spinner-wrap"><div className="spinner" /></div>}
        {error && (
          <div className="global-error">
            <span className="error-label" style={{ borderRadius: '4px' }}>API ERROR</span>
            <span className="error-message">{error}</span>
          </div>
        )}
        
        {!loading && (
          <>
            {activeTab === 'lines' && (
              <>
                {allLines.length === 0 ? (
                  <div className="empty-state">
                    <p>⏳ Initial sync in progress — waiting for first cycle…</p>
                  </div>
                ) : (
                  <div className="lines-list">
                    {allLines.map(line => {
                      const run = runs[line];
                      const recentAlert = getRecentAlertForLine(line, run, status.serverTime);
                      return (
                        <LineCard
                          key={line}
                          lineName={line}
                          status={status.lines[line]}
                          run={run}
                          hourStats={hourStats[line]}
                          serverTime={status.serverTime}
                          vncPort={status.vnc_port}
                          vncPassword={status.vnc_password}
                          onVncOpen={setActiveVnc}
                          recentAlert={recentAlert}
                          onAlertClick={handleAlertClick}
                          onDismissAlert={handleAlertDismiss}
                        />
                      );
                    })}
                  </div>
                )}
              </>
            )}

            {activeTab === 'products' && (
              <ProductSpecsPanel products={products} />
            )}

            {activeTab === 'alerts' && (
              <AlertLogPanel 
                alerts={alerts} 
                filterText={alertFilter} 
                setFilterText={setAlertFilter} 
              />
            )}

            {activeTab === 'settings' && (
              <SettingsPanel />
            )}
          </>
        )}
      </main>

      <VncModal 
        vncConfig={activeVnc?.vncConfig} 
        lineData={activeVnc?.lineData}
        onClose={() => setActiveVnc(null)} 
      />
    </div>
  );
}
