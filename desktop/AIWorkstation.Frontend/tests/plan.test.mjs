import test from 'node:test';
import assert from 'node:assert/strict';
import {parsePlanMarkdown,summarizeWorkflowPlan,isNewerVersion} from '../src/model/plan.mjs';

test('Plan outline preserves heading hierarchy and checkbox evidence',()=>{
 const p=parsePlanMarkdown('# 总计划\n一些说明\n## 第一阶段\n- [x] 安装依赖\n- [ ] 添加核心\n  - [X] 编译\n## 第二阶段\n1. 检查兼容性');
 assert.equal(p.sections.length,3);assert.equal(p.tracked,3);assert.equal(p.done,2);
 assert.equal(p.untracked,1);assert.equal(p.progress,67);assert.equal(p.sections[1].level,2);
 assert.equal(p.sections[2].items[0].tracked,false);
});
test('Plan parser does not mistake examples inside code fences for real work',()=>{
 const p=parsePlanMarkdown('```md\n- [x] fake\n```\n# Plan\n- [ ] real\n~~~\n- [x] fake2\n~~~');
 assert.equal(p.tracked,1);assert.equal(p.done,0);assert.equal(p.sections.length,1);
});
test('No checkboxes means progress unknown, not zero',()=>{
 const p=parsePlanMarkdown('# Architecture\n1. Design a new core\n2. Test it');
 assert.equal(p.progress,null);assert.equal(p.untracked,2);
});
test('Empty markdown and nested headings remain valid',()=>{
 assert.equal(parsePlanMarkdown('').sections.length,0);
 assert.equal(parsePlanMarkdown('## Stage\n### Detail\n- [x] ok').sections.at(-1).level,3);
});
test('Workflow progress is derived only from durable stage status',()=>{
 const t={graphMode:true,steps:[
  {id:'a',status:'Completed',dependsOn:[]},{id:'b',status:'Pending',dependsOn:['a']},
  {id:'c',status:'Pending',dependsOn:['b']},{id:'d',status:'Interrupted',dependsOn:['a']} ]};
 const s=summarizeWorkflowPlan(t);assert.equal(s.progress,25);assert.equal(s.steps[1].state,'ready');assert.equal(s.steps[2].state,'blocked');
 assert.equal(s.steps[3].state,'attention');
});
test('Version-based live refresh recognizes changes without model calls',()=>{
 assert.equal(isNewerVersion('a','b'),true);assert.equal(isNewerVersion('a','a'),false);
});
test('Large plan parser is bounded',()=>{
 const p=parsePlanMarkdown('# Plan\n'+Array.from({length:6000},(_,i)=>'- [ ] item '+i).join('\n'));
 assert.equal(p.clipped,true);assert.ok(p.tracked<=1000);
});
