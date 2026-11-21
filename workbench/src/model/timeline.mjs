/** Pure helpers for the observatory timeline. No fetch, no estimation: only what the event store reported. */

export const LANE_ORDER = ['model', 'tool', 'builder', 'system', 'error'];

/** Which lane an activity row belongs to. Unknown sources land in "system" rather than being dropped. */
export function laneOf(row) {
  if (row.status === 'error' || row.status === 'failed') return 'error';
  const s = String(row.source || '');
  if (s === 'local' || s === 'router') return 'model';
  if (/^(claude|codex|builder)/.test(s)) return 'builder';
  if (s === 'tool' || s === 'task' || s === 'agent') return 'tool';
  return 'system';
}

/**
 * Lay activity rows out on a shared time axis.
 * Returns {start,end,spanSec,lanes:[{lane,items:[{x,ts,label,source,status}]}],gaps:[{from,to,sec}]}.
 * x is 0..100 (percent of the axis). `minGapSec` marks quiet periods so a stall is visible at a glance.
 */
export function buildLanes(rows, {minGapSec = 30, maxItems = 200} = {}) {
  const clean = (rows || []).filter(r => r && Number.isFinite(r.ts)).slice(-maxItems).sort((a, b) => a.ts - b.ts);
  if (!clean.length) return {start: null, end: null, spanSec: 0, lanes: [], gaps: []};
  const start = clean[0].ts, end = clean[clean.length - 1].ts;
  const span = Math.max(end - start, 1);
  /** @type {Array<{lane:string,items:Array<{x:number,ts:number,label:string,source:string,status:string}>}>} */
  const lanes = LANE_ORDER.map(lane => ({lane, items: []}));
  for (const r of clean) {
    lanes[LANE_ORDER.indexOf(laneOf(r))].items.push({
      x: Math.round(((r.ts - start) / span) * 1000) / 10, ts: r.ts, label: String(r.label || '').slice(0, 80),
      source: String(r.source || ''), status: r.status || '',
    });
  }
  /** @type {Array<{from:number,to:number,sec:number}>} */
  const gaps = [];
  for (let i = 1; i < clean.length; i++) {
    const sec = clean[i].ts - clean[i - 1].ts;
    if (sec >= minGapSec) gaps.push({from: clean[i - 1].ts, to: clean[i].ts, sec: Math.round(sec)});
  }
  return {start, end, spanSec: end - start, lanes: lanes.filter(l => l.items.length), gaps};
}

/**
 * Cumulative token use over time from one session's events. Only events with reported numbers count;
 * `total`-scope events replace the running value (they are cumulative), `delta`/`turn` add to it.
 * Unknown usage is kept out of the series and counted, never plotted as zero.
 */
export function tokenSeries(events) {
  let acc = 0, unknown = 0, unverified = false;
  const points = [];
  for (const e of (events || []).slice().sort((a, b) => a.seq - b.seq)) {
    const t = e.tokens;
    if (!t) continue;
    if (t.source === 'unknown' || (t.in === null && t.out === null)) { unknown++; continue; }
    const n = (t.in || 0) + (t.out || 0);
    if (t.scope === 'total') acc = n; else acc += n;
    if (t.scope === 'turn') unverified = true;
    points.push({ts: e.ts, total: acc});
  }
  return {points, unknown, unverified, max: points.length ? Math.max(...points.map(p => p.total)) : 0};
}

/** Polyline coordinates (0..100 x, 0..100 y with 0 at the top) for a series, plus an optional budget line. */
export function seriesPath(series, limit = /** @type {number|null} */ (null)) {
  const pts = series.points;
  if (!pts.length) return {line: '', limitY: null};
  const t0 = pts[0].ts, t1 = pts[pts.length - 1].ts, span = Math.max(t1 - t0, 1);
  const top = Math.max(series.max, limit || 0, 1);
  const line = pts.map(p => (((p.ts - t0) / span) * 100).toFixed(1) + ',' + (100 - (p.total / top) * 100).toFixed(1)).join(' ');
  return {line, limitY: limit ? Math.round((100 - (limit / top) * 100) * 10) / 10 : null};
}

/** Human duration for gaps and spans. */
export function formatSpan(sec) {
  if (!Number.isFinite(sec) || sec < 0) return '—';
  if (sec < 90) return Math.round(sec) + 's';
  if (sec < 5400) return Math.round(sec / 60) + 'min';
  return (sec / 3600).toFixed(1) + 'h';
}
