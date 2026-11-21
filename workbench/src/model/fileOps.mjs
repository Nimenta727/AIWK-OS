/** UI-only helpers for guest file operations. Pure functions: no fetch, no file access.
 *  The Python toolplane/Broker remain authoritative; this only prepares reviewable requests. */

export function normalizePath(value) {
  const raw = String(value ?? '').trim().replace(/^\.\//, '');
  if (!raw || raw.length > 512 || raw.includes('\\') || raw.startsWith('/') || raw.includes('\0'))
    throw new Error('invalid-path');
  const parts = raw.split('/').filter(Boolean);
  if (!parts.length || parts.some(p => p === '..' || p === '.' || p === '.git' || p === '.ssh' || p === '.aiws-trash'))
    throw new Error('invalid-path');
  return parts.join('/');
}

export function tokenize(input) {
  const out = [];
  const re = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let m;
  while ((m = re.exec(String(input ?? ''))) !== null) out.push(m[1] ?? m[2] ?? m[3]);
  return out;
}

const WORDS = {
  mkdir: ['mkdir', '新建文件夹', '创建文件夹', '新建目录'],
  copy: ['cp', 'copy', '复制'],
  move: ['mv', 'move', '移动', '重命名', 'rename'],
  trash: ['rm', 'trash', 'delete', '删除', '移到回收站'],
  restore: ['restore', 'undo', '恢复', '撤销']
};

/** Deterministic command grammar (works with no model): `mv a b`, `复制 a 到 b`, `rm a` ... */
export function parseCommand(input) {
  const tokens = tokenize(input).filter(t => !['到', '为', 'to', 'as'].includes(t.toLowerCase()));
  if (!tokens.length) return {ok: false, reason: 'empty'};
  const head = tokens[0].toLowerCase();
  const kind = Object.keys(WORDS).find(k => WORDS[k].includes(head) || WORDS[k].includes(tokens[0]));
  if (!kind) return {ok: false, reason: 'unknown-command'};
  const args = tokens.slice(1);
  try {
    if (kind === 'mkdir' || kind === 'trash') {
      if (args.length !== 1) return {ok: false, reason: 'arity'};
      return {ok: true, op: {kind, path: normalizePath(args[0])}};
    }
    if (kind === 'restore') {
      if (args.length !== 1 || !/^[a-f0-9]{32}$/.test(args[0])) return {ok: false, reason: 'bad-trash-id'};
      return {ok: true, op: {kind, trashId: args[0]}};
    }
    if (args.length !== 2) return {ok: false, reason: 'arity'};
    return {ok: true, op: {kind, path: normalizePath(args[0]), to: normalizePath(args[1])}};
  } catch {
    return {ok: false, reason: 'invalid-path'};
  }
}

export const TOOL_FOR = {mkdir: 'file.mkdir', copy: 'file.copy', move: 'file.move', trash: 'file.trash', restore: 'file.restore'};
export const NEEDS_FINGERPRINT = new Set(['copy', 'move', 'trash']);

/** Build one DAG stage. Never fabricates a fingerprint: callers must pass a stat result. */
export function buildStage(op, stat) {
  const tool = TOOL_FOR[op.kind];
  if (!tool) throw new Error('unknown-operation');
  const args = {};
  if (op.kind === 'restore') args.trashId = op.trashId;
  else {
    args.path = op.path;
    if (op.to) args.to = op.to;
    if (NEEDS_FINGERPRINT.has(op.kind)) {
      if (!stat || !/^[a-f0-9]{64}$/.test(stat.sha256 || '')) throw new Error('fingerprint-required');
      args.expectedSha256 = stat.sha256;
    }
  }
  return {key: 'op', label: describeOp(op, false).slice(0, 160), tool, arguments: args, dependsOn: []};
}

export function describeOp(op, english) {
  const t = (zh, en) => english ? en : zh;
  switch (op.kind) {
    case 'mkdir': return t(`新建文件夹 ${op.path}`, `Create folder ${op.path}`);
    case 'copy': return t(`复制 ${op.path} → ${op.to}`, `Copy ${op.path} → ${op.to}`);
    case 'move': return t(`移动/重命名 ${op.path} → ${op.to}`, `Move/rename ${op.path} → ${op.to}`);
    case 'trash': return t(`移到回收站 ${op.path}（可恢复）`, `Move ${op.path} to trash (reversible)`);
    case 'restore': return t(`从回收站恢复 ${op.trashId.slice(0, 8)}…`, `Restore trash item ${op.trashId.slice(0, 8)}…`);
    default: return 'unknown';
  }
}

/** Nested folder tree from flat `files` and `dirs` lists. Folders first, then names. */
export function buildTree(files, dirs) {
  const root = {name: '', path: '', type: 'dir', children: []};
  const index = new Map([['', root]]);
  const ensureDir = path => {
    if (index.has(path)) return index.get(path);
    const slash = path.lastIndexOf('/');
    const parent = ensureDir(slash < 0 ? '' : path.slice(0, slash));
    const node = {name: path.slice(slash + 1), path, type: 'dir', children: []};
    parent.children.push(node);
    index.set(path, node);
    return node;
  };
  for (const d of dirs || []) ensureDir(d);
  for (const f of files || []) {
    const slash = f.lastIndexOf('/');
    ensureDir(slash < 0 ? '' : f.slice(0, slash)).children.push({name: f.slice(slash + 1), path: f, type: 'file', children: []});
  }
  const sort = n => {
    n.children.sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === 'dir' ? -1 : 1));
    n.children.forEach(sort);
  };
  sort(root);
  return root.children;
}

export function parentOf(path) {
  const slash = String(path).lastIndexOf('/');
  return slash < 0 ? '' : path.slice(0, slash);
}
