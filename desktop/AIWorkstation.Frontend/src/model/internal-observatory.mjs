/** Pure local projections. Stage states are NOT model-call events. */
export const phaseOrder=['Routing','Context','Launcher','Provider','Handoff'];
export function measuredUsage(step){
 const u=step?.usage;
 const valid=!!u&&Number.isFinite(u.input)&&Number.isFinite(u.output)&&u.input>=0&&u.output>=0;
 return {valid,input:valid?u.input:null,output:valid?u.output:null,source:valid?(u.source||'structured log'):''};
}
export function stageTotals(task){
 const stages=task?.steps||[];
 const modelStages=stages.filter(s=>s.agent!=='Manual');
 const measured=modelStages.map(measuredUsage);
 return {count:stages.length,done:stages.filter(s=>s.status==='Completed').length,plans:task?.unified?.plans?.length||0,
  unknown:measured.filter(x=>!x.valid).length,verified:measured.filter(x=>x.valid).length,
  input:measured.reduce((n,x)=>n+(x.input||0),0),output:measured.reduce((n,x)=>n+(x.output||0),0)};
}
export function phaseProjection(lane){
 const map=new Map((lane?.nodes||[]).filter(n=>phaseOrder.includes(n.phase)).map(n=>[n.phase,n]));
 return phaseOrder.map(phase=>({phase,node:map.get(phase)||null,state:map.get(phase)?.state||'Unknown'}));
}
export function directoryChanges(report){
 const groups=new Map();
 for(const f of report?.entries||[]){
  if(f.isDirectory||f.change==='unchanged'||typeof f.path!=='string')continue;
  const parts=f.path.split('/');
  if(parts.some(x=>!x||x==='.'||x==='..')||f.path.includes('\\')||f.path.startsWith('/'))continue;
  const dir=parts.length>1?parts.slice(0,-1).join('/'):'(root)';
  const item=groups.get(dir)||{dir,files:[]};
  item.files.push({path:f.path,change:f.change,evidence:f.evidence});
  groups.set(dir,item);
 }
 return [...groups.values()].sort((a,b)=>b.files.length-a.files.length||a.dir.localeCompare(b.dir));
}