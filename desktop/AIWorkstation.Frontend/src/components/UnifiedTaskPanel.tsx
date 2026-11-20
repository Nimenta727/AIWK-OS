import {useEffect,useState} from 'react';
import {BookOpenCheck, CheckCheck, FileCode2, GitBranch, Save, ShieldCheck} from 'lucide-react';
import type {WorkTask} from '../bridge';

export function UnifiedTaskPanel({task,action,busy}:{task:WorkTask;action:(name:string,payload:Record<string,unknown>)=>Promise<void>;busy:boolean}){
 const [goal,setGoal]=useState(task.unified.goal);
 const [criteria,setCriteria]=useState(task.unified.acceptanceCriteria);
 const [editing,setEditing]=useState(false);
 useEffect(()=>{setGoal(task.unified.goal);setCriteria(task.unified.acceptanceCriteria);},[task.id,task.unified.goal,task.unified.acceptanceCriteria]);
 const unified=task.unified;
 return <section className="unified-task-panel" aria-label="AIWS 统一任务内核">
  <div className="unified-task-head"><div><div className="eyebrow">SINGLE SOURCE OF TRUTH</div><h2>统一任务档案</h2><p>目标、计划版本、工作项和 Agent 运行记录都属于当前任务，切换模型不会复制出新任务。</p></div><button className="button secondary small" onClick={()=>setEditing(x=>!x)}>{editing?'收起编辑':'编辑目标'}</button></div>
  <div className="unified-stats"><span><BookOpenCheck size={14}/> {unified.plans.length} 份计划版本</span><span><GitBranch size={14}/> {unified.workItems.length} 个工作项</span><span><FileCode2 size={14}/> {unified.artifacts.length} 个工件引用</span><span><CheckCheck size={14}/> {unified.agentRuns.length} 次本地运行意图</span></div>
  {editing?<div className="unified-edit"><label>任务总目标<textarea maxLength={6000} rows={3} value={goal} onChange={e=>setGoal(e.target.value)}/></label><label>验收标准<textarea maxLength={6000} rows={3} value={criteria} placeholder="用可验证的结果说明什么叫完成" onChange={e=>setCriteria(e.target.value)}/></label><button className="button dark small" disabled={busy||!goal.trim()} onClick={()=>void action('tasks.setBrief',{taskId:task.id,goal,acceptanceCriteria:criteria}).then(()=>setEditing(false))}><Save size={14}/> 保存统一任务目标</button></div>:<div className="unified-summary"><div><strong>目标</strong><p>{unified.goal||task.title}</p></div><div><strong>验收</strong><p>{unified.acceptanceCriteria||'未设置；可补充明确的完成标准'}</p></div></div>}
  {unified.plans.length>0&&<div className="unified-plan-refs"><strong>已绑定计划（仅哈希引用，不复制文档）</strong>{unified.plans.slice(-4).reverse().map(p=><span key={p.id}><BookOpenCheck size={13}/>{p.relativePath}<small>{p.sha256.slice(0,10)}</small></span>)}</div>}
  <div className="unified-evidence"><ShieldCheck size={14}/> 工件记录和 Agent 运行记录来自本地状态；启动 CLI 不等于模型收到请求。</div>
 </section>;
}
