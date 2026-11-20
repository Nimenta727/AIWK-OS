import test from 'node:test';
import assert from 'node:assert/strict';
import {flowNodes, sumMeasuredUsage, findDuplicates, agentName} from '../src/model/workflow.mjs';
const t = {steps:[
  {id:'a',title:'设计',agent:'ClaudeCode',status:'Completed',usage:{input:200,output:100},lastPromptFingerprint:'X'},
  {id:'b',title:'实现',agent:'Codex',status:'Pending',usage:{input:null,output:null},lastPromptFingerprint:'X'}
]};
test('graph includes entry/router/stages/output in correct order',()=>assert.deepEqual(flowNodes(t).map(x=>x.id),['entry','router','a','b','output']));
test('unknown usage is not silently counted as zero measured',()=>assert.deepEqual(sumMeasuredUsage(t),{stages:1,input:200,output:100,missing:1}));
test('duplicate context fingerprint is detected',()=>assert.deepEqual(findDuplicates(t),['b']));
test('no selected task yields no graph',()=>assert.deepEqual(flowNodes(null),[]));
test('agent identity is explicit',()=>assert.equal(agentName('ClaudeCode'),'Claude Code'));
