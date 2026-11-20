import {useEffect,useState} from 'react';
import { CheckCircle2, ClipboardCheck, Play, RotateCcw, ShieldAlert } from 'lucide-react';
import type {WorkTask,WorkStep} from '../bridge';
import {agentName} from '../model/workflow.mjs';
export function TaskInspector({task,step,action,busy}:{task:WorkTask;step:WorkStep|null;action:(name:string,params?:Record<string,unknown>)=>void;busy:boolean}){
  const [result,setResult]=useState('');
  useEffect(()=>setResult(step?.result||''),[step?.id,step?.result]);
  if(!step) return <div className="inspector-placeholder"><div className="inspector-illustration">✳</div><strong>选择一个阶段</strong><p>查看 Agent、审批、执行状态和用量证据。</p></div>;
  const pending=step.status==='Pending', running=step.status==='Running';
  return <div className="inspector-body">
    <div className="overline">阶段检查器</div><h2>{step.title}</h2><div className="pill-row"><span className="pill">{agentName(step.agent)}</span><span className="pill muted">{step.status}</span></div>
    <div className="divider"/><div className="field"><label>任务目标</label><p className="instructions">{step.instructions}</p></div>
    <div className="field"><label>安全审批</label><p className="supporting">{step.requiresApproval?step.approvalGranted?'已为此阶段一次性批准':'需要批准后才可启动':'无需额外审批，但启动外部 CLI 仍需明确确认'}</p></div>
    {pending&&step.requiresApproval&&!step.approvalGranted&&<button className="button secondary full" disabled={busy} onClick={()=>action('steps.approve',{taskId:task.id,stepId:step.id})}><ClipboardCheck size={16}/> 批准该阶段</button>}
    {pending&&step.agent==='Manual'&&<button className="button secondary full" disabled={busy||(step.requiresApproval&&!step.approvalGranted)} onClick={()=>action('steps.startManual',{taskId:task.id,stepId:step.id})}><Play size={16}/> 开始人工阶段</button>}
    {pending&&step.agent!=='Manual'&&<button className="button dark full" disabled={busy||(step.requiresApproval&&!step.approvalGranted)} onClick={()=>action('steps.launch',{taskId:task.id,stepId:step.id})}><Play size={16}/> 启动官方 CLI</button>}
    {running&&<><div className="field"><label>实际执行结果（人工确认）</label><textarea value={result} rows={5} onChange={e=>setResult(e.target.value)} maxLength={12000} placeholder="粘贴已核实的执行结果。外部 CLI 不会自动交回内容。"/></div><button className="button dark full" disabled={busy||!result.trim()} onClick={()=>action('steps.complete',{taskId:task.id,stepId:step.id,result})}><CheckCircle2 size={16}/> 标记完成并保存</button></>}
    {step.status==='Failed'||step.status==='Interrupted'?<button className="button secondary full" disabled={busy} onClick={()=>action('steps.retry',{taskId:task.id,stepId:step.id})}><RotateCcw size={16}/> 重置阶段</button>:null}
    <div className="divider"/><div className="field"><label>Token 观测</label>{step.usage?.input!=null&&step.usage?.output!=null?<p className="supporting">输入 {step.usage.input.toLocaleString()} · 输出 {step.usage.output.toLocaleString()}<br/>来源：{step.usage.source}</p>:<p className="supporting">无结构化计量证据 · 真实使用量未知</p>}</div>
    <div className="inspector-warning"><ShieldAlert size={15}/><span>批准并不授予管理员权限；CLI 以当前 Windows 用户权限运行。</span></div>
  </div>;
}
