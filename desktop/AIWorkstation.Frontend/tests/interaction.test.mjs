import {test} from 'node:test';
import assert from 'node:assert/strict';
import {filterTaskList,shouldActivateShortcut,timeoutMessage} from '../src/model/interaction.mjs';

test('task filter preserves input and sorts by recency', () => {
 const tasks=[{id:'a',title:'Codex Windows',createdAt:'2026-01-01'},{id:'b',title:'Claude CODE',createdAt:'2026-02-01'}];
 assert.deepEqual(filterTaskList(tasks,' claude ').map(x=>x.id),['b']);
 assert.deepEqual(filterTaskList(tasks,'').map(x=>x.id),['b','a']);
 assert.equal(tasks[0].id,'a');
});
test('task search is case-insensitive and handles empty values', () => {
 assert.deepEqual(filterTaskList([{title:'AI 计划中心',id:'x'}],'计划').map(x=>x.id),['x']);
 assert.deepEqual(filterTaskList(null,'anything'),[]);
});
test('shortcuts only use deliberate key combinations', () => {
 assert.equal(shouldActivateShortcut({ctrlKey:true,metaKey:false,altKey:false,shiftKey:false,repeat:false}),true);
 assert.equal(shouldActivateShortcut({ctrlKey:false,metaKey:true,altKey:false,shiftKey:false,repeat:false}),true);
 for(const event of [
  {ctrlKey:false,metaKey:false,altKey:false,shiftKey:false,repeat:false},
  {ctrlKey:true,metaKey:false,altKey:false,shiftKey:false,repeat:true},
  {ctrlKey:true,metaKey:false,altKey:true,shiftKey:false,repeat:false},
  {ctrlKey:true,metaKey:false,altKey:false,shiftKey:true,repeat:false}
 ]) assert.equal(shouldActivateShortcut(event),false);
});
test('read and write timeouts distinguish unknown side effects', () => {
 assert.match(timeoutMessage('state',true),/未自动重试/);
 assert.match(timeoutMessage('tasks.create',false),/结果尚不确定/);
 assert.match(timeoutMessage('tasks.create',false),/切勿直接重复提交/);
});
