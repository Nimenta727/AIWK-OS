/** UI-only helpers for the observatory. Pure functions: no fetch, no model, no estimation. */

/** Unknown stays unknown: null/undefined is shown as an em dash, never as 0. */
export function formatTokens(n) {
  if (n === null || n === undefined || typeof n !== 'number' || Number.isNaN(n)) return '—';
  if (n < 1000) return String(n);
  if (n < 1e6) return (n / 1000).toFixed(n < 10000 ? 1 : 0).replace(/\.0$/, '') + 'k';
  return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
}

export function budgetState(used, limit) {
  if (!limit || limit <= 0) return {level: 'none', ratio: null};
  if (used === null || used === undefined) return {level: 'unknown', ratio: null};
  const ratio = used / limit;
  return {level: ratio >= 1 ? 'over' : ratio >= 0.7 ? 'warn' : 'ok', ratio: Math.min(ratio, 1.5)};
}

const ORDER = ['completed', 'running', 'queued', 'pending', 'interrupted', 'failed'];
/** Stacked-bar segments from stage state counts, in a stable order; zero-count states are omitted. */
export function stateSegments(stages) {
  const total = ORDER.reduce((sum, k) => sum + (stages?.[k] || 0), 0);
  if (!total) return [];
  return ORDER.filter(k => stages[k]).map(k => ({state: k, count: stages[k], pct: Math.round(stages[k] * 1000 / total) / 10}));
}

/** Tasks that need attention (failed / interrupted / waiting) come first; the rest stay collapsed. */
export function attentionFirst(recent, max = 5) {
  const score = t => (t.stages?.failed ? 3 : 0) + (t.stages?.interrupted ? 2 : 0) + (t.stages?.pending ? 1 : 0);
  const sorted = [...(recent || [])].sort((a, b) => score(b) - score(a) || (b.createdAt || 0) - (a.createdAt || 0));
  return {shown: sorted.slice(0, max), hidden: Math.max(0, sorted.length - max)};
}

/** Per-agent token bars. Agents without reported numbers get no bar (pct 0) and total null. */
export function agentBars(byAgent) {
  const rows = Object.entries(byAgent || {}).map(([agent, t]) => {
    const known = t.in !== null || t.out !== null;
    return {agent, total: known ? (t.in || 0) + (t.out || 0) : null, unknownSessions: t.unknownSessions || 0};
  });
  const max = Math.max(0, ...rows.map(r => r.total || 0));
  return rows.map(r => ({...r, pct: max && r.total ? Math.max(2, Math.round(r.total * 100 / max)) : 0}));
}

export function clock(ts) {
  if (typeof ts !== 'number' || !isFinite(ts)) return '--:--:--';
  const d = new Date(ts * 1000);
  const p = n => String(n).padStart(2, '0');
  return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}

export function basisText(tokens, english) {
  const t = (zh, en) => english ? en : zh;
  if (!tokens || tokens.basis === 'none') return t('无上报数据', 'nothing reported');
  const base = tokens.basis === 'reported-total' ? t('提供方上报的总量', 'provider-reported total') : t('逐条上报之和', 'sum of reported figures');
  return tokens.verified === false ? base + t('（语义未验证）', ' (semantics unverified)') : base;
}

/** Light colours: red is never hidden behind a friendlier state. */
export function lightTone(level) {
  return level === 'red' ? 'red' : level === 'yellow' ? 'yellow' : 'green';
}
