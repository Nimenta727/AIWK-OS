import test from 'node:test';
import assert from 'node:assert/strict';
import {viewerKind, rawUrl, parseMarkdown, parseInline, safeHref, parseTable, resolveBrowserTarget} from '../src/model/apps.mjs';

test('viewerKind routes by extension, case-insensitively, with a text fallback', () => {
  const k = p => viewerKind(p);
  assert.deepEqual(['a.PNG', 'x/y.pdf', 'p.html', 'README.md', 'd.csv', 'c.json', 'r.docx', 'main.py', 'Makefile'].map(k),
    ['image', 'pdf', 'html', 'markdown', 'table', 'json', 'document', 'text', 'text']);
});

test('rawUrl encodes the path', () => assert.equal(rawUrl('a b/ü.png'), '/api/v1/workspace/raw?path=a%20b%2F%C3%BC.png'));

test('markdown blocks: headings, lists, code fences, quotes, paragraphs', () => {
  const b = parseMarkdown('# T\n\npara one\nstill\n\n- a\n- b\n\n1. x\n\n```js\nlet a=1;\n```\n> q\n---');
  assert.deepEqual(b.map(x => x.type), ['h', 'p', 'list', 'list', 'code', 'quote', 'hr']);
  assert.equal(b[0].level, 1);
  assert.equal(b[1].spans[0].v, 'para one still');
  assert.deepEqual([b[2].ordered, b[3].ordered], [false, true]);
  assert.equal(b[4].text, 'let a=1;');
});

test('markdown never produces HTML: markup stays literal text', () => {
  const b = parseMarkdown('<img src=x onerror=alert(1)> and <script>x()</script>');
  assert.equal(b.length, 1);
  assert.ok(b[0].spans.every(s => s.t === 'text'));
  assert.ok(b[0].spans[0].v.includes('<img'));
});

test('inline marks and link safety', () => {
  const s = parseInline('a `c` **b** *i* [t](https://x.io) [bad](javascript:alert(1))');
  assert.deepEqual(s.filter(x => x.t !== 'text').map(x => x.t), ['code', 'strong', 'em', 'link', 'link']);
  assert.equal(safeHref('https://x.io/a?b=1'), 'https://x.io/a?b=1');
  for (const bad of ['javascript:alert(1)', 'data:text/html,x', 'file:///etc/passwd', '//evil.com', 'http://a b'])
    assert.equal(safeHref(bad), null, bad);
});

test('unterminated code fence does not hang or drop text', () => {
  const b = parseMarkdown('```\nopen');
  assert.equal(b[0].type, 'code'); assert.equal(b[0].text, 'open');
});

test('table: quotes, escaped quotes, newlines in cells, TSV, caps', () => {
  const t = parseTable('name,note\n"a,b","say ""hi"""\n"multi\nline",2\n');
  assert.deepEqual(t.header, ['name', 'note']);
  assert.deepEqual(t.rows, [['a,b', 'say "hi"'], ['multi\nline', '2']]);
  assert.deepEqual(parseTable('a\tb\n1\t2').rows, [['1', '2']]);
  const big = parseTable('h\n' + Array.from({length: 2000}, (_, i) => i).join('\n'), {maxRows: 10});
  assert.equal(big.rows.length, 10); assert.equal(big.truncated, true);
  assert.equal(parseTable('a,b,c\n1,2,3', {maxCols: 2}).columnsTruncated, true);
  assert.deepEqual(parseTable('').rows, []);
});

test('browser address: loopback dev servers embed, workspace html embeds, other sites never embed', () => {
  assert.deepEqual(resolveBrowserTarget('localhost:5173'), {kind: 'local', url: 'http://localhost:5173/'});
  assert.equal(resolveBrowserTarget('http://127.0.0.1:8000/app').kind, 'local');
  assert.equal(resolveBrowserTarget('docs/index.html').kind, 'workspace');
  assert.equal(resolveBrowserTarget('example.com').kind, 'external');
  assert.equal(resolveBrowserTarget('https://example.com/x').url, 'https://example.com/x');
});

test('browser address: dangerous or ambiguous targets are invalid', () => {
  for (const bad of ['', '   ', 'javascript:alert(1)', 'file:///etc/passwd', 'ftp://x.org', 'http://u:p@host.com/', '../secret.html',
    '/abs/x.html', 'http://localhost/', 'https://localhost:3000/', 'http://localhost:80/', 'http://127.0.0.1:22/', 'a'.repeat(3000)])
    assert.equal(resolveBrowserTarget(bad).kind, 'invalid', bad);
});
