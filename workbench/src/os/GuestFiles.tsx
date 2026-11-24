import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from './api';
import {Badge,Button,Empty,IconButton,Input,Notice,Row,Section} from '../ui/kit';
import {buildStage,buildTree,describeOp,normalizePath,parentOf,parseCommand} from '../model/fileOps.mjs';

type FileTree={files:string[];dirs?:string[];truncated:boolean};
type FileDetail={path:string;text:string;sha256:string};
type Stat={path:string;type:'file'|'dir';size:number|null;mtime:number;sha256:string};
type TrashItem={trashId:string;original:string;type:string;trashedAt:number};
type TaskDetail={task:{id:string};stages:Array<{state:string;approval:number;error:string|null;result:unknown}>};
type Op={kind:'mkdir'|'copy'|'move'|'trash'|'restore';path?:string;to?:string;trashId?:string};
type Pending={id:string;taskId:string;op:Op;state:'awaiting'|'running'|'done'|'failed'|'dismissed';error?:string;fingerprint?:string;undo?:string};
type Node={name:string;path:string;type:'dir'|'file';children:Node[]};

const REASONS:Record<string,[string,string]>={
 'empty':['请输入指令','Enter a command'],
 'unknown-command':['无法识别。可用：新建文件夹 / 复制 / 移动 / 重命名 / 删除 / 恢复（例：移动 a.txt 到 docs/a.txt）。自然语言请用“本地助手”。','Unknown command. Try: mkdir / cp / mv / rm / restore. For natural language use the Local assistant.'],
 'arity':['参数数量不对','Wrong number of arguments'],
 'invalid-path':['路径必须是工作区内的相对路径','Path must be relative to the workspace'],
 'bad-trash-id':['恢复需要 32 位回收站编号','Restore needs a 32-char trash id']
};
const STATE:Record<Pending['state'],{zh:string;en:string;tone?:'ok'|'warn'|'err'|'info'}>={
 awaiting:{zh:'等待你的批准',en:'Awaiting approval',tone:'warn'},running:{zh:'执行中',en:'Running',tone:'info'},
 done:{zh:'已完成',en:'Done',tone:'ok'},failed:{zh:'失败',en:'Failed',tone:'err'},dismissed:{zh:'已关闭',en:'Closed'}};
const errText=(e:unknown)=>e instanceof Error?e.message:String(e);

/** The guest workspace as a file manager. Reading is direct; every change is first an approval card (a one-stage DAG task),
 *  executed only after "Approve & run"; deleting only moves to the recoverable trash.
 *  `.aiws-os-file-list` / `.aiws-os-file-detail pre` are hooks of the in-image GUI smoke test. */
export default function GuestFiles({onPlanCreated,english,command}:{
 csrf?:string;onPlanCreated:()=>void;english:boolean;command?:{text:string;nonce:number}|null
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
 const reload=useCallback(async()=>{
  try{
   const [tree,bin]=await Promise.all([api<FileTree>('/workspace/tree'),api<{items:TrashItem[]}>('/workspace/trash')]);
   setFiles(tree);setTrash(bin.items);setError('');
  }catch(e){setError(errText(e));}
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
   const d=await api<FileDetail>('/workspace/file?path='+encodeURIComponent(node.path));
   setSelected({path:node.path,type:'file'});setDetail(d);setText(d.text);
  }catch(e){setSelected({path:node.path,type:'file'});setDetail(null);setError(errText(e));}
  finally{setBusy(false);lock.current=false;}
 };

 // Creating a request never executes anything: it only queues a reviewable approval card.
 const propose=useCallback(async(op:Op)=>{
  setError('');
  try{
   let stat:Stat|undefined;
   if(op.kind==='copy'||op.kind==='move'||op.kind==='trash')
    stat=await api<Stat>('/workspace/stat?path='+encodeURIComponent(op.path||''));
   const stage=buildStage(op,stat);
   const task=await api<TaskDetail>('/tasks',{method:'POST',body:JSON.stringify({
    title:'Files: '+describeOp(op,true).slice(0,140),goal:'User-requested guest file operation',stages:[stage]})});
   if(task.stages[0].approval!==0)throw new Error('Write stage did not require explicit approval');
   setPending(list=>[{id:task.task.id,taskId:task.task.id,op,state:'awaiting',fingerprint:stat?.sha256},...list]);
  }catch(e){setError(errText(e));}
 },[]);

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
   await api(base+'approve',{method:'POST',body:'{}'});
   await api(base+'dispatch',{method:'POST',body:'{}'});
   for(let i=0;i<100;i++){
    const s=(await api<TaskDetail>('/tasks/'+p.taskId)).stages[0];
    if(s.state==='completed'){
     const undo=p.op.kind==='trash'?(s.result as {trashId?:string}|null)?.trashId:undefined;
     patch(p.id,{state:'done',undo});await reload();return;
    }
    if(s.state==='failed'||s.state==='interrupted'){patch(p.id,{state:'failed',error:s.error||s.state});await reload();return;}
    await new Promise(r=>setTimeout(r,250));
   }
   patch(p.id,{state:'failed',error:tr('等待超时，请在“持久任务”中查看','Timed out; check Persistent tasks')});
  }catch(e){patch(p.id,{state:'failed',error:errText(e)});}
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
  setForm({kind,value:kind==='mkdir'?(base?base+'/':''):(selected?.path||'')});
 };
 const saveEdit=async()=>{
  if(lock.current||!detail||!editing)return;
  lock.current=true;setBusy(true);setError('');
  try{
   const planned=await api<TaskDetail>('/tasks',{method:'POST',body:JSON.stringify({
    title:'Guest file edit: '+detail.path.slice(0,100),goal:'Review before changing a guest project file',
    stages:[{key:'write',label:'Review and replace guest file',tool:'file.replace',
     arguments:{path:detail.path,text,expectedSha256:detail.sha256},dependsOn:[]}]})});
   if(!planned.task.id||planned.stages[0].approval!==0)throw new Error('Guest write stage did not require explicit approval');
   setEditing(false);onPlanCreated();
  }catch(e){setError(errText(e));}
  finally{setBusy(false);lock.current=false;}
 };

 const tree=buildTree(files?.files||[],files?.dirs||[]) as Node[];
 const rows=(nodes:Node[],depth:number):React.ReactNode[]=>nodes.flatMap(n=>[
  <Row key={n.path} depth={depth} icon={n.type==='dir'?(open.has(n.path)?'folder-opened':'folder'):'file'} expanded={n.type==='dir'?open.has(n.path):undefined}
   label={n.name} on={selected?.path===n.path} onClick={()=>void select(n)}/>,
  ...(n.type==='dir'&&open.has(n.path)?rows(n.children,depth+1):[])]);
 const visible=pending.filter(p=>p.state!=='dismissed');
 const formLabel=form?.kind==='mkdir'?tr('新文件夹路径','New folder path'):form?.kind==='copy'?tr('复制到','Copy to'):tr('移动/重命名为','Move / rename to');

 return <div className="gp aiws-os-files">
  <header><h2>{tr('AI 文件管理','AI files')}</h2>
   <Button icon="new-folder" onClick={()=>startForm('mkdir')}>{tr('新建文件夹','New folder')}</Button>
   <IconButton icon="refresh" label={tr('刷新','Refresh')} onClick={()=>void reload()}/></header>
  <p className="muted">{tr('所有会改变文件的操作都先生成待批准卡片，批准后才执行；删除只是移到可恢复的回收站。',
   'Every change creates an approval card first. Deleting only moves items to a recoverable trash.')}</p>
  {error&&<Notice tone="err">{error}</Notice>}

  {visible.length>0&&<Section title={tr('待批准的操作','Pending operations')} count={visible.length}>
   {visible.map(p=><div key={p.id} className="gp-card">
    <div className="gp-card-main"><strong>{describeOp(p.op,english)}</strong> <Badge tone={STATE[p.state].tone}>{english?STATE[p.state].en:STATE[p.state].zh}</Badge>
     {p.fingerprint&&<span className="muted"> · SHA-256 {p.fingerprint.slice(0,12)}…</span>}
     {p.error&&<p className="gp-err">{p.error}</p>}</div>
    <div className="gp-actions">
     {p.state==='awaiting'&&<><Button variant="primary" icon="check" onClick={()=>void approve(p)}>{tr('批准并执行','Approve & run')}</Button>
      <Button icon="close" onClick={()=>patch(p.id,{state:'dismissed'})}>{tr('放弃','Discard')}</Button></>}
     {p.state==='done'&&p.undo&&<Button icon="history" onClick={()=>{patch(p.id,{undo:undefined});void propose({kind:'restore',trashId:p.undo!});}}>{tr('撤销（恢复）','Undo (restore)')}</Button>}
     {(p.state==='done'||p.state==='failed')&&<Button icon="close" onClick={()=>patch(p.id,{state:'dismissed'})}>{tr('关闭','Close')}</Button>}
    </div></div>)}
  </Section>}

  {form&&<form className="form" onSubmit={e=>{e.preventDefault();submitForm();}}>
   <label>{formLabel}<Input autoFocus value={form.value} onChange={e=>setForm({...form,value:e.target.value})} aria-label={formLabel}/></label>
   <Button type="submit" variant="primary">{tr('生成待批准卡片','Create approval card')}</Button>
   <Button onClick={()=>setForm(null)}>{tr('取消','Cancel')}</Button>
  </form>}

  <div className="gp-split">
   <div className="gp-tree aiws-os-file-list" role="tree" aria-label={tr('文件列表','File list')}>
    {tree.length?rows(tree,0):<p className="muted pad">{tr('工作区目前没有文件','No files in this workspace')}</p>}
    {files?.truncated&&<p className="muted pad">{tr('已达到安全列表上限','File list capped for safety')}</p>}
   </div>
   <div className="gp-detail aiws-os-file-detail">
    {selected?<>
     <header><strong className="selectable">{selected.path}</strong>{detail&&<span className="muted">SHA-256 {detail.sha256.slice(0,16)}…</span>}</header>
     {detail&&(editing?<textarea className="k-input gp-edit" aria-label={tr('编辑文件内容','Edit file contents')} spellCheck={false} value={text} onChange={e=>setText(e.target.value)}/>
      :<pre className="gp-pre selectable">{detail.text}</pre>)}
     {!detail&&selected.type==='dir'&&<Empty icon="folder" title={tr('文件夹','Folder')}>{tr('可以移动/重命名或移到回收站。','Move, rename or move it to the trash.')}</Empty>}
     <div className="gp-actions">
      <Button icon="arrow-right" onClick={()=>startForm('move')} disabled={busy}>{tr('移动/重命名','Move / rename')}</Button>
      {selected.type==='file'&&<Button icon="copy" onClick={()=>startForm('copy')} disabled={busy}>{tr('复制','Copy')}</Button>}
      <Button icon="trash" onClick={()=>void propose({kind:'trash',path:selected.path})} disabled={busy}>{tr('移到回收站','Move to trash')}</Button>
      {detail&&(!editing?<Button icon="edit" onClick={()=>setEditing(true)} disabled={busy}>{tr('手动修改','Edit')}</Button>:
       <><Button variant="primary" icon="save" disabled={busy} onClick={()=>void saveEdit()}>{tr('提交变更','Submit edit')}</Button>
        <Button icon="discard" onClick={()=>{setEditing(false);setText(detail.text);}}>{tr('取消','Cancel')}</Button></>)}
     </div></>
     :<Empty icon="files" title={busy?tr('正在读取…','Reading…'):tr('选择一个文件或文件夹','Select a file or folder')}>
      {tr('也可以在命令面板（Ctrl+Shift+P）或总览的输入框里写：移动 a.txt 到 docs/a.txt','Or type in the overview box: mv a.txt docs/a.txt')}</Empty>}
   </div>
  </div>

  <Section title={tr('回收站','Trash')} count={trash.length}>
   {trash.length?trash.map(i=><Row key={i.trashId} icon="trash" label={i.original} detail={i.type}
     right={<Button icon="history" onClick={()=>void propose({kind:'restore',trashId:i.trashId})}>{tr('恢复','Restore')}</Button>}/>)
    :<p className="muted pad">{tr('回收站是空的','Trash is empty')}</p>}
  </Section>
 </div>;
}
