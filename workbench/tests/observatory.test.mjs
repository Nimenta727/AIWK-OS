import {test} from 'node:test';
import assert from 'node:assert/strict';
import {formatTokens,budgetState,stateSegments,attentionFirst,agentBars,clock,basisText,lightTone} from '../src/model/observatory.mjs';

test('unknown tokens are never shown as zero', () => {
 for (const v of [null,undefined,NaN,'x']) assert.equal(formatTokens(v),'—');
 assert.equal(formatTokens(0),'0');
 assert.equal(formatTokens(999),'999');
 assert.equal(formatTokens(1500),'1.5k');
 assert.equal(formatTokens(12000),'12k');
 assert.equal(formatTokens(1250000),'1.3M');
 assert.equal(formatTokens(2000000),'2M');
});
test('budget meter states', () => {
 assert.deepEqual(budgetState(100,null),{level:'none',ratio:null});
 assert.deepEqual(budgetState(100,0),{level:'none',ratio:null});
 assert.equal(budgetState(null,1000).level,'unknown');
 assert.equal(budgetState(100,1000).level,'ok');
 assert.equal(budgetState(700,1000).level,'warn');
 assert.equal(budgetState(1000,1000).level,'over');
 assert.equal(budgetState(5000,1000).ratio,1.5);
});
test('state segments are stable and omit empty states', () => {
 assert.deepEqual(stateSegments({}),[]);
 const s=stateSegments({failed:1,completed:3});
 assert.deepEqual(s.map(x=>x.state),['completed','failed']);
 assert.equal(s[0].pct,75);
 assert.equal(s.reduce((a,x)=>a+x.pct,0),100);
});
test('attention first collapses the rest', () => {
 const mk=(id,stages,createdAt)=>({id,stages,createdAt});
 const tasks=[mk('ok1',{completed:2},9),mk('bad',{failed:1},1),mk('wait',{pending:1},5),mk('ok2',{completed:1},8),mk('ok3',{completed:1},7),mk('ok4',{completed:1},6),mk('ok5',{completed:1},4)];
 const r=attentionFirst(tasks,3);
 assert.deepEqual(r.shown.map(t=>t.id),['bad','wait','ok1']);
 assert.equal(r.hidden,4);
 assert.deepEqual(attentionFirst(undefined),{shown:[],hidden:0});
 assert.equal(tasks[0].id,'ok1');
});
test('agent bars: unknown agents get no bar', () => {
 const bars=agentBars({claude:{in:100,out:100,unknownSessions:0},local:{in:null,out:null,unknownSessions:2},codex:{in:50,out:0,unknownSessions:0}});
 const by=Object.fromEntries(bars.map(b=>[b.agent,b]));
 assert.equal(by.claude.pct,100);
 assert.equal(by.codex.pct,25);
 assert.equal(by.local.total,null);
 assert.equal(by.local.pct,0);
});
test('clock and basis text', () => {
 assert.equal(clock(null),'--:--:--');
 assert.match(clock(1700000000),/^\d\d:\d\d:\d\d$/);
 assert.match(basisText({basis:'none'},false),/无上报/);
 assert.match(basisText({basis:'sum-of-reported',verified:false},true),/unverified/);
 assert.match(basisText({basis:'reported-total',verified:true},true),/provider-reported/);
});
test('red is never softened', () => {
 assert.equal(lightTone('red'),'red');
 assert.equal(lightTone('yellow'),'yellow');
 assert.equal(lightTone('anything-else'),'green');
});
