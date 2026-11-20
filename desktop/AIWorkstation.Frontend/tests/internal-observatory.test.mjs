import test from 'node:test';
import assert from 'node:assert/strict';
import {stageTotals,measuredUsage,phaseProjection,directoryChanges} from '../src/model/internal-observatory.mjs';
test('unknown provider usage is not measured zero',()=>{
 const task={steps:[{agent:'Codex',status:'Running',usage:{input:null,output:null}},{agent:'Manual',status:'Completed'}]};
 const x=stageTotals(task);assert.equal(x.unknown,1);assert.equal(x.verified,0);assert.equal(x.done,1);
});
test('imported genuine zero tokens stay measured',()=>{
 const x=measuredUsage({usage:{input:0,output:0,source:'Codex JSONL'}});
 assert.equal(x.valid,true);assert.equal(x.input,0);
});
test('partial usage cannot be called measured',()=>{
 assert.equal(measuredUsage({usage:{input:17,output:null}}).valid,false);
 assert.equal(measuredUsage({usage:{input:-3,output:8}}).valid,false);
});
test('five phases keep missing evidence unknown',()=>{
 const xs=phaseProjection({nodes:[{phase:'Context',state:'Recorded'}]});
 assert.equal(xs.length,5);assert.equal(xs[0].state,'Unknown');assert.equal(xs[1].state,'Recorded');
});
test('Git changes grouped by directory, never infer rename',()=>{
 const x=directoryChanges({entries:[{path:'src/core/a.ts',change:'modified'},{path:'src/core/b.ts',change:'added'},{path:'docs/a.md',change:'removed'},{path:'src/core',isDirectory:true,change:'touched'}]});
 assert.equal(x[0].dir,'src/core');assert.equal(x[0].files.length,2);assert.equal(x[1].dir,'docs');
});
test('invalid paths excluded from presentation',()=>{
 assert.deepEqual(directoryChanges({entries:[{path:'../secret',change:'added'},{path:'src\\secret',change:'added'}]}),[]);
});