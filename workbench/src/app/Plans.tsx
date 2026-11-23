import {useCallback,useEffect,useMemo,useState} from 'react';
import {Badge,Button,Empty,Icon,Notice,Row} from '../ui/kit';
import {Dialog} from '../ui/Layout';
import {api} from '../os/api';
import {msg} from './common';
import type {Tr} from './common';

export type PlanStep={id:string;title:string;detail:string|null;tool:string|null;targets:string[];risk:string;hints?:string[];deps:string[];state:string;needsApproval:boolean;parsed:string|null};
export type Plan={id:string;source:'local'|'cloud';title:string;goal?:string;status:string;steps:PlanStep[];createdAt?:number;parsedFromText?:boolean;kind?:string;runId?:string};

const RISK_TONE:Record<string,'ok'|'warn'|'err'|undefined>={low:'ok',medium:'warn',high:'err'};
const STATE_ICON:Record<string,string>={completed:'pass',running:'sync',failed:'error',pending:'circle-large-outline',interrupted:'warning',unknown:'question'};

/** The plan review area: one row per step, risk computed by the platform, approvals per step. No walls of text. */
export default function Plans({tr,focus,onStop,activeRun,reload}:{tr:Tr;focus:string|null;onStop:(runId:string)=>void;activeRun:string|null;reload:()=>Promise<void>}){
 const [plans,setPlans]=useState<Plan[]>([]);
 const [sel,setSel]=useState<string|null>(focus);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [confirm,setConfirm]=useState<{plan:Plan;step:PlanStep}|null>(null);
 const load=useCallback(async()=>{try{setPlans((await api<{plans:Plan[]}>('/plans')).plans);setError('');}catch(e){setError(msg(e));}},[]);
 useEffect(()=>{void load();const t=window.setInterval(()=>{if(!document.hidden)void load();},4000);return()=>window.clearInterval(t);},[load]);
 useEffect(()=>{if(focus)setSel(focus);},[focus]);
 const ordered=useMemo(()=>[...plans].sort((a,b)=>Number(b.status==='awaiting-approval')-Number(a.status==='awaiting-approval')),[plans]);
 const plan=ordered.find(p=>p.id===sel)||ordered[0]||null;
 const approve=async(p:Plan,s:PlanStep)=>{
  setBusy(true);setError('');
  try{const base='/tasks/'+encodeURIComponent(p.id)+'/stages/'+encodeURIComponent(s.id)+'/';
   await api(base+'approve',{method:'POST',body:'{}'});await api(base+'dispatch',{method:'POST',body:'{}'});
   await new Promise(r=>setTimeout(r,400));await load();await reload();}
  catch(e){setError(msg(e));}finally{setBusy(false);}
 };
 const decide=async(runId:string,action:'approve'|'deny')=>{
  setBusy(true);setError('');
  try{await api('/builder/runs/'+encodeURIComponent(runId)+'/'+action,{method:'POST',body:'{}'});await new Promise(r=>setTimeout(r,300));await load();await reload();}
  catch(e){setError(msg(e));}finally{setBusy(false);}
 };
 const ready=(p:Plan,s:PlanStep)=>s.needsApproval&&s.deps.every(d=>p.steps.find(x=>x.id===d)?.state==='completed');
 const safeToBatch=plan?plan.steps.filter(s=>plan.source==='local'&&ready(plan,s)&&s.risk==='low'):[];
 const riskLabel=(r:string)=>({low:tr('低','low'),medium:tr('中','medium'),high:tr('高','high'),unknown:tr('未知','unknown')} as Record<string,string>)[r]||r;
 const stateLabel=(s:string)=>({completed:tr('完成','done'),running:tr('进行中','running'),failed:tr('失败','failed'),pending:tr('待处理','pending'),interrupted:tr('已中断','interrupted')} as Record<string,string>)[s]||s;
 if(!ordered.length)return <Empty icon="checklist" title={tr('还没有计划','No plans yet')}>{tr('本地模型生成的任务计划和云端 CLI 宣布的计划会显示在这里，逐步审核。','Plans from the local model and from the cloud CLI show up here for step-by-step review.')}</Empty>;
 return <div className="pl">
  <div className="pl-list" role="tree" aria-label={tr('计划列表','Plans')}>
   {ordered.map(p=><Row key={p.id} icon={p.source==='cloud'?'cloud':'checklist'} label={p.title} on={p.id===plan?.id} onClick={()=>setSel(p.id)}
    right={p.status==='awaiting-approval'?<Badge tone="warn">{tr('待审','review')}</Badge>:<span>{p.status}</span>}/>)}
  </div>
  {plan&&<div className="pl-main selectable">
   <header><div><h2>{plan.title}</h2>{plan.goal&&<p>{plan.goal}</p>}</div>
    <div className="pl-actions">
     {safeToBatch.length>0&&<Button variant="primary" icon="check-all" disabled={busy} onClick={()=>void (async()=>{for(const s of safeToBatch)await approve(plan,s);})()}>{tr('批准全部低风险步骤','Approve all low-risk')} ({safeToBatch.length})</Button>}
     {plan.kind==='native'&&plan.status==='awaiting-approval'&&plan.runId&&<>
      <Button variant="primary" icon="check" disabled={busy} onClick={()=>void decide(plan.runId as string,'approve')}>{tr('批准计划','Approve plan')}</Button>
      <Button icon="close" disabled={busy} onClick={()=>void decide(plan.runId as string,'deny')}>{tr('驳回，让它重做','Reject, ask it to revise')}</Button></>}
     {plan.source==='cloud'&&activeRun&&plan.status!=='done'&&<Button icon="debug-stop" onClick={()=>onStop(activeRun)}>{tr('停止云端运行','Stop the cloud run')}</Button>}
    </div></header>
   {error&&<Notice tone="err">{error}</Notice>}
   {plan.parsedFromText&&<Notice tone="warn">{tr('这份计划是模型写的文字，由平台按列表格式拆成步骤，可能不完全准确；风险无法判定，下面只是关键词提示。','This plan is free text written by the model; the platform split it into steps by list format, which may be inexact. Risk cannot be determined, only keyword hints are shown.')}</Notice>}
   {plan.kind==='native'?<Notice>{plan.status==='awaiting-approval'?tr('模型在等你批准这份计划，批准之前它不会动手。风险一列由平台按工具类型计算，不是模型自己说的。','The model is waiting for you to approve this plan and will not act before. The risk column is computed by the platform from each tool, not claimed by the model.'):tr('风险一列由平台按工具类型计算。每一次工具调用仍然由平台执行，需要批准的操作会在“总览”里等你。','The risk column is computed by the platform from each tool. Every tool call is still executed by the platform; actions needing approval wait for you on the Overview.')}</Notice>
    :plan.source==='cloud'&&<Notice>{tr('云端 CLI 自己决定每一步，平台无法逐步拦截；实际的约束来自你授权的范围（工具、预算、需批准的操作）。','The cloud CLI decides each step itself; the platform cannot gate steps one by one. The real limits are your mandate (tools, budget, actions needing approval).')}</Notice>}
   <table className="pl-table"><thead><tr><th>#</th><th>{tr('步骤','Step')}</th><th>{tr('工具 / 对象','Tool / targets')}</th><th>{tr('风险','Risk')}</th><th>{tr('依赖','Needs')}</th><th>{tr('状态','State')}</th><th/></tr></thead>
    <tbody>{plan.steps.map((s,i)=><tr key={s.id} className={s.risk==='high'?'hi':''}>
     <td>{i+1}</td>
     <td><strong>{s.title}</strong>{s.detail&&<div className="muted">{s.detail}</div>}{s.hints&&s.hints.length>0&&<div>{s.hints.map(h=><Badge key={h} tone="warn">{h}</Badge>)}</div>}</td>
     <td>{s.tool&&<code>{s.tool}</code>}{s.targets.map(t=><div key={t} className="muted"><code>{t}</code></div>)}</td>
     <td>{s.risk==='unknown'?<span className="muted">{riskLabel('unknown')}</span>:<Badge tone={RISK_TONE[s.risk]}>{riskLabel(s.risk)}</Badge>}</td>
     <td>{s.deps.length?s.deps.map(d=>plan.steps.findIndex(x=>x.id===d)+1).join(', '):'—'}</td>
     <td><Icon name={STATE_ICON[s.state]||'circle-large-outline'} spin={s.state==='running'}/> {stateLabel(s.state)}</td>
     <td>{plan.source==='local'&&s.needsApproval&&(ready(plan,s)?
       <Button variant={s.risk==='high'?'secondary':'primary'} disabled={busy} onClick={()=>s.risk==='high'?setConfirm({plan,step:s}):void approve(plan,s)}>{tr('批准并运行','Approve & run')}</Button>:
       <span className="muted">{tr('等待前置步骤','waiting')}</span>)}</td>
    </tr>)}</tbody></table>
  </div>}
  {confirm&&<Dialog title={tr('高风险步骤','High-risk step')} onClose={()=>setConfirm(null)}
   actions={<><Button onClick={()=>setConfirm(null)} autoFocus>{tr('取消','Cancel')}</Button>
    <Button variant="primary" onClick={()=>{const c=confirm;setConfirm(null);void approve(c.plan,c.step);}}>{tr('我确认，运行','Confirm and run')}</Button></>}>
   <p><strong>{confirm.step.title}</strong></p><p className="muted"><code>{confirm.step.tool}</code> {confirm.step.targets.join(', ')}</p>
   <p>{tr('这一步会删除、移动、启动程序或改动系统服务，可能无法撤销。','This step deletes, moves, launches a program or changes a system service and may not be undoable.')}</p></Dialog>}
 </div>;
}
