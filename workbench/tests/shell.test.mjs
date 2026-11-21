import {test} from 'node:test';
import assert from 'node:assert/strict';
import {MAX_TABS,openTab,closeTab,cycleTab,fileTabId,fileTitle,filterCommands,matchKey,isEditableTarget,sanitizePrefs,loadPrefs,savePrefs,DEFAULT_PREFS,flattenTree} from '../src/model/shell.mjs';

const T=(id,pinned=false)=>({id,kind:'page',title:id,pinned});

test('tabs are unique and focusing an open tab does not duplicate it', () => {
 let s=openTab([T('home',true)],T('a'),'home'); assert.deepEqual(s.tabs.map(t=>t.id),['home','a']); assert.equal(s.active,'a');
 s=openTab(s.tabs,T('a'),s.active); assert.equal(s.tabs.length,2);
 s=openTab(s.tabs,T('home'),s.active); assert.equal(s.active,'home');
 assert.deepEqual(openTab([T('x')],{id:''},'x'),{tabs:[T('x')],active:'x'});
});
test('opening beyond the limit drops the oldest non-pinned inactive tab, never pinned or active ones', () => {
 let s={tabs:[T('home',true)],active:'home'};
 for(let i=0;i<MAX_TABS+5;i++) s=openTab(s.tabs,T('t'+i),s.active);
 assert.equal(s.tabs.length,MAX_TABS);
 assert.ok(s.tabs.some(t=>t.id==='home'));
 assert.equal(s.active,'t'+(MAX_TABS+4));
 assert.ok(!s.tabs.some(t=>t.id==='t0'));
});
test('closing: pinned tabs stay, active falls back to the neighbour, unknown ids are ignored', () => {
 const tabs=[T('home',true),T('a'),T('b'),T('c')];
 assert.deepEqual(closeTab(tabs,'a','home'),{tabs,active:'a'});
 let s=closeTab(tabs,'b','b'); assert.deepEqual(s.tabs.map(t=>t.id),['home','a','c']); assert.equal(s.active,'c');
 s=closeTab(s.tabs,'c','c'); assert.equal(s.active,'a');
 s=closeTab(tabs,'a','c'); assert.equal(s.active,'a');
 assert.deepEqual(closeTab(tabs,'a','nope'),{tabs,active:'a'});
 assert.equal(closeTab([T('only')],'only','only').active,null);
});
test('cycling wraps in both directions', () => {
 const tabs=[T('a'),T('b'),T('c')];
 assert.equal(cycleTab(tabs,'c',1),'a'); assert.equal(cycleTab(tabs,'a',-1),'c'); assert.equal(cycleTab([],'x',1),'x');
});
test('file tab helpers', () => { assert.equal(fileTabId('a/b.txt'),'file:a/b.txt'); assert.equal(fileTitle('a/b/c.py'),'c.py'); assert.equal(fileTitle('x'),'x'); });
test('palette filtering: all words, prefix first, keywords searchable', () => {
 const cmds=[{id:1,label:'View: Observatory',keywords:'home 观察台'},{id:2,label:'View: Files',keywords:'explorer'},{id:3,label:'Toggle Theme'},{id:4,label:'Open AIWS Code',keywords:'editor ide'}];
 assert.equal(filterCommands(cmds,'').length,4);
 assert.deepEqual(filterCommands(cmds,'view').map(c=>c.id),[2,1]);   // equal rank: alphabetical
 assert.deepEqual(filterCommands(cmds,'ide').map(c=>c.id),[4]);
 assert.deepEqual(filterCommands(cmds,'观察台').map(c=>c.id),[1]);
 assert.deepEqual(filterCommands(cmds,'toggle theme').map(c=>c.id),[3]);
 assert.deepEqual(filterCommands(cmds,'zzz'),[]);
 assert.equal(filterCommands(cmds,'e')[0].label.toLowerCase().startsWith('e'),false);
});
test('shortcuts need their modifiers and ignore plain typing', () => {
 const ev=(o)=>({ctrlKey:false,metaKey:false,shiftKey:false,altKey:false,...o});
 assert.ok(matchKey(ev({ctrlKey:true,shiftKey:true,key:'P'}),'mod+shift+p'));
 assert.ok(matchKey(ev({metaKey:true,shiftKey:true,key:'p'}),'mod+shift+p'));
 assert.ok(!matchKey(ev({ctrlKey:true,key:'p'}),'mod+shift+p'));
 assert.ok(!matchKey(ev({key:'p'}),'mod+shift+p'));
 assert.ok(matchKey(ev({ctrlKey:true,key:'b'}),'mod+b'));
 assert.ok(!matchKey(ev({ctrlKey:true,altKey:true,key:'b'}),'mod+b'));
 assert.ok(matchKey(ev({key:'/'}),'/'));
 assert.ok(!matchKey(ev({ctrlKey:true,key:'/'}),'/'));
 assert.ok(isEditableTarget({tagName:'INPUT'})); assert.ok(isEditableTarget({tagName:'textarea'})); assert.ok(!isEditableTarget({tagName:'DIV'})); assert.ok(isEditableTarget({tagName:'DIV',isContentEditable:true}));
});
test('preferences are sanitised and storage failures never throw', () => {
 assert.deepEqual(sanitizePrefs({theme:'neon',sidebar:'yes',activity:'../x'}),DEFAULT_PREFS);
 assert.equal(sanitizePrefs({theme:'light'}).theme,'light');
 const mem={}; const ok={getItem:k=>mem[k]??null,setItem:(k,v)=>{mem[k]=v;}};
 assert.ok(savePrefs(ok,{theme:'light',panel:true})); assert.deepEqual(loadPrefs(ok),{...DEFAULT_PREFS,theme:'light',panel:true});
 const broken={getItem(){throw new Error('denied');},setItem(){throw new Error('denied');}};
 assert.deepEqual(loadPrefs(broken),DEFAULT_PREFS); assert.equal(savePrefs(broken,DEFAULT_PREFS),false);
 assert.deepEqual(loadPrefs({getItem:()=> '{bad'}),DEFAULT_PREFS);
});
test('explorer rows: only expanded folders show children', () => {
 const tree=[{name:'d',path:'d',type:'dir',children:[{name:'x',path:'d/x',type:'file',children:[]}]},{name:'a',path:'a',type:'file',children:[]}];
 assert.deepEqual(flattenTree(tree,new Set()).map(r=>r.path),['d','a']);
 assert.deepEqual(flattenTree(tree,new Set(['d'])).map(r=>[r.path,r.depth]),[['d',0],['d/x',1],['a',0]]);
});
