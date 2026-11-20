import test from 'node:test';
import assert from 'node:assert/strict';
import {graphLayers,readyStageIds} from '../src/model/workflow.mjs';
const mk=(id,dep=[],status='Pending')=>({id,title:id,dependsOn:dep,status});
test('DAG layers render parallel branches and join',()=>{
 const task={graphMode:true,steps:[mk('start'),mk('impl',['start']),mk('audit',['start']),mk('ship',['impl','audit'])]};
 assert.deepEqual(graphLayers(task).map(xs=>xs.map(x=>x.id)),[['start'],['impl','audit'],['ship']]);
 assert.deepEqual(readyStageIds(task),['start']);
 task.steps[0].status='Completed';
 assert.deepEqual(readyStageIds(task),['impl','audit']);
 task.steps[1].status='Completed';
 assert.deepEqual(readyStageIds(task),['audit']);
 task.steps[2].status='Completed';
 assert.deepEqual(readyStageIds(task),['ship']);
});
test('cyclic DAG projection rejects cycle',()=>{
 assert.throws(()=>graphLayers({graphMode:true,steps:[mk('a',['b']),mk('b',['a'])]}),/环/);
});
test('legacy workflow continues sequential scheduling',()=>{
 const task={graphMode:false,steps:[mk('a'),mk('b'),mk('c')]};
 assert.deepEqual(readyStageIds(task),['a']);
 task.steps[0].status='Completed';
 assert.deepEqual(readyStageIds(task),['b']);
});
