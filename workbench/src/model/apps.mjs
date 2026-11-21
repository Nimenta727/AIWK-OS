/** Pure logic for the integrated viewers and the preview browser. No DOM, no fetch. */

const IMAGE = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg']);
const EXT = p => { const n = String(p).split('/').pop() || ''; const i = n.lastIndexOf('.'); return i < 0 ? '' : n.slice(i + 1).toLowerCase(); };

/** Which viewer shows this workspace path. Unknown extensions fall back to the plain-text viewer. */
export function viewerKind(path) {
  const e = EXT(path);
  if (IMAGE.has(e)) return 'image';
  if (e === 'pdf') return 'pdf';
  if (e === 'html' || e === 'htm') return 'html';
  if (e === 'md' || e === 'markdown') return 'markdown';
  if (e === 'csv' || e === 'tsv') return 'table';
  if (e === 'json') return 'json';
  if (['docx', 'odt', 'epub', 'rtf'].includes(e)) return 'document';
  return 'text';
}

export function rawUrl(path) { return '/api/v1/workspace/raw?path=' + encodeURIComponent(path); }

/** Minimal Markdown: headings, fenced code, bullet/numbered lists, quotes, rules, paragraphs. Inline marks are returned as
 *  plain spans (text|code|strong|em|link). Nothing is ever turned into HTML, so a document cannot inject markup. */
export function parseInline(text) {
  const spans = [];
  const re = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(\[[^\]\n]+\]\([^)\s]+\))/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) spans.push({t: 'text', v: text.slice(last, m.index)});
    const s = m[0];
    if (m[1]) spans.push({t: 'code', v: s.slice(1, -1)});
    else if (m[2]) spans.push({t: 'strong', v: s.slice(2, -2)});
    else if (m[3]) spans.push({t: 'em', v: s.slice(1, -1)});
    else { const k = s.indexOf(']('); spans.push({t: 'link', v: s.slice(1, k), href: s.slice(k + 2, -1)}); }
    last = m.index + s.length;
  }
  if (last < text.length) spans.push({t: 'text', v: text.slice(last)});
  return spans;
}

export function parseMarkdown(source) {
  const lines = String(source).replace(/\r\n?/g, '\n').split('\n');
  const blocks = [];
  let para = [], list = null, quote = [];
  const flush = () => {
    if (para.length) blocks.push({type: 'p', spans: parseInline(para.join(' '))});
    if (list) blocks.push(list);
    if (quote.length) blocks.push({type: 'quote', spans: parseInline(quote.join(' '))});
    para = []; list = null; quote = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = /^```(\w*)\s*$/.exec(line);
    if (fence) {
      flush();
      const body = [];
      for (i++; i < lines.length && !/^```\s*$/.test(lines[i]); i++) body.push(lines[i]);
      blocks.push({type: 'code', lang: fence[1], text: body.join('\n')});
      continue;
    }
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    const ul = /^\s*[-*+]\s+(.*)$/.exec(line);
    const ol = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const q = /^>\s?(.*)$/.exec(line);
    if (h) { flush(); blocks.push({type: 'h', level: h[1].length, spans: parseInline(h[2])}); }
    else if (/^\s*([-*_])\1\1+\s*$/.test(line)) { flush(); blocks.push({type: 'hr'}); }
    else if (ul || ol) {
      const ordered = Boolean(ol);
      if (!list || list.ordered !== ordered) { flush(); list = {type: 'list', ordered, items: []}; }
      list.items.push(parseInline((ul || ol)[1]));
    } else if (q) { if (!quote.length) flush(); quote.push(q[1]); }
    else if (!line.trim()) flush();
    else { if (list || quote.length) flush(); para.push(line.trim()); }
  }
  flush();
  return blocks;
}

/** Only http(s) links are ever made clickable; everything else (javascript:, data:, file:) stays inert text. */
export function safeHref(href) { return /^https?:\/\/[^\s]+$/i.test(href) ? href : null; }

/** CSV/TSV with quotes. Capped so a huge file cannot freeze the page. */
export function parseTable(text, {maxRows = 500, maxCols = 50} = {}) {
  const delim = /\t/.test(String(text).split('\n', 1)[0]) && !/,/.test(String(text).split('\n', 1)[0]) ? '\t' : ',';
  const rows = [];
  let row = [], cell = '', quoted = false, truncated = false;
  const src = String(text);
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (quoted) {
      if (c === '"') { if (src[i + 1] === '"') { cell += '"'; i++; } else quoted = false; }
      else cell += c;
    } else if (c === '"' && cell === '') quoted = true;
    else if (c === delim) { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && src[i + 1] === '\n') i++;
      row.push(cell); cell = ''; rows.push(row); row = [];
      if (rows.length >= maxRows + 1) { truncated = true; break; }
    } else cell += c;
  }
  if (!truncated && (cell !== '' || row.length)) { row.push(cell); rows.push(row); }
  const clip = r => r.slice(0, maxCols);
  return {header: clip(rows[0] || []), rows: rows.slice(1).map(clip), truncated, columnsTruncated: rows.some(r => r.length > maxCols)};
}

/** Address bar of the preview browser. Allowed: loopback dev servers (embedded), workspace HTML (embedded, sandboxed),
 *  and other http(s) sites (NOT embedded: they are handed to the system browser, so no site ever runs inside the workbench). */
export function resolveBrowserTarget(input) {
  const text = String(input || '').trim();
  if (!text || text.length > 2048) return {kind: 'invalid'};
  if (/^[\w./-]+\.html?$/i.test(text) && !text.startsWith('/') && !text.includes('..')) return {kind: 'workspace', path: text, url: rawUrl(text)};
  if (/^[./\\]/.test(text)) return {kind: 'invalid'};
  let candidate = text;
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(candidate)) candidate = (/^(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/.test(candidate) ? 'http://' : 'https://') + candidate;
  let u;
  try { u = new URL(candidate); } catch { return {kind: 'invalid'}; }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return {kind: 'invalid'};
  if (u.username || u.password) return {kind: 'invalid'};
  const loopback = u.hostname === 'localhost' || u.hostname === '127.0.0.1';
  if (loopback && u.protocol === 'http:' && u.port && Number(u.port) >= 1024) return {kind: 'local', url: u.href};
  if (loopback) return {kind: 'invalid'};
  if (!/^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]*[a-z0-9])?$/i.test(u.hostname)) return {kind: 'invalid'};   // real host names only
  return {kind: 'external', url: u.href};
}
