/** Pure projection helpers for the local execution atlas. Never imply model authorship. */
export const structureLabel = {
  added:'新增',removed:'删除','moved-in':'移入','moved-out':'移出',modified:'修改',replaced:'类型变化',touched:'涉及变化',unknown:'证据不足',unchanged:'未变化'
};
export const evidenceLabel = {
  Planned:'计划',Recorded:'本地记录',Imported:'用户导入',Unknown:'未知',Attention:'需关注'
};

/** Flat bounded snapshot -> nested folders. Do not make up renames from path similarity. */
export function buildStructureTree(entries = []) {
  const byPath = new Map();
  for(const e of entries) {
    if(typeof e.path !== 'string' || !e.path || e.path.startsWith('/') || e.path.includes('\\') || e.path.split('/').some(x=>!x||x==='.'||x==='..')) continue;
    byPath.set(e.path,{...e,children:[],changedCount:0});
  }
  // Checkpoint inventories can skip directories when there is incomplete evidence.
  for(const path of [...byPath.keys()]) {
    const parts=path.split('/');
    for(let i=1;i<parts.length;i++) {
      const parent=parts.slice(0,i).join('/');
      if(!byPath.has(parent)) byPath.set(parent,{path:parent,isDirectory:true,before:false,after:false,change:'unknown',evidence:'由文件路径推断的目录，不代表快照完整',children:[],changedCount:0});
    }
  }
  const roots=[];
  for(const item of byPath.values()) {
    const slash=item.path.lastIndexOf('/');
    if(slash<0) roots.push(item);
    else byPath.get(item.path.slice(0,slash))?.children.push(item);
  }
  const aggregate=node=>{
    node.children.sort((a,b)=>Number(b.isDirectory)-Number(a.isDirectory)||a.path.localeCompare(b.path,'zh-CN'));
    let count=(node.change!=='unchanged'&&node.change!=='unknown'&&!node.isDirectory)?1:0;
    for(const child of node.children) count+=aggregate(child);
    node.changedCount=count;
    return count;
  };
  roots.sort((a,b)=>Number(b.isDirectory)-Number(a.isDirectory)||a.path.localeCompare(b.path,'zh-CN'));
  roots.forEach(aggregate);
  return roots;
}

export function isVisibleInMode(node,mode){
  if(mode==='before') return !!node.before||node.children.some(child=>isVisibleInMode(child,mode));
  if(mode==='after') return !!node.after||node.children.some(child=>isVisibleInMode(child,mode));
  return node.change!=='unchanged'||node.changedCount>0||node.children.some(child=>isVisibleInMode(child,'changes'));
}

export function summarizeStructure(report){
  if(!report) return {added:0,removed:0,modified:0,directories:0,partial:true};
  return {added:report.added,removed:report.removed,modified:report.modified,directories:report.changedDirectories,partial:report.partial};
}
export function providerEventLabel(event){
  if(event.kind==='codex.turn.completed') return 'Codex 回合用量';
  if(event.kind==='codex.turn.started') return 'Codex 回合开始（导入）';
  if(event.kind==='claude.result.aggregate') return 'Claude 结果汇总（导入）';
  if(event.kind==='tool.started') return `工具开始 · ${event.toolCategory||'未知类型'}`;
  if(event.kind==='tool.completed') return `工具结束 · ${event.toolCategory||'未知类型'}`;
  return '导入事件 · '+event.kind;
}
export function measuredEventTokens(event){
  return event.input==null||event.output==null?null:{input:event.input,output:event.output,cached:event.cachedInput};
}

/** Return true if a path or any descendant matches a case-insensitive filter. */
export function matchesPath(node,query){
 const term=query.trim().toLocaleLowerCase();
 return !term||node.path.toLocaleLowerCase().includes(term)||node.children.some(c=>matchesPath(c,term));
}
