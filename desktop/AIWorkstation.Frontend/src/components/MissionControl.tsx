import {useEffect,useMemo,useState} from 'react';
import {Activity,ArrowRight,BookOpenCheck,CheckCircle2,Clock3,Code2,GitBranch,Layers3,RefreshCcw,ShieldAlert,ShieldCheck,TerminalSquare} from 'lucide-react';
import {bridge,type DispatchPlan,type HealthSnapshot,type WorkTask} from '../bridge';
import {dispatchLabel,missionTotals,nextAction} from '../model/mission.mjs';
import {ExecutionAtlas} from './ExecutionAtlas';

type Props={task:WorkTask|null;action:(name:string,payload:Record<string,unknown>)=>Promise<void>;onOpenStep:(id:string)=>void;onOpenPlans:()=>void;onOpenProject:()=>void;busy:boolean};
export function MissionControl({task,action,onOpenStep,onOpenPlans,onOpenProject,busy}:Props){
 const [plan,setPlan]=useState<DispatchPlan|null>(null);
 const [health,setHealth]=useState<HealthSnapshot|null>(null);
 const [error,setError]=useState('');
 const [refresh,setRefresh]=useState(0);
 const [atlasOpen,setAtlasOpen]=useState(false);
 const [stageId,setStageId]=useState('');
 const [parallel,setParallel]=useState(1);
 const stats=useMemo(()=>missionTotals(task),[task]);
 useEffect(()=>{setPlan(null);setStageId('');setAtlasOpen(false);},[task?.id]);
 useEffect(()=>{
  let active=true;
  if(task)void bridge.call<DispatchPlan>('scheduler.plan',{taskId:task.id}).then(data=>{
   if(active){setPlan(data);setParallel(data.maxRecommendedActive);setStageId(before=>before&&data.stages.some(x=>x.stageId===before)?before:(data.nextStageId||data.stages[0]?.stageId||''));}
  }).catch(e=>{if(active)setError(String(e))});
  void bridge.call<HealthSnapshot>('diagnostics.health').then(data=>{if(active)setHealth(data)}).catch(e=>{if(active)setError(String(e))});
  return ()=>{active=false};
 },[task,refresh]);
 const next=nextAction(plan);
 const selected=task?.steps.find(x=>x.id===stageId);
 const selectedSlot=plan?.stages.find(x=>x.stageId===stageId);
 const execute=async(name:string,payload:Record<string,unknown>)=>{
  setError('');try{await action(name,payload);setRefresh(v=>v+1);}catch(e){setError(String(e));}
 };
 const exportHealth=async()=>{setError('');try{await bridge.call('diagnostics.export');}catch(e){setError(String(e));}};
 return <div className="mission-page">
  <div className="page-heading"><div><div className="eyebrow">MISSION CONTROL / ONE TASK, MANY AGENTS</div><h1>AI 协作总控台</h1>
   <p>一条任务统一计划、Agent 调度、上下文、Git 变化与本地审计；排队与查看不会调用模型。</p></div>
   <button className="button secondary small" onClick={()=>setRefresh(x=>x+1)}><RefreshCcw size={15}/>刷新本地状态</button></div>
  {!task?<div className="blank-state"><GitBranch size={24}/>先从左侧选择任务，或者新建一个协作任务。</div>:<>
  <div className="mission-metrics">
   <div><small>完成进度</small><strong>{stats.done}/{stats.total}</strong><span>已确认阶段</span></div>
   <div><small>排队 / 执行</small><strong>{plan?.queuedStages??'—'} / {stats.running}</strong><span>排队不是远程模型调用</span></div>
   <div><small>已绑定计划</small><strong>{stats.plans}</strong><span>保存版本与来源</span></div>
   <div><small>未知 Token 阶段</small><strong>{stats.unknownUsage}</strong><span>未知不等于 0</span></div>
  </div>
  {error&&<div className="tool-error" role="alert">{error}</div>}
  <div className="mission-actions"><button className="button secondary small" onClick={onOpenPlans}><BookOpenCheck size={15}/>查看计划中心</button>
   <button className="button secondary small" onClick={onOpenProject}><Code2 size={15}/>查看代码与目录</button>
   <button className="button secondary small" onClick={()=>setAtlasOpen(v=>!v)}><Layers3 size={15}/>{atlasOpen?'收起':'展开'}调用与结构总览</button></div>
  <div className="mission-columns">
   <section className="mission-card"><div className="mission-card-head"><div><h2>任务 DAG / 调度队列</h2><p>{task.title} · {plan?.mode==='human-supervised'?'用户监督模式':'读取策略中'}</p></div><span>{plan?.readyStages??0} 待排队</span></div>
    <div className="mission-queue">{plan?.stages.map((item,i)=><button className={`mission-stage ${stageId===item.stageId?'active':''}`} key={item.stageId} onClick={()=>setStageId(item.stageId)}>
     <span className="mission-stage-order">{i+1}</span><span className="mission-stage-label"><strong>{item.title}</strong><small>{item.agent} · {dispatchLabel(item.status)}</small></span><small>{item.approxTokens?`≈${item.approxTokens} tokens`:''}</small><ArrowRight size={14}/></button>)}
    {!plan&&<div className="project-empty">正在本地计算 DAG 和执行器可用性…</div>}</div>
    <div className="mission-policy"><label>调度建议的最大并行阶段数 <select value={parallel} disabled={busy} onChange={e=>setParallel(Number(e.target.value))}>
      {[1,2,3,4].map(x=><option key={x} value={x}>{x}</option>)}</select></label>
     <button className="button secondary small" disabled={busy||parallel===plan?.maxRecommendedActive} onClick={()=>void execute('scheduler.parallel',{taskId:task.id,limit:parallel})}>保存策略</button>
    </div><p className="mission-fineprint">这是一项调度建议，不是进程安全沙箱。只有不同 Worktree 才能安全地并行安排写入阶段；任何 CLI 启动仍需用户确认。</p>
   </section>
   <section className="mission-card"><div className="mission-card-head"><div><h2>下一步与执行证据</h2><p>状态由 AIWS 保存，不取决于当前聊天窗口。</p></div><Activity size={18}/></div>
    {selected&&selectedSlot?<div className="mission-focused"><span className="eyebrow">当前选中阶段</span><h3>{selected.title}</h3><p>{selectedSlot.reason}</p>
      <div className="mission-stage-facts"><span>执行器 <strong>{selectedSlot.agent}</strong></span><span>依赖 <strong>{selectedSlot.dependencyCount}</strong></span><span>本地草稿 <strong>{selectedSlot.approxTokens?`约 ${selectedSlot.approxTokens} Token`:'不适用 / 未知'}</strong></span>
       <span>Git 证据 <strong>{selected.gitBefore?'已有开始检查点':'暂无完整开始证据'}</strong></span></div>
      {selectedSlot.status==='unavailable'&&selectedSlot.recommendedAgent&&<button className="button secondary" disabled={busy} onClick={()=>void execute('steps.switchAgent',{taskId:task.id,stepId:selected.id,agent:selectedSlot.recommendedAgent})}>切换至可用的 {selectedSlot.recommendedAgent==='Codex'?'Codex':'Claude Code'}（撤销原审批）</button>}
      {selectedSlot.status==='approval'&&<button className="button secondary" disabled={busy} onClick={()=>void execute('scheduler.prepare',{taskId:task.id,stepId:selected.id})}><ShieldCheck size={15}/>审批并加入调度队列</button>}
      {selectedSlot.canQueue&&<button className="button dark" disabled={busy} onClick={()=>void execute('scheduler.queue',{taskId:task.id,stepId:selected.id})}><CheckCircle2 size={15}/>加入本地调度队列</button>}
      {selectedSlot.isQueued&&selected.agent!=='Manual'&&<button className="button dark" disabled={busy} onClick={()=>void execute('steps.launch',{taskId:task.id,stepId:selected.id})}><TerminalSquare size={15}/>从总控台确认启动官方 CLI</button>}
      {selectedSlot.isQueued&&selected.agent==='Manual'&&<button className="button dark" disabled={busy} onClick={()=>void execute('steps.startManual',{taskId:task.id,stepId:selected.id})}><CheckCircle2 size={15}/>开始人工验收阶段</button>}
      {selectedSlot.isQueued&&selectedSlot.ticketId&&<button className="button secondary" disabled={busy} onClick={()=>void execute('scheduler.cancel',{taskId:task.id,ticketId:selectedSlot.ticketId!})}>撤销排队（不影响 Git）</button>}
      <button className="button secondary" onClick={()=>onOpenStep(selected.id)}><TerminalSquare size={15}/>到阶段检查器确认启动或记录结果</button>
    </div>:<div className="project-empty">没有可用阶段。</div>}
    {next&&<p className="mission-next">系统推荐关注：{next.title} — {dispatchLabel(next.status)}。推荐不等于授权或自动执行。</p>}
    <div className="mission-diagnostics"><h3>本机可靠性检查</h3><div><Clock3 size={15}/>运行中 {health?.runningStages??'—'}，中断待核查 {health?.interruptedStages??'—'}</div>
     <div><ShieldAlert size={15}/>备份 {health?.backupAvailable?'存在':'尚未创建 / 无历史版本'}</div>
     <p>{health?.releaseNotice||'正在读取本地诊断。'}</p>
     <button className="button secondary small" onClick={()=>void exportHealth()}>导出脱敏诊断 JSON</button></div>
   </section>
  </div>
  {atlasOpen&&<div className="mission-atlas"><ExecutionAtlas task={task} preferredStageId={stageId}/></div>}
  <div className="mission-footer"><ShieldCheck size={16}/>调度、计划和 Git 投影是纯本地操作。外部 Claude/Codex 的未公开内部请求、实际 Token 与无人值守调度仍不属于可保证能力。</div>
  </>}
 </div>;
}
