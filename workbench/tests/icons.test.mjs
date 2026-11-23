// Every icon name written in the UI must exist in the codicon font, or the icon renders as an empty box.
// (`power` did not exist; the Power-off button had a blank icon.) Names come from icon="x", icon:'x' and <Icon name="x".
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync, statSync, existsSync} from 'node:fs';
import {join} from 'node:path';

const root = new URL('..', import.meta.url).pathname;
const css = join(root, 'node_modules/@vscode/codicons/dist/codicon.css');
const files = dir => readdirSync(dir).flatMap(n => {const p = join(dir, n); return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(n) ? [p] : [];});

test('every literal icon name exists in the codicon font', {skip: !existsSync(css) && 'codicons not installed'}, () => {
  const known = new Set([...readFileSync(css, 'utf8').matchAll(/\.codicon-([a-z0-9-]+):before/g)].map(m => m[1]));
  const used = new Set();
  for (const f of files(join(root, 'src'))) {
    const src = readFileSync(f, 'utf8');
    for (const re of [/\bicon="([a-z0-9-]+)"/g, /\bicon:'([a-z0-9-]+)'/g, /<Icon name="([a-z0-9-]+)"/g]) for (const m of src.matchAll(re)) used.add(m[1]);
  }
  assert.ok(used.size > 30, 'the scan must find the icons');
  assert.deepEqual([...used].filter(n => !known.has(n)).sort(), []);
});
