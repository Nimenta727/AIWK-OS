import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizePath,parseCommand,buildStage,buildTree,describeOp,parentOf} from '../src/model/fileOps.mjs';

test('paths: relative only, no escape or protected names', () => {
 assert.equal(normalizePath('./a//b.txt'),'a/b.txt');
 for (const bad of ['','/etc/passwd','../x','a/../b','a\\b','.git/config','x/.ssh/id','.aiws-trash/x'])
  assert.throws(()=>normalizePath(bad),/invalid-path/,bad);
});
test('commands: english and chinese forms', () => {
 assert.deepEqual(parseCommand('mv a.txt docs/b.txt').op,{kind:'move',path:'a.txt',to:'docs/b.txt'});
 assert.deepEqual(parseCommand('复制 a.txt 到 b.txt').op,{kind:'copy',path:'a.txt',to:'b.txt'});
 assert.deepEqual(parseCommand('重命名 old.md 为 new.md').op,{kind:'move',path:'old.md',to:'new.md'});
 assert.deepEqual(parseCommand('删除 "my notes/a b.txt"').op,{kind:'trash',path:'my notes/a b.txt'});
 assert.deepEqual(parseCommand('新建文件夹 论文').op,{kind:'mkdir',path:'论文'});
 assert.equal(parseCommand('restore '+'a'.repeat(32)).op.kind,'restore');
});
test('commands: rejects unknown, wrong arity, escapes, bad ids', () => {
 assert.equal(parseCommand('').reason,'empty');
 assert.equal(parseCommand('format c:').reason,'unknown-command');
 assert.equal(parseCommand('mv a').reason,'arity');
 assert.equal(parseCommand('rm ../x').reason,'invalid-path');
 assert.equal(parseCommand('mv a /etc/x').reason,'invalid-path');
 assert.equal(parseCommand('restore ../x').reason,'bad-trash-id');
});
test('stage building never invents fingerprints; no permanent delete tool exists', () => {
 const sha='b'.repeat(64);
 const s=buildStage({kind:'move',path:'a',to:'b'},{sha256:sha});
 assert.deepEqual(s.arguments,{path:'a',to:'b',expectedSha256:sha});
 assert.equal(s.tool,'file.move');
 assert.throws(()=>buildStage({kind:'trash',path:'a'},null),/fingerprint-required/);
 assert.throws(()=>buildStage({kind:'trash',path:'a'},{sha256:'zz'}),/fingerprint-required/);
 assert.equal(buildStage({kind:'mkdir',path:'d'}).arguments.expectedSha256,undefined);
 assert.equal(buildStage({kind:'trash',path:'a'},{sha256:sha}).tool,'file.trash');
 assert.throws(()=>buildStage({kind:'delete',path:'a'}),/unknown-operation/);
});
test('describe and tree', () => {
 assert.match(describeOp({kind:'trash',path:'a'},false),/可恢复/);
 assert.match(describeOp({kind:'trash',path:'a'},true),/reversible/);
 const tree=buildTree(['z.txt','d/b.txt','d/a.txt'],['d','empty']);
 assert.deepEqual(tree.map(n=>n.name),['d','empty','z.txt']);
 assert.deepEqual(tree[0].children.map(n=>n.name),['a.txt','b.txt']);
 assert.equal(parentOf('a/b/c'),'a/b'); assert.equal(parentOf('c'),'');
});
