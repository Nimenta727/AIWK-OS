import {useEffect,useMemo,useState} from 'react';
import {Activity,ArrowRight,BookOpenCheck,ChevronDown,ChevronRight,Code2,FileCode2,FolderTree,GitBranch,Layers3,RefreshCcw,ShieldCheck,Workflow} from 'lucide-react';
import {bridge,type AtlasFlow,type ExecutionRecord,type StructureReport,type FileReview,type HandoffSummary,type WorkTask} from '../bridge';
import {stageTotals,measuredUsage,phaseProjection,directoryChanges} from '../model/internal-observatory.mjs';
type Props={task:WorkTask|null;language:'zh'|'en';onOpenAtlas:(id:string)=>void;onOpenPlan:()=>void;onOpenGit:()=>void;onOpenStage:(id:string)=>void};
const zh={title:'内部执行透视',intro:'一条任务，展开到 Agent、上下文、调用证据和目录结构。仅展示本地可证实的信息。',refresh:'刷新证据',empty:'选择任务查看内部执行拓扑',steps:'阶段完成',tokens:'实测输入 / 输出',unknown:'未知用量阶段',plans:'计划版本',topology:'任务与 Agent 拓扑',chain:'五段执行证据链',changes:'项目结构变化',context:'上下文来源',events:'执行事件',repo:'完整 Git 审查',atlas:'执行全景',plan:'计划中心',inspector:'阶段检查器',none:'尚无可观察证据',partial:'检查点不完整，不能宣称没有修改',local:'纯本地读取 · 不产生模型请求',caveat:'阶段状态和 CLI 启动不代表远程模型请求；没有结构化官方日志时，真实 Token 用量未知。',files:'文件',dirs:'目录',read:'查看 Diff'};
const en={title:'Internal Observatory',intro:'One task, expandable agents, context provenance, request evidence and project evolution. Only grounded local facts are shown.',refresh:'Refresh',empty:'Select a task to inspect its execution topology',steps:'Completed stages',tokens:'Measured input / output',unknown:'Unknown usage stages',plans:'Plan revisions',topology:'Agent & task topology',chain:'Five-phase evidence chain',changes:'Project structure changes',context:'Context provenance',events:'Execution events',repo:'Git review',atlas:'Execution Atlas',plan:'Plan Studio',inspector:'Stage inspector',none:'No observed evidence yet',partial:'Incomplete checkpoints: absence of changes cannot be asserted',local:'Read-only local projection · No model calls',caveat:'Stage status and CLI launch do not prove a remote model request. Actual token usage without structured provider evidence remains unknown.',files:'Files',dirs:'Directories',read:'View diff'};
const labels={Routing:['执行器分配','Routing'],Context:['上下文编译','Context'],Launcher:['CLI 启动','CLI launch'],Provider:['模型 / 工具证据','Model / tools'],Handoff:['阶段交接','Handoff']};
const evidence={Planned:['计划','Planned'],Recorded:['本地记录','Recorded'],Imported:['已导入','Imported'],Unknown:['未知','Unknown'],Attention:['需关注','Attention']};
const short=(n:number|null|undefined)=>n==null?'—':n.toLocaleString('en-US');
export function InternalObservatory({task,language,onOpenAtlas,onOpenPlan,onOpenGit,onOpenStage}:Props){
 const t=language==='zh'?zh:en,ix=language==='zh'?0:1;
 const [stageId,setStageId]=useState(''),[flow,setFlow]=useState<AtlasFlow|null>(null),[events,setEvents]=useState<ExecutionRecord[]>([]);
 const [structure,setStructure]=useState<StructureReport|null>(null),[context,setContext]=useState<HandoffSummary|null>(null);
 const [file,setFile]=useState(''),[diff,setDiff]=useState<FileReview|null>(null),[openDirs,setOpenDirs]=useState<Set<string>>(()=>new Set());
 const [tab,setTab]=useState<'changes'|'context'|'events'>('changes'),[refresh,setRefresh]=useState(0),[error,setError]=useState('');
 const taskId=task?.id;
 useEffect(()=>{setStageId(task?.steps.find(s=>s.status==='Running')?.id||task?.steps[0]?.id||'');setFile('');},[taskId]);
 useEffect(()=>{
  let current=true;setFlow(null);setEvents([]);
  if(taskId){Promise.allSettled([bridge.call<AtlasFlow>('atlas.flow',{taskId}),bridge.call<ExecutionRecord[]>('ledger.timeline',{taskId})]).then(res=>{
   if(!current)return;
   if(res[0].status==='fulfilled')setFlow(res[0].value);
   if(res[1].status==='fulfilled')setEvents(res[1].value);
   if(res.some(x=>x.status==='rejected'))setError(language==='en'?'Some local evidence sources are unavailable':'部分本地证据读取失败');
  });}
  return()=>{current=false;};
 },[taskId,task,refresh,language]);
 useEffect(()=>{
  let current=true;setStructure(null);setContext(null);setFile('');setDiff(null);setOpenDirs(new Set());
  if(taskId&&stageId)Promise.allSettled([bridge.call<StructureReport>('atlas.structure',{taskId,stepId:stageId}),bridge.call<HandoffSummary>('context.bundle',{taskId,stepId:stageId})]).then(res=>{
   if(!current)return;if(res[0].status==='fulfilled')setStructure(res[0].value);if(res[1].status==='fulfilled')setContext(res[1].value);
  });
  return()=>{current=false;};
 },[taskId,stageId,refresh]);
 useEffect(()=>{
  let current=true;setDiff(null);
  if(taskId&&stageId&&file)bridge.call<FileReview>('atlas.fileDiff',{taskId,stepId:stageId,path:file})
   .then(x=>{if(current)setDiff(x)}).catch(e=>{if(current)setError(String(e))});
  return()=>{current=false;};
 },[taskId,stageId,file,refresh]);
 const totals=useMemo(()=>stageTotals(task),[task]);
 const selected=task?.steps.find(s=>s.id===stageId),lane=flow?.lanes.find(l=>l.stepId===stageId),usage=measuredUsage(selected);
 const groups=useMemo(()=>directoryChanges(structure),[structure]);
 const select=(id:string)=>{setStageId(id);setTab('changes');};
 const toggle=(name:string)=>setOpenDirs(xs=>{const next=new Set(xs);next.has(name)?next.delete(name):next.add(name);return next});
 if(!task)return <div className="io-page"><h1>{t.title}</h1><p>{t.empty}</p></div>;
 return <div className="io-page">
  <div className="io-header"><div><div className="eyebrow">AIWS · INTERNAL OBSERVABILITY</div><h1>{t.title}</h1><p>{t.intro}</p></div>
   <button className="button secondary small" onClick={()=>setRefresh(x=>x+1)}><RefreshCcw size={15}/>{t.refresh}</button></div>
  <div className="io-metrics">
   <div><small><Workflow size={14}/>{t.steps}</small><strong>{totals.done} / {totals.count}</strong></div>
   <div><small><Activity size={14}/>{t.tokens}</small><strong>{totals.verified?short(totals.input)+' / '+short(totals.output):'—'}</strong></div>
   <div><small><ShieldCheck size={14}/>{t.unknown}</small><strong>{totals.unknown}</strong></div>
   <div><small><BookOpenCheck size={14}/>{t.plans}</small><strong>{totals.plans}</strong><button onClick={onOpenPlan}>{t.plan}<ArrowRight size={12}/></button></div>
  </div>
  {error&&<div role="alert" className="tool-error">{error}</div>}
  <div className="io-grid">
   <section className="io-panel"><header><span className="eyebrow">WORKFLOW / STAGES</span><h2>{t.topology}</h2></header>
    <div className="io-task-root"><Layers3 size={17}/><strong>{task.title}</strong></div>
    <div className="io-stages">{task.steps.map((s,i)=><button type="button" key={s.id} aria-pressed={stageId===s.id} onClick={()=>select(s.id)}>
     <span className="io-index">{i+1}</span><span className="io-stage-label"><strong>{s.title}</strong><small>{s.agent} · {s.status}</small>
     {s.dependsOn?.length>0&&<small>{s.dependsOn.length} dependencies</small>}</span><small>{measuredUsage(s).valid?short(measuredUsage(s).input!+measuredUsage(s).output!)+' t':'? t'}</small><ChevronRight size={14}/></button>)}</div>
    <button className="io-footer-link" disabled={!stageId} onClick={()=>onOpenStage(stageId)}>{t.inspector}<ArrowRight size={14}/></button>
   </section>
   <section className="io-panel"><header><span className="eyebrow">STAGE / EVIDENCE</span><h2>{selected?.title||'—'}</h2><small>{usage.valid?(short(usage.input)+' in · '+short(usage.output)+' out · '+usage.source):t.unknown}</small></header>
    <div className="io-phases">{phaseProjection(lane).map((p,i)=><div key={p.phase}><span className={'io-phase-dot '+p.state.toLowerCase()}>{i+1}</span><strong>{labels[p.phase as keyof typeof labels][ix]}</strong><small>{evidence[p.state as keyof typeof evidence]?.[ix]||p.state}</small></div>)}</div>
    <div className="io-tabs" role="tablist">{([['changes',t.changes],['context',t.context],['events',t.events]] as const).map(([id,label])=><button type="button" role="tab" aria-selected={tab===id} key={id} onClick={()=>setTab(id)}>{label}</button>)}</div>
    <div className="io-tab" role="tabpanel">{tab==='context'?<div className="io-context">
     {context?.manifest?.length?context.manifest.map((m,i)=><div key={i}><span className={m.included?'io-included':'io-excluded'}/><strong>{m.kind}</strong><small title={m.reference}>{m.reference}</small><em>{short(m.characters)} ch</em></div>):<p>{t.none}</p>}
     {context&&<small>≈ {short(context.approxTokens)} {language==='en'?'estimated':'本地估算'} Token</small>}
    </div>:tab==='events'?<div className="io-events">
     {events.filter(e=>e.stageId===stageId).slice(-30).reverse().map(e=><div key={e.id}><span>{e.evidence}</span><strong>{e.kind}</strong><small>{e.metadata||e.source}</small></div>)}
     {!events.some(e=>e.stageId===stageId)&&<p>{t.none}</p>}
    </div>:<div className="io-impacts">
     {structure?.partial&&<p className="io-warning">{t.partial}</p>}
     <p>{t.files}: {groups.reduce((n,g)=>n+g.files.length,0)} · {t.dirs}: {structure?.changedDirectories??'—'}</p>
     {groups.map(g=><div className="io-folder" key={g.dir}><button type="button" aria-expanded={openDirs.has(g.dir)} onClick={()=>toggle(g.dir)}>
      {openDirs.has(g.dir)?<ChevronDown size={14}/>:<ChevronRight size={14}/>}<FolderTree size={15}/><strong>{g.dir}</strong><small>{g.files.length}</small></button>
      {openDirs.has(g.dir)&&g.files.map(f=><button type="button" className="io-file" key={f.path} onClick={()=>setFile(f.path)}><FileCode2 size={13}/>{f.path.split('/').at(-1)}<em>{f.change}</em></button>)}</div>)}
     {!groups.length&&<p>{t.none}</p>}
     {file&&<div className="io-diff"><strong>{file}</strong><pre>{diff?.diff||diff?.note||t.none}</pre></div>}
    </div>}</div>
    <div className="io-actions"><button disabled={!stageId} onClick={()=>onOpenAtlas(stageId)}>{t.atlas}<ArrowRight size={14}/></button><button onClick={onOpenGit}><Code2 size={14}/>{t.repo}</button></div>
   </section>
  </div>
  <p className="io-caveat"><ShieldCheck size={16}/>{t.caveat}</p>
 </div>;
}