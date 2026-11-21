import {useCallback,useEffect,useRef,useState} from 'react';
import {AlertTriangle,ChevronRight,FileText,FolderTree,RefreshCw,Save} from 'lucide-react';

type FileTree={files:string[];truncated:boolean};
type FileDetail={path:string;text:string;sha256:string};
type TaskCreated={task:{id:string};stages:Array<{state:string;approval:number}>};

async function local<T>(path:string, options?:RequestInit):Promise<T>{
 const response=await fetch('/api/v1'+path,{credentials:'omit',cache:'no-store',...options});
 const data=await response.json() as T&{error?:string};
 if(!response.ok)throw new Error(data.error||'Guest file service unavailable');
 return data;
}

export default function GuestFiles({csrf,onPlanCreated,english}:{
 csrf:string;onPlanCreated:()=>void;english:boolean
}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [files,setFiles]=useState<FileTree|null>(null);
 const [selected,setSelected]=useState<FileDetail|null>(null);
 const [text,setText]=useState('');
 const [editing,setEditing]=useState(false);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const pending=useRef(false);
 const reload=useCallback(async()=>{
  try{
   const tree=await local<FileTree>('/workspace/tree');
   setFiles(tree);
   setError('');
  }catch(e){setError(String(e));}
 },[]);
 useEffect(()=>{void reload();},[reload]);
 const open=async(path:string)=>{
  if(pending.current)return;
  pending.current=true;setBusy(true);setError('');
  try{
   const detail=await local<FileDetail>('/workspace/file?path='+encodeURIComponent(path));
   setSelected(detail);setText(detail.text);setEditing(false);
  }catch(e){setError(String(e));}
  finally{setBusy(false);pending.current=false;}
 };
 const submit=async()=>{
  if(pending.current||!selected||!editing||!csrf)return;
  pending.current=true;setBusy(true);setError('');
  try{
   const planned=await local<TaskCreated>('/tasks',{method:'POST',headers:{
    'Content-Type':'application/json','X-AIWS-CSRF':csrf
   },body:JSON.stringify({
    title:'Guest file edit: '+selected.path.slice(0,100),
    goal:'Review before changing a guest project file',
    stages:[{key:'write',label:'Review and replace guest file',
      tool:'file.replace',arguments:{
        path:selected.path,text,expectedSha256:selected.sha256
      },dependsOn:[]}]
   })});
   if(!planned.task.id||planned.stages[0].approval!==0){
    throw new Error('Guest write stage did not require explicit approval');
   }
   setEditing(false);
   onPlanCreated();
  }catch(e){setError(String(e));}
  finally{setBusy(false);pending.current=false;}
 };
 return <section className="aiws-os-card aiws-os-files">
  <header className="aiws-os-files-head">
   <h2><FolderTree size={18}/>{tr('客户机工作区文件','Guest workspace files')}</h2>
   <button type="button" onClick={()=>void reload()}><RefreshCw size={15}/>{tr('刷新','Refresh')}</button>
  </header>
  <p className="aiws-os-muted">{tr(
   '只展示客户机专用工作区；AI 可通过同一受控工具接口操作，手动编辑是可选的。',
   'Guest workspace only. AI uses the same restricted tools; manual edits remain optional.'
  )}</p>
  {error&&<p className="aiws-os-error" role="alert"><AlertTriangle size={16}/>{error}</p>}
  <div className="aiws-os-files-grid">
   <div className="aiws-os-file-list" aria-label={tr('文件列表','File list')}>
    {files?.files.length?files.files.map(path=>
     <button type="button" key={path} onClick={()=>void open(path)} className={selected?.path===path?'selected':''}>
      <FileText size={15}/><span>{path}</span><ChevronRight size={14}/></button>
    ):<p className="aiws-os-muted">{tr('工作区目前没有文件','No files in this workspace')}</p>}
    {files?.truncated&&<p className="aiws-os-muted">{tr('已达到安全列表上限','File list capped for safety')}</p>}
   </div>
   <div className="aiws-os-file-detail">
    {selected?<><header className="aiws-os-file-meta"><strong>{selected.path}</strong><span>SHA-256: {selected.sha256.slice(0,16)}…</span></header>
      {editing?<textarea aria-label={tr('编辑文件内容','Edit file contents')} spellCheck={false}
        value={text} onChange={e=>setText(e.target.value)}/>:
       <pre>{selected.text}</pre>}
      <div className="aiws-os-file-actions">
       {!editing?<button type="button" onClick={()=>setEditing(true)} disabled={busy}>
        {tr('可选：手动修改','Optional manual edit')}</button>:
        <><button type="button" className="aiws-os-primary" disabled={busy||!csrf}
         onClick={()=>void submit()}><Save size={15}/>{tr('提交客体文件变更','Submit guest edit')}</button>
         <button type="button" onClick={()=>{setEditing(false);setText(selected.text);}}>{tr('取消','Cancel')}</button></>}
      </div>
    </>:<div className="aiws-os-file-empty"><FolderTree size={36}/>
      <p>{busy?tr('正在读取…','Reading…'):tr('选择文件，查看内容和版本指纹','Select a file to inspect contents and hash')}</p>
    </div>}
   </div>
  </div>
 </section>;
}
