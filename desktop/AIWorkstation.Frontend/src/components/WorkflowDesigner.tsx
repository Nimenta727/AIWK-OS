import {useState} from 'react';
import {Plus} from 'lucide-react';
import type {WorkTask} from '../bridge';
export function WorkflowDesigner({task,action,busy}:{task:WorkTask;action:(name:string,payload:Record<string,unknown>)=>Promise<void>;busy:boolean}){
 const [title,setTitle]=useState('');const [agent,setAgent]=useState('Codex');
 const [depends,setDepends]=useState<string[]>([]);
 const [editing,setEditing]=useState('');const [editedDeps,setEditedDeps]=useState<string[]>([]);
 const editable=task.graphMode&&task.steps.every(s=>s.status==='Pending');
 if(!task.graphMode)return null;
 return <div className="dag-designer"><h3>DAG 编排器</h3><p>依赖决定阶段就绪顺序；未获批准不会自动启动模型。</p>
  <div className="dag-add"><input maxLength={100} value={title} onChange={e=>setTitle(e.target.value)} placeholder="新阶段名称" disabled={!editable}/>
   <select value={agent} disabled={!editable} onChange={e=>setAgent(e.target.value)}><option value="ClaudeCode">Claude Code</option><option value="Codex">Codex</option><option value="Manual">人工验收</option></select>
   <button className="button secondary small" disabled={!editable||busy||!title.trim()} onClick={()=>void action('steps.add',{taskId:task.id,title,agent,dependsOn:depends}).then(()=>{setTitle('');setDepends([]);})}><Plus size={14}/> 添加节点</button></div>
  <div className="dag-dependency-list"><strong>新节点依赖</strong>{task.steps.map(s=><label key={s.id}><input type="checkbox" disabled={!editable} checked={depends.includes(s.id)} onChange={e=>setDepends(xs=>e.target.checked?[...xs,s.id]:xs.filter(x=>x!==s.id))}/>{s.title}</label>)}</div>
  <div className="dag-edit"><strong>修改已有阶段依赖</strong><select disabled={!editable} value={editing} onChange={e=>{
    setEditing(e.target.value);setEditedDeps(task.steps.find(s=>s.id===e.target.value)?.dependsOn||[]);}}>
    <option value="">选择阶段</option>{task.steps.map(s=><option key={s.id} value={s.id}>{s.title}</option>)}
  </select>{editing&&<><div className="dag-dependency-list">{task.steps.filter(s=>s.id!==editing).map(s=><label key={s.id}><input type="checkbox" checked={editedDeps.includes(s.id)} onChange={e=>setEditedDeps(xs=>e.target.checked?[...xs,s.id]:xs.filter(x=>x!==s.id))}/>{s.title}</label>)}</div>
  <button className="button secondary small" disabled={!editable||busy} onClick={()=>void action('steps.dependencies',{taskId:task.id,stepId:editing,dependsOn:editedDeps})}>保存依赖</button></>}</div>
  {!editable&&<small>存在已启动阶段，工作流结构已锁定；可新建任务进行设计。</small>}
 </div>;
}
