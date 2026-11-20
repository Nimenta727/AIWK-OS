import {test} from 'node:test';import {strict as assert} from 'node:assert';
import {missionTotals,dispatchLabel,nextAction} from '../src/model/mission.mjs';
test('mission progress is derived only from persisted stages',()=>{
 const task={steps:[{status:'Completed',agent:'Codex',usage:{input:40,output:20}},{status:'Running',agent:'ClaudeCode',usage:{}},{status:'Failed',agent:'Manual'}],unified:{plans:[{id:'p'}]}};
 assert.deepEqual(missionTotals(task),{total:3,done:1,running:1,attention:1,plans:1,unknownUsage:1});
});
test('scheduler next picks an already queued stage before an unapproved stage',()=>{
 assert.equal(nextAction({stages:[{stageId:'a',status:'approval'},{stageId:'b',status:'queued'}]}).stageId,'b');
 assert.equal(nextAction({stages:[{status:'completed'}]}),null);
 assert.equal(dispatchLabel('unavailable'),'执行器不可用');
});
test('no phantom completion or usage evidence for an empty task',()=>{
 assert.equal(missionTotals(null).done,0);assert.equal(missionTotals({steps:[{status:'Pending',agent:'Codex'}]}).unknownUsage,1);
});
