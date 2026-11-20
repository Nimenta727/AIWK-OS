import test from 'node:test';
import assert from 'node:assert/strict';
import {buildStructureTree,isVisibleInMode,summarizeStructure,measuredEventTokens,providerEventLabel,matchesPath} from '../src/model/atlas.mjs';

test('directory grouping counts affected files and includes changed ancestors',()=>{
 const roots=buildStructureTree([
  {path:'src',isDirectory:true,before:true,after:true,change:'touched'},
  {path:'src/logic',isDirectory:true,before:true,after:true,change:'touched'},
  {path:'src/logic/a.cs',isDirectory:false,before:true,after:true,change:'modified'},
  {path:'src/logic/b.cs',isDirectory:false,before:false,after:true,change:'added'},
  {path:'README.md',isDirectory:false,before:true,after:true,change:'unchanged'}
 ]);
 assert.equal(roots.find(x=>x.path==='src').changedCount,2);
 assert.equal(roots.find(x=>x.path==='src').children[0].changedCount,2);
 assert.equal(isVisibleInMode(roots.find(x=>x.path==='README.md'),'changes'),false);
 assert.equal(isVisibleInMode(roots.find(x=>x.path==='README.md'),'before'),true);
});

test('change inventory preserves file deletions and no false renames',()=>{
 const tree=buildStructureTree([{path:'old/removed.cs',isDirectory:false,before:true,after:false,change:'removed'}]);
 assert.equal(tree[0].path,'old');
 assert.equal(tree[0].children[0].change,'removed');
 assert.equal(isVisibleInMode(tree[0].children[0],'after'),false);
 assert.equal(isVisibleInMode(tree[0].children[0],'before'),true);
});

test('unsafe relative names are not projected',()=>{
 const tree=buildStructureTree([{path:'../secrets',change:'added'},{path:'C:\\Windows',change:'added'},{path:'good/file.cs',change:'unknown'}]);
 assert.deepEqual(tree.map(x=>x.path),['good']);
});

test('unknown context and token evidence remain unknown',()=>{
 assert.equal(measuredEventTokens({kind:'tool.started',input:null,output:null}),null);
 assert.deepEqual(measuredEventTokens({kind:'codex.turn.completed',input:0,output:0,cachedInput:0}),{input:0,output:0,cached:0});
 assert.match(providerEventLabel({kind:'claude.result.aggregate'}),/汇总/);
 assert.equal(summarizeStructure(null).partial,true);
});

test('missing stage structure may show incomplete side without claiming change',()=>{
 const [node]=buildStructureTree([{path:'a.cs',isDirectory:false,before:true,after:false,change:'unknown'}]);
 assert.equal(isVisibleInMode(node,'changes'),true);
 assert.equal(node.change,'unknown');
});

test('search matches nested folder changes including removed paths',()=>{
 const [root]=buildStructureTree([{path:'src/old/gone.ts',isDirectory:false,before:true,after:false,change:'removed'}]);
 assert.equal(matchesPath(root,'gone.ts'),true);
 assert.equal(matchesPath(root,'missing'),false);
 assert.equal(matchesPath(root,' OLD '),true);
});
