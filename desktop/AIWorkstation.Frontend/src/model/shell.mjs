/** Pure logic of the editor-style shell (tabs, command palette, shortcuts, preferences). No DOM, no fetch. */

export const MAX_TABS = 12;

/** Open (or focus) a tab. Tabs are unique by id. When full, the oldest non-pinned inactive tab is dropped. */
export function openTab(tabs, tab, active) {
  if (!tab || typeof tab.id !== 'string' || !tab.id) return {tabs, active};
  if (tabs.some(t => t.id === tab.id)) return {tabs, active: tab.id};
  let next = [...tabs, {pinned: false, ...tab}];
  while (next.length > MAX_TABS) {
    const victim = next.findIndex(t => !t.pinned && t.id !== tab.id && t.id !== active);
    if (victim < 0) break;
    next = next.filter((_, i) => i !== victim);
  }
  return {tabs: next, active: tab.id};
}

/** Close a tab. Pinned tabs never close. Returns the neighbour as the new active tab when the active one closes. */
export function closeTab(tabs, active, id) {
  const index = tabs.findIndex(t => t.id === id);
  if (index < 0 || tabs[index].pinned) return {tabs, active};
  const next = tabs.filter(t => t.id !== id);
  if (active !== id) return {tabs: next, active};
  const neighbour = next[Math.min(index, next.length - 1)] || next[0];
  return {tabs: next, active: neighbour ? neighbour.id : null};
}

export function cycleTab(tabs, active, step) {
  if (!tabs.length) return active;
  const i = Math.max(0, tabs.findIndex(t => t.id === active));
  return tabs[(i + step + tabs.length) % tabs.length].id;
}

export function fileTabId(path) { return 'file:' + path; }
export function fileTitle(path) { return String(path).split('/').pop() || String(path); }

/** Command palette search: every query word must occur (case-insensitive), earlier/prefix matches rank first. */
export function filterCommands(commands, query) {
  const words = String(query || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [...commands];
  const scored = [];
  for (const c of commands) {
    const hay = (c.label + ' ' + (c.keywords || '')).toLowerCase();
    if (!words.every(w => hay.includes(w))) continue;
    const label = c.label.toLowerCase();
    const score = words.reduce((s, w) => s + (label.startsWith(w) ? 0 : label.includes(w) ? 1 : 2), 0);
    scored.push({c, score});
  }
  return scored.sort((a, b) => a.score - b.score || a.c.label.localeCompare(b.c.label)).map(x => x.c);
}

/** Match a keyboard event against 'ctrl+shift+p' style specs ('mod' = ctrl or meta). Never matches plain typing. */
export function matchKey(event, spec) {
  const parts = spec.toLowerCase().split('+');
  const key = parts.pop();
  const want = {mod: parts.includes('mod'), ctrl: parts.includes('ctrl'), shift: parts.includes('shift'), alt: parts.includes('alt')};
  const mod = want.mod ? (event.ctrlKey || event.metaKey) : (want.ctrl ? event.ctrlKey : !(event.ctrlKey || event.metaKey));
  if (!mod || Boolean(event.shiftKey) !== want.shift || Boolean(event.altKey) !== want.alt) return false;
  return String(event.key || '').toLowerCase() === key;
}

/** Keys typed inside text fields must not trigger shortcuts that lack a modifier. */
export function isEditableTarget(target) {
  const tag = target && target.tagName ? String(target.tagName).toLowerCase() : '';
  return tag === 'input' || tag === 'textarea' || tag === 'select' || Boolean(target && target.isContentEditable);
}

export const DEFAULT_PREFS = {theme: 'dark', sidebar: true, panel: false, activity: 'observatory'};

export function sanitizePrefs(value) {
  const out = {...DEFAULT_PREFS};
  if (value && typeof value === 'object') {
    if (value.theme === 'dark' || value.theme === 'light') out.theme = value.theme;
    if (typeof value.sidebar === 'boolean') out.sidebar = value.sidebar;
    if (typeof value.panel === 'boolean') out.panel = value.panel;
    if (['observatory', 'explorer', 'tools', 'tasks', 'ai', 'system'].includes(value.activity)) out.activity = value.activity;
  }
  return out;
}

/** localStorage may be missing or throw (private windows): every access is guarded and falls back to defaults. */
export function loadPrefs(storage, key = 'aiws.shell.prefs') {
  try { return sanitizePrefs(JSON.parse(storage.getItem(key) || 'null')); } catch { return {...DEFAULT_PREFS}; }
}
export function savePrefs(storage, prefs, key = 'aiws.shell.prefs') {
  try { storage.setItem(key, JSON.stringify(sanitizePrefs(prefs))); return true; } catch { return false; }
}

/** Build the explorer tree rows (flattened, only expanded folders' children), folders first. */
export function flattenTree(nodes, expanded, depth = 0) {
  const rows = [];
  for (const n of nodes) {
    rows.push({...n, depth});
    if (n.type === 'dir' && expanded.has(n.path)) rows.push(...flattenTree(n.children || [], expanded, depth + 1));
  }
  return rows;
}
