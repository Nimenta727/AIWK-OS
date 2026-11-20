import assert from 'node:assert/strict';
import test from 'node:test';
import {describeGitStatus,describeObservedChange,formatShortHead} from '../src/model/projectEvidence.mjs';

test('untracked and modified files are distinct',()=>{
 assert.equal(describeGitStatus('??').short,'U');
 assert.equal(describeGitStatus(' M').short,'M');
 assert.equal(describeGitStatus('D ').short,'D');
});
test('timeline only claims observed state changes',()=>{
 assert.match(describeObservedChange('changed'),/变化/);
 assert.match(describeObservedChange('cleared'),/未提交/);
 assert.doesNotMatch(describeObservedChange('appeared'),/AI|模型/);
});
test('short commits avoid fabricated hashes',()=>{
 assert.equal(formatShortHead('0123456789abcdef'),'01234567');
 assert.equal(formatShortHead(''),'无提交记录');
});

import {visibleProjectFiles} from '../src/model/projectEvidence.mjs';

test('changed-only project tree retains containing directories',()=>{
 const rows=[{path:'src',isDirectory:true},{path:'src/core',isDirectory:true},{path:'src/core/agent.ts',isDirectory:false,status:' M'},{path:'src/core/clean.ts',isDirectory:false,status:''},{path:'docs',isDirectory:true},{path:'docs/README.md',isDirectory:false,status:''}];
 assert.deepEqual(visibleProjectFiles(rows,'changed',new Set()).map(x=>x.path),['src','src/core','src/core/agent.ts']);
 assert.deepEqual(visibleProjectFiles(rows,'changed',new Set(['src'])).map(x=>x.path),['src']);
 assert.deepEqual(visibleProjectFiles(rows,'all',new Set(['src/core'])).map(x=>x.path),['src','src/core','docs','docs/README.md']);
});
