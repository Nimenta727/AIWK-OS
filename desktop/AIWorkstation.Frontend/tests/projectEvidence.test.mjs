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
