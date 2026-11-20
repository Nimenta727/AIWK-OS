import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Activity,ArrowRight,BookOpen,Check,CheckCircle2,ChevronDown,ChevronRight,Clock3,FileText,FolderOpen,GitBranch,Info,Layers,LayoutList,ListChecks,RefreshCw,Search,ShieldCheck,Workflow} from 'lucide-react';
import {bridge,type PlanCatalog,type PlanDocument,type WorkTask} from '../bridge';
import {parsePlanMarkdown,summarizeWorkflowPlan} from '../model/plan.mjs';

type PlanSection={id:string;title:string;level:number;line:number;items:{id:string;line:number;text:string;tracked:boolean;completed:boolean;indent:number}[];notes:string[]};
type PlanOutline={sections:PlanSection[];tracked:number;done:number;pending:number;untracked:number;clipped:boolean;progress:number|null};
type View='outline'|'board'|'source';
const labels:Record<string,string>={done:'已完成',running:'执行中',attention:'需关注',blocked:'等待依赖',ready:'待执行'};

function Meter({value,unknown=false}:{value:number;unknown?:boolean}){
 return <div className="plan-meter" role="progressbar" aria-label={unknown?'计划进度未知':'计划完成率'} aria-valuenow={unknown?undefined:value} aria-valuemin={unknown?undefined:0} aria-valuemax={unknown?undefined:100}>
  <div className={unknown?'plan-meter-unknown':'plan-meter-bar'} style={{width:unknown?'100%':`${Math.min(100,Math.max(0,value))}%`}}/>
 </div>;
}

export function PlanCenter({task,onRefresh,onOpenStep,onOpenAtlas}:{task:WorkTask|null;onRefresh:()=>Promise<void>;onOpenStep:(id:string)=>void;onOpenAtlas:()=>void}){
 const [scopeStep,setScopeStep]=useState('');
 const [catalog,setCatalog]=useState<PlanCatalog|null>(null);
 const [path,setPath]=useState('');
 const [document,setDocument]=useState<PlanDocument|null>(null);
 const [view,setView]=useState<View>('outline');
 const [collapsed,setCollapsed]=useState<Set<string>>(()=>new Set());
 const [query,setQuery]=useState('');
 const [error,setError]=useState('');
 const [lastCheck,setLastCheck]=useState<Date|null>(null);
 const [busy,setBusy]=useState(false);
 const [revision,setRevision]=useState(0);
 const [updates,setUpdates]=useState<string[]>([]);
 const taskId=task?.id;
 const previousCatalog=useRef<PlanCatalog|null>(null);
 const catalogGeneration=useRef(0);
 useEffect(()=>{catalogGeneration.current++;previousCatalog.current=null;setScopeStep('');setCatalog(null);setPath('');setDocument(null);setCollapsed(new Set());setQuery('');setUpdates([]);setError('');},[taskId]);
 const loadCatalog=useCallback(async()=>{
  if(!taskId)return;
  const generation=catalogGeneration.current;
  const data=await bridge.call<PlanCatalog>('plans.list',{taskId,...(scopeStep?{stepId:scopeStep}:{})});
  if(generation!==catalogGeneration.current)return;
  const old=previousCatalog.current;
  if(old&&old.workspace===data.workspace){
   const prev=new Map(old.files.map(f=>[f.path,f.version]));
   const changed=data.files.filter(f=>prev.has(f.path)&&prev.get(f.path)!==f.version);
   if(changed.length)setUpdates(rows=>[`${new Date().toLocaleTimeString('zh-CN')} · 更新：${changed.map(f=>f.name).slice(0,3).join('、')}`,...rows].slice(0,6));
  }
  previousCatalog.current=data;
  setCatalog(data);
  setLastCheck(new Date());
 },[taskId,scopeStep]);
 // Local-only refresh every 3 seconds *while the Plan Center is mounted*.
 // An active poll cannot overlap the next one; no provider request is issued.
 useEffect(()=>{
  if(!taskId)return;
  let alive=true,inFlight=false;
  const run=async()=>{
   if(!alive||inFlight)return;inFlight=true;
   try{await Promise.all([loadCatalog(),onRefresh()]);if(alive)setError('');}
   catch(ex){if(alive)setError(ex instanceof Error?ex.message:String(ex));}
   finally{inFlight=false;}
  };
  void run();const timer=window.setInterval(()=>{void run();},3000);
  return()=>{alive=false;window.clearInterval(timer);};
 },[taskId,loadCatalog,onRefresh]);
 const meta=catalog?.files.find(f=>f.path===path);
 useEffect(()=>{
  let alive=true;
  if(!taskId||!path||!meta){setDocument(null);return;}
  void bridge.call<PlanDocument>('plans.read',{taskId,path,...(scopeStep?{stepId:scopeStep}:{})}).then(doc=>{
   if(alive){setDocument(doc);setCollapsed(new Set());}
  }).catch(ex=>{if(alive){setDocument(null);setError(ex instanceof Error?ex.message:String(ex));}});
  return()=>{alive=false;};
 },[taskId,path,meta?.version,scopeStep,revision]);
 const workflow=useMemo(()=>summarizeWorkflowPlan(task),[task]);
 const outline=useMemo(()=>document?parsePlanMarkdown(document.text) as PlanOutline:null,[document]);
 const activePlan=Boolean(path);
 const matchingSections=useMemo(()=>outline?.sections.filter(s=>!query.trim()||s.title.toLowerCase().includes(query.toLowerCase())||s.items.some(i=>i.text.toLowerCase().includes(query.toLowerCase())))||[],[outline,query]);
 const manualRefresh=async()=>{
  setBusy(true);setError('');try{await Promise.all([loadCatalog(),onRefresh()]);setRevision(v=>v+1);}
  catch(ex){setError(ex instanceof Error?ex.message:String(ex));}finally{setBusy(false);}
 };
 const toggle=(id:string)=>setCollapsed(prev=>{const next=new Set(prev);if(next.has(id))next.delete(id);else next.add(id);return next;});
 if(!task)return <div className="plan-center"><div className="page-heading"><div><div className="eyebrow">AIWS PLAN STUDIO</div><h1>计划中心</h1><p>先选择一个工作流任务，阅读和跟踪它的计划。</p></div></div><div className="blank-state">目前没有选中的任务。新建任务后可以查看阶段计划和本地 Markdown 计划书。</div></div>;
 return <div className="plan-center">
  <header className="plan-header"><div><div className="eyebrow">PLAN STUDIO · LOCAL-FIRST</div><h1>计划中心</h1><p>{task.title} · 把复杂计划拆成清晰的阶段与可展开的行动清单</p></div>
   <div className="plan-header-controls"><span className="plan-live"><i/>每 3 秒同步本地进度</span><button className="button secondary small" disabled={busy} onClick={()=>void manualRefresh()}><RefreshCw size={14}/>{busy?'检查中':'立即同步'}</button></div></header>
  <div className="plan-kpis"><div><span>工作流完成率</span><strong>{workflow.progress}%</strong><Meter value={workflow.progress}/><small>{workflow.completed} / {workflow.total} 个阶段完成</small></div>
   <div><span>正在执行</span><strong>{workflow.running}</strong><small>来自 AIWS 已保存的阶段状态</small></div>
   <div><span>检测到的计划书</span><strong>{catalog?.files.length??'—'}</strong><small>仅当前工作目录 · Markdown</small></div>
   <div><span>本地检测时间</span><strong className="plan-time">{lastCheck?lastCheck.toLocaleTimeString('zh-CN'):'等待连接'}</strong><small>不触发任何模型调用</small></div>
  </div>
  {error&&<div className="tool-error" role="alert">{error}</div>}
  <div className="plan-security"><ShieldCheck size={15}/> 本页面只读取本地计划与工作流状态。计划文件勾选项只反映原文状态；AIWS 不会替模型修改计划、不向模型发送文件、也不会假装读取了 CLI 内部规划。</div>
  <div className="plan-layout">
   <aside className="plan-library"><div className="plan-panel-head"><strong><BookOpen size={16}/>计划来源</strong><small>选择视图</small></div>
    <button className={`plan-source ${!activePlan?'active':''}`} onClick={()=>{setPath('');setDocument(null);setView('board');}}><Workflow size={17}/><span><strong>任务执行计划</strong><small>AIWS 阶段状态 · 实时同步</small></span><ChevronRight size={14}/></button>
    <div className="plan-folder-row"><FolderOpen size={14}/><strong>项目计划文档</strong><span>{catalog?.files.length||0}</span></div>
    <label className="plan-workspace-label">扫描工作区</label><select className="plan-scope" value={scopeStep} onChange={e=>{catalogGeneration.current++;previousCatalog.current=null;setCatalog(null);setScopeStep(e.target.value);setPath('');setDocument(null);setUpdates([]);}}><option value="">任务主目录</option>{task.steps.filter(s=>s.worktreePath).map(s=><option key={s.id} value={s.id}>{s.title} · Worktree</option>)}</select>
    <div className="plan-file-list">{catalog?.files.map(f=><button className={`plan-source ${path===f.path?'active':''}`} key={f.path} onClick={()=>{setPath(f.path);setView('outline');}} title={f.path}><FileText size={16}/><span><strong>{f.name}</strong><small>{f.path} · {(f.bytes/1024).toFixed(1)} KB</small></span></button>)}
     {catalog&&catalog.files.length===0&&<div className="plan-empty-file">未找到 Markdown 计划。可在 <code>docs/ROADMAP.md</code>、<code>docs/plans/</code>、<code>plans/</code>、<code>.claude/plans/</code> 等位置保存计划。</div>}
    </div>
    {catalog?.notices.map((note,i)=><div className="plan-library-note" key={i}><Info size={12}/>{note}</div>)}
   </aside>
   <section className="plan-workarea">
    <div className="plan-workarea-top"><div><div className="eyebrow">{activePlan?'MARKDOWN OUTLINE':'WORKFLOW BOARD'}</div><h2>{activePlan?(path.split('/').at(-1)||'计划文档'):'任务执行总览'}</h2><small>{activePlan?`${path} · ${document?new Date(document.updatedAt).toLocaleString('zh-CN'):'读取中…'}`:'来自 AIWS 持久化任务状态；不等于模型内部请求数'}</small></div>
     <div className="plan-view-buttons">{activePlan&&([['outline','大纲'],['board','看板'],['source','原文']] as const).map(([id,label])=><button key={id} className={view===id?'active':''} onClick={()=>setView(id)}>{label}</button>)}<button onClick={onOpenAtlas}><Layers size={13}/>调用与结构</button></div>
    </div>
    {!activePlan?<div className="plan-stage-board">
      <div className="plan-section-progress"><strong>整体执行阶段</strong><span>{workflow.progress}% 已确认完成</span><Meter value={workflow.progress}/></div>
      <div className="plan-stage-columns">{([['ready','待执行与等待'],['running','执行中'],['done','已完成'],['attention','需关注']] as const).map(([key,title])=>{
       const items=workflow.steps.filter((x:{state:string})=>key==='ready'?x.state==='ready'||x.state==='blocked':x.state===key);
       return <div className="plan-stage-column" key={key}><div className="plan-column-heading"><strong>{title}</strong><span>{items.length}</span></div>{items.map((step:{id:string;title:string;index:number;status:string;state:string;dependsOn:string[];agent:string;instructions:string})=><button key={step.id} className={`plan-stage-card ${step.state}`} onClick={()=>onOpenStep(step.id)}><span className="plan-card-top"><small>阶段 {step.index} · {step.agent==='ClaudeCode'?'Claude':step.agent==='Codex'?'Codex':'人工'}</small><em>{labels[step.state]}</em></span><strong>{step.title}</strong><p>{step.instructions?.slice(0,130)||'未填写阶段说明'}</p><small>{step.dependsOn?.length?`依赖 ${step.dependsOn.length} 个阶段`:'无显式依赖'} <ArrowRight size={12}/></small></button>)}{!items.length&&<div className="plan-no-card">暂无阶段</div>}</div>;
      })}</div>
      <div className="plan-footer-note"><Info size={14}/>阶段进度来自本地审批与状态更新；打开阶段可继续查看 Agent 执行、Token、上下文和代码变化。</div>
    </div>:!document?<div className="plan-loading"><Activity size={21}/>读取本地计划文档…</div>:<>
      <div className="plan-document-kpis"><span>{outline?.sections.length||0} 个章节</span><span>{outline?.tracked||0} 个清单项</span><span>{outline?.done||0} 项原文已勾选</span><span>文档进度 {outline?.progress!=null?`${outline.progress}%`:'未知（无勾选项）'}</span></div>
      <Meter value={outline?.progress||0} unknown={outline?.progress==null}/>
      {outline?.clipped&&<div className="plan-library-note">计划过长，仅展示前 5,000 行和限量章节/清单。原始文件没有修改。</div>}
      {view==='source'?<pre className="plan-markdown-raw">{document.text}</pre>:<>
       <label className="plan-query"><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索计划标题与行动项" aria-label="搜索计划内容"/></label>
       <div className={view==='board'?'plan-outline-grid':'plan-outline-list'}>{matchingSections.map(section=>{
        const isCollapsed=collapsed.has(section.id);
        const tracked=section.items.filter(i=>i.tracked);
        const checked=tracked.filter(i=>i.completed).length;
        return <article className="plan-section" key={section.id}>
          <button className="plan-section-title" onClick={()=>toggle(section.id)}><span className="plan-chapter-icon">{isCollapsed?<ChevronRight size={17}/>:<ChevronDown size={17}/>}</span><span className="plan-section-caption"><small>LEVEL {section.level} · LINE {section.line}</small><strong>{section.title}</strong></span><span className="plan-chapter-count">{tracked.length?`${checked}/${tracked.length}`:`${section.items.length} 项`}</span></button>
          {!isCollapsed&&<div className="plan-section-content">{section.notes.slice(0,view==='board'?2:5).map((note,i)=><p className="plan-section-note" key={i}>{note}</p>)}
          {section.items.filter(i=>!query.trim()||section.title.toLowerCase().includes(query.toLowerCase())||i.text.toLowerCase().includes(query.toLowerCase())).map(item=><div key={item.id} className={`plan-check-item ${item.completed?'complete':''}`} style={{paddingLeft:Math.min(item.indent,4)*14}}><span className={`plan-check ${item.completed?'checked':item.tracked?'':'untracked'}`}>{item.completed?<Check size={12}/>:item.tracked?'':<LayoutList size={12}/>}</span><span>{item.text}</span><small>{item.line}</small></div>)}
          {section.items.length===0&&<small className="plan-no-items">此章节没有 Markdown 列表项。</small>}</div>}
         </article>;
       })}{matchingSections.length===0&&<div className="plan-no-card">没有符合条件的章节。</div>}</div>
      </>}
      <div className="plan-footer-note"><Info size={14}/>计划完成率只依据 Markdown 中的 <code>- [x]</code> / <code>- [ ]</code>，而不是 AIWS 推断。未标记的任务不计入完成率。</div>
    </>}
   </section>
  </div>
  {updates.length>0&&<div className="plan-updates"><Clock3 size={15}/><strong>监测到的本地计划更新</strong>{updates.map((row,i)=><span key={i}>{row}</span>)}</div>}
  <div className="plan-foot"><ListChecks size={16}/> 当前阶段进度与本地文件变更由 AIWS 轮询；外部 Claude/Codex 未通过公开接口报告的规划事件仍不可见。</div>
 </div>;
}
