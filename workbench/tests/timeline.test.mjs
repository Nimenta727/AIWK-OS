import {test} from 'node:test';
import assert from 'node:assert/strict';
import {laneOf,buildLanes,tokenSeries,seriesPath,formatSpan} from '../src/model/timeline.mjs';

test('errors go to the error lane regardless of source',()=>{
 assert.equal(laneOf({source:'local',status:'error'}),'error');
 assert.equal(laneOf({source:'local',status:'ok'}),'model');
 assert.equal(laneOf({source:'claude-1',status:'ok'}),'builder');
 assert.equal(laneOf({source:'weird',status:''}),'system');   // never dropped
});
test('lanes share one axis, keep order, and flag quiet gaps',()=>{
 const rows=[{ts:100,source:'local',label:'a',status:'ok'},{ts:110,source:'tool',label:'b',status:'ok'},{ts:200,source:'local',label:'c',status:'error'}];
 const t=buildLanes(rows);
 assert.equal(t.start,100);assert.equal(t.end,200);assert.equal(t.spanSec,100);
 assert.deepEqual(t.lanes.map(l=>l.lane),['model','tool','error']);
 assert.equal(t.lanes[0].items[0].x,0);assert.equal(t.lanes[2].items[0].x,100);
 assert.deepEqual(t.gaps,[{from:110,to:200,sec:90}]);
});
test('empty and malformed input is harmless',()=>{
 assert.equal(buildLanes([]).lanes.length,0);
 assert.equal(buildLanes([null,{ts:'x'},{source:'a'}]).lanes.length,0);
 assert.equal(buildLanes([{ts:5,source:'a',label:'only'}]).spanSec,0);   // single point: no division by zero
});
test('token series: unknown is not plotted as zero, total replaces, delta adds',()=>{
 const ev=[{seq:1,ts:1,tokens:{in:10,out:5,source:'reported',scope:'delta'}},
  {seq:2,ts:2,tokens:{in:null,out:null,source:'unknown',scope:'delta'}},
  {seq:3,ts:3,tokens:{in:20,out:5,source:'reported',scope:'delta'}},
  {seq:4,ts:4,tokens:{in:100,out:50,source:'reported',scope:'total'}}];
 const s=tokenSeries(ev);
 assert.deepEqual(s.points.map(p=>p.total),[15,40,150]);assert.equal(s.unknown,1);assert.equal(s.unverified,false);
 assert.equal(tokenSeries([{seq:1,ts:1,tokens:{in:1,out:1,source:'reported',scope:'turn'}}]).unverified,true);
});
test('series path scales to the budget line when it is larger than the data',()=>{
 const s=tokenSeries([{seq:1,ts:0,tokens:{in:50,out:0,source:'reported',scope:'total'}},{seq:2,ts:10,tokens:{in:100,out:0,source:'reported',scope:'total'}}]);
 const p=seriesPath(s,200);assert.equal(p.limitY,0);assert.ok(p.line.endsWith('100.0,50.0'));
 assert.equal(seriesPath({points:[],max:0}).line,'');
});
test('span formatting',()=>{assert.equal(formatSpan(45),'45s');assert.equal(formatSpan(600),'10min');assert.equal(formatSpan(7200),'2.0h');assert.equal(formatSpan(-1),'—');});
