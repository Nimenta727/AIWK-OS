import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from './api';
import {AlertTriangle,Check,ChevronDown,ChevronRight,Copy,FileText,Folder,FolderPlus,FolderTree,MoveRight,RefreshCw,Save,Trash2,Undo2,X} from 'lucide-react';
import {buildStage,buildTree,describeOp,normalizePath,parentOf,parseCommand} from '../model/fileOps.mjs';

type FileTree={files:string[];dirs?:string[];truncated:boolean};
type FileDetail={path:string;text:string;sha256:string};
type Stat={path:string;type:'file'|'dir';size:number|null;mtime:number;sha256:string};
type TrashItem={trashId:string;original:string;type:string;trashedAt:number};
type TaskDetail={task:{id:string};stages:Array<{state:string;approval:number;error:string|null;result:unknown}>};
type Op={kind:'mkdir'|'copy'|'move'|'trash'|'restore';path?:string;to?:string;trashId?:string};
type Pending={id:string;taskId:string;op:Op;state:'awaiting'|'running'|'done'|'failed'|'dismissed';error?:string;fingerprint?:string;undo?:string};
type Node={name:string;path:string;type:'dir'|'file';children:Node[]};

// shared client: localized errors and one automatic CSRF refresh, like every other page
const local=<T,>(path:string,options?:RequestInit):Promise<T>=>api<T>(path,options);

const REASONS:Record<string,[string,string]>={
 'empty':['请输入指令','Enter a command'],
 'unknown-command':['无法识别。可用：新建文件夹 / 复制 / 移动 / 重命名 / 删除 / 恢复（例：移动 a.txt 到 docs/a.txt）。自然语言将在本地模型接入后支持。','Unknown command. Try: mkdir / cp / mv / rm / restore. Natural language arrives with the local model.'],
 'arity':['参数数量不对','Wrong number of arguments'],
 'invalid-path':['路径必须是工作区内的相对路径','Path must be relative to the workspace'],
 'bad-trash-id':['恢复需要 32 位回收站编号','Restore needs a 32-char trash id']
};

export default function GuestFiles({csrf,onPlanCreated,english,command}:{
 csrf:string;onPlanCreated:()=>void;english:boolean;command?:{text:string;nonce:number}|null
}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [files,setFiles]=useState<FileTree|null>(null);
 const [trash,setTrash]=useState<TrashItem[]>([]);
 const [open,setOpen]=useState<Set<string>>(new Set());
 const [selected,setSelected]=useState<{path:string;type:'file'|'dir'}|null>(null);
 const [detail,setDetail]=useState<FileDetail|null>(null);
 const [text,setText]=useState('');
 const [editing,setEditing]=useState(false);
 const [pending,setPending]=useState<Pending[]>([]);
 const [form,setForm]=useState<{kind:'mkdir'|'copy'|'move';value:string}|null>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const lock=useRef(false);
 const headers={'Content-Type':'application/json','X-AIWS-CSRF':csrf};
 const reload=useCallback(async()=>{
  try{
   const [tree,bin]=await Promise.all([local<FileTree>('/workspace/tree'),local<{items:TrashItem[]}>('/workspace/trash')]);
   setFiles(tree);setTrash(bin.items);setError('');
  }catch(e){setError(e instanceof Error?e.message:String(e));}
 },[]);
 useEffect(()=>{void reload();},[reload]);

 const select=async(node:Node)=>{
  setForm(null);setEditing(false);
  if(node.type==='dir'){
   setSelected({path:node.path,type:'dir'});setDetail(null);
   setOpen(prev=>{const next=new Set(prev);if(next.has(node.path))next.delete(node.path);else next.add(node.path);return next;});
   return;
  }
  if(lock.current)return;
  lock.current=true;setBusy(true);setError('');
  try{
   const d=await local<FileDetail>('/workspace/file?path='+encodeURIComponent(node.path));
   setSelected({path:node.path,type:'file'});setDetail(d);setText(d.text);
  }catch(e){setSelected({path:node.path,type:'file'});setDetail(null);setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);lock.current=false;}
 };

 // Creating a request never executes anything: it only queues a reviewable approval card.
 const propose=useCallback(async(op:Op)=>{
  if(!csrf){setError(tr('会话未就绪','Session not ready'));return;}
  setError('');
  try{
   let stat:Stat|undefined;
   if(op.kind==='copy'||op.kind==='move'||op.kind==='trash')
    stat=await local<Stat>('/workspace/stat?path='+encodeURIComponent(op.path||''));
   const stage=buildStage(op,stat);
   const task=await local<TaskDetail>('/tasks',{method:'POST',headers,body:JSON.stringify({
    title:'Files: '+describeOp(op,true).slice(0,140),goal:'User-requested guest file operation',stages:[stage]})});
   if(task.stages[0].approval!==0)throw new Error('Write stage did not require explicit approval');
   setPending(list=>[{id:task.task.id,taskId:task.task.id,op,state:'awaiting',fingerprint:stat?.sha256},...list]);
  }catch(e){setError(String(e instanceof Error?e.message:e));}
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[csrf,english]);

 const runCommand=useCallback((input:string)=>{
  const parsed=parseCommand(input) as {ok:boolean;reason?:string;op?:Op};
  if(!parsed.ok||!parsed.op){const r=REASONS[parsed.reason||'unknown-command'];setError(english?r[1]:r[0]);return;}
  void propose(parsed.op);
 },[propose,english]);
 const lastNonce=useRef(0);
 useEffect(()=>{
  if(command&&command.nonce!==lastNonce.current){lastNonce.current=command.nonce;runCommand(command.text);}
 },[command,runCommand]);

 const patch=(id:string,change:Partial<Pending>)=>setPending(list=>list.map(p=>p.id===id?{...p,...change}:p));
 const approve=async(p:Pending)=>{
  if(p.state!=='awaiting')return;
  patch(p.id,{state:'running'});
  try{
   const base='/tasks/'+p.taskId+'/stages/op/';
   await local(base+'approve',{method:'POST',headers,body:'{}'});
   await local(base+'dispatch',{method:'POST',headers,body:'{}'});
   for(let i=0;i<100;i++){
    const t=await local<TaskDetail>('/tasks/'+p.taskId);
    const s=t.stages[0];
    if(s.state==='completed'){
     const undo=p.op.kind==='trash'?(s.result as {trashId?:string}|null)?.trashId:undefined;
     patch(p.id,{state:'done',undo});await reload();return;
    }
    if(s.state==='failed'||s.state==='interrupted'){patch(p.id,{state:'failed',error:s.error||s.state});await reload();return;}
    await new Promise(r=>setTimeout(r,250));
   }
   patch(p.id,{state:'failed',error:tr('等待超时，请在“持久任务”中查看','Timed out; check Persistent DAG')});
  }catch(e){patch(p.id,{state:'failed',error:String(e instanceof Error?e.message:e)});}
 };

 const submitForm=()=>{
  if(!form||!selected&&form.kind!=='mkdir')return;
  try{
   const value=normalizePath(form.value);
   if(form.kind==='mkdir')void propose({kind:'mkdir',path:value});
   else void propose({kind:form.kind,path:selected!.path,to:value});
   setForm(null);
  }catch{setError(english?REASONS['invalid-path'][1]:REASONS['invalid-path'][0]);}
 };
 const startForm=(kind:'mkdir'|'copy'|'move')=>{
  const base=selected?(selected.type==='dir'?selected.path:parentOf(selected.path)):'';
  const seed=kind==='mkdir'?(base?base+'/':''):(selected?.path||'');
  setForm({kind,value:seed});
 };
 const saveEdit=async()=>{
  if(lock.current||!detail||!editing||!csrf)return;
  lock.current=true;setBusy(true);setError('');
  try{
   const planned=await local<TaskDetail>('/tasks',{method:'POST',headers,body:JSON.stringify({
    title:'Guest file edit: '+detail.path.slice(0,100),goal:'Review before changing a guest project file',
    stages:[{key:'write',label:'Review and replace guest file',tool:'file.replace',
     arguments:{path:detail.path,text,expectedSha256:detail.sha256},dependsOn:[]}]})});
   if(!planned.task.id||planned.stages[0].approval!==0)throw new Error('Guest write stage did not require explicit approval');
   setEditing(false);onPlanCreated();
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);lock.current=false;}
 };

 const tree=buildTree(files?.files||[],files?.dirs||[]) as Node[];
 const render=(nodes:Node[],depth:number):React.ReactNode=>nodes.map(n=><div key={n.path}>
  <button type="button" style={{paddingLeft:9+depth*16}} className={selected?.path===n.path?'selected':''} onClick={()=>void select(n)}>
   {n.type==='dir'?(open.has(n.path)?<ChevronDown size={14}/>:<ChevronRight size={14}/>):<i className="aiws-os-tree-pad" aria-hidden="true"/>}
   {n.type==='dir'?<Folder size={15}/>:<FileText size={15}/>}<span>{n.name}</span></button>
  {n.type==='dir'&&open.has(n.path)&&render(n.children,depth+1)}
 </div>);
 const visible=pending.filter(p=>p.state!=='dismissed');
 const stateText:Record<string,[string,string]>={awaiting:['等待你的批准','Awaiting your approval'],running:['执行中…','Running…'],
  done:['已完成','Done'],failed:['失败','Failed']};

 return <section className="aiws-os-card aiws-os-files">
  <header className="aiws-os-files-head">
   <h2><FolderTree size={18}/>{tr('客户机工作区文件','Guest workspace files')}</h2>
   <div className="aiws-os-file-toolbar">
    <button type="button" onClick={()=>startForm('mkdir')}><FolderPlus size={15}/>{tr('新建文件夹','New folder')}</button>
    <button type="button" onClick={()=>void reload()}><RefreshCw size={15}/>{tr('刷新','Refresh')}</button>
   </div>
  </header>
  <p className="aiws-os-muted">{tr(
   '所有会改变文件的操作都先生成待批准卡片，批准后才执行；删除只是移到可恢复的回收站。',
   'Every change creates an approval card first. Deleting only moves items to a recoverable trash.')}</p>
  {error&&<p className="aiws-os-error" role="alert"><AlertTriangle size={16}/>{error}</p>}

  {visible.length>0&&<div className="aiws-os-approvals" aria-label={tr('待批准操作','Pending operations')}>
   {visible.map(p=><div key={p.id} className={'aiws-os-approval '+p.state}>
    <div><strong>{describeOp(p.op,english)}</strong>
     <small>{tr(stateText[p.state][0],stateText[p.state][1])}{p.fingerprint?' · SHA-256 '+p.fingerprint.slice(0,12)+'…':''}</small>
     {p.error&&<small className="aiws-os-error-inline">{p.error}</small>}</div>
    <div className="aiws-os-approval-actions">
     {p.state==='awaiting'&&<><button type="button" className="aiws-os-primary" onClick={()=>void approve(p)}><Check size={15}/>{tr('批准并执行','Approve & run')}</button>
      <button type="button" onClick={()=>patch(p.id,{state:'dismissed'})}><X size={15}/>{tr('放弃','Discard')}</button></>}
     {p.state==='done'&&p.undo&&<button type="button" onClick={()=>{patch(p.id,{undo:undefined});void propose({kind:'restore',trashId:p.undo!});}}><Undo2 size={15}/>{tr('撤销（恢复）','Undo (restore)')}</button>}
     {(p.state==='done'||p.state==='failed')&&<button type="button" onClick={()=>patch(p.id,{state:'dismissed'})}><X size={15}/>{tr('关闭','Close')}</button>}
    </div></div>)}
  </div>}

  {form&&<form className="aiws-os-file-form" onSubmit={e=>{e.preventDefault();submitForm();}}>
   <label>{form.kind==='mkdir'?tr('新文件夹路径','New folder path'):form.kind==='copy'?tr('复制到','Copy to'):tr('移动/重命名为','Move/rename to')}
    <input autoFocus value={form.value} onChange={e=>setForm({...form,value:e.target.value})} spellCheck={false}/></label>
   <button type="submit" className="aiws-os-primary">{tr('生成待批准卡片','Create approval card')}</button>
   <button type="button" onClick={()=>setForm(null)}>{tr('取消','Cancel')}</button>
  </form>}

  <div className="aiws-os-files-grid">
   <div className="aiws-os-file-list" aria-label={tr('文件列表','File list')}>
    {tree.length?render(tree,0):<p className="aiws-os-muted">{tr('工作区目前没有文件','No files in this workspace')}</p>}
    {files?.truncated&&<p className="aiws-os-muted">{tr('已达到安全列表上限','File list capped for safety')}</p>}
   </div>
   <div className="aiws-os-file-detail">
    {selected&&<header className="aiws-os-file-meta"><strong>{selected.path}</strong>
     {detail&&<span>SHA-256: {detail.sha256.slice(0,16)}…</span>}</header>}
    {selected?<>
     {detail&&(editing?<textarea aria-label={tr('编辑文件内容','Edit file contents')} spellCheck={false} value={text} onChange={e=>setText(e.target.value)}/>:<pre>{detail.text}</pre>)}
     {!detail&&selected.type==='dir'&&<div className="aiws-os-file-empty"><Folder size={32}/><p>{tr('文件夹','Folder')}</p></div>}
     <div className="aiws-os-file-actions">
      <button type="button" onClick={()=>startForm('move')} disabled={busy}><MoveRight size={15}/>{tr('移动/重命名','Move / rename')}</button>
      {selected.type==='file'&&<button type="button" onClick={()=>startForm('copy')} disabled={busy}><Copy size={15}/>{tr('复制','Copy')}</button>}
      <button type="button" onClick={()=>void propose({kind:'trash',path:selected.path})} disabled={busy}><Trash2 size={15}/>{tr('移到回收站','Move to trash')}</button>
      {detail&&(!editing?<button type="button" onClick={()=>setEditing(true)} disabled={busy}>{tr('手动修改','Edit')}</button>:
       <><button type="button" className="aiws-os-primary" disabled={busy||!csrf} onClick={()=>void saveEdit()}><Save size={15}/>{tr('提交变更','Submit edit')}</button>
        <button type="button" onClick={()=>{setEditing(false);setText(detail.text);}}>{tr('取消','Cancel')}</button></>)}
     </div></>:<div className="aiws-os-file-empty"><FolderTree size={36}/>
      <p>{busy?tr('正在读取…','Reading…'):tr('选择文件或文件夹；也可使用顶部指令栏','Select an item, or use the command bar above')}</p></div>}
   </div>
  </div>

  <div className="aiws-os-trash">
   <h3><Trash2 size={15}/>{tr('回收站','Trash')} ({trash.length})</h3>
   {trash.length?trash.map(i=><div key={i.trashId} className="aiws-os-trash-row">
    <span>{i.original} <small>{i.type}</small></span>
    <button type="button" onClick={()=>void propose({kind:'restore',trashId:i.trashId})}><Undo2 size={14}/>{tr('恢复','Restore')}</button></div>)
    :<p className="aiws-os-muted">{tr('回收站是空的','Trash is empty')}</p>}
  </div>
 </section>;
}
