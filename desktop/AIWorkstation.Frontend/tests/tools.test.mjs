import test from 'node:test';
import assert from 'node:assert/strict';
import {READ_ONLY_VIEWS,resolveReadOnlyView,normalizeOutput} from '../src/model/toolCommands.mjs';
test('read-only Git selectors are unique and contain no unsafe operations',()=>{
 const ids=READ_ONLY_VIEWS.map(x=>x.id);
 assert.equal(new Set(ids).size,ids.length);
 for(const v of READ_ONLY_VIEWS){assert.ok(v.command.startsWith('git '));assert.ok(resolveReadOnlyView(v.id));}
 for(const bad of ['push','fetch','!shell','../../etc','status; del C:\\',''])assert.equal(resolveReadOnlyView(bad),null);
});
test('terminal output view has a strict maximum length',()=>{
 assert.equal(normalizeOutput('abc'), 'abc');
 assert.equal(normalizeOutput('a'.repeat(130000)).length,120000);
});
