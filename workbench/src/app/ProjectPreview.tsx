import {useCallback,useEffect,useState} from 'react';
import {Button,Icon,Input,Select} from '../ui/kit';
import {api} from '../os/api';
import {msg} from './common';
import type {Tr} from './common';

type St={running:boolean;url:string|null;path:string|null};

/** Preview a folder of the project (a web page, a bundler's output, generated docs) in the tab below. Read-only; stops by itself when idle. */
export default function ProjectPreview({tr,folders,onUrl}:{tr:Tr;folders:string[];onUrl:(url:string)=>void}){
 const [st,setSt]=useState<St|null>(null);
 const [folder,setFolder]=useState(folders[0]||'.');
 const [sub,setSub]=useState('');
 const [err,setErr]=useState('');
 const [busy,setBusy]=useState(false);
 const load=useCallback(async()=>{try{setSt(await api<St>('/preview'));}catch(e){setErr(msg(e));}},[]);
 useEffect(()=>{void load();},[load]);
 useEffect(()=>{if(!folders.includes(folder)&&folder!=='.')setFolder(folders[0]||'.');},[folders,folder]);
 const run=async(path:string,body:object)=>{
  setBusy(true);setErr('');
  try{const r=await api<St>(path,{method:'POST',body:JSON.stringify(body)});setSt(r);return r;}
  catch(e){setErr(msg(e));return null;}finally{setBusy(false);}
 };
 const start=async()=>{
  const rel=[folder==='.'?'':folder,sub.trim().replace(/^\/+|\/+$/g,'')].filter(Boolean).join('/')||'.';
  const r=await run('/preview',{path:rel});
  if(r?.url)onUrl(r.url);
 };
 return <div className="pv" role="group" aria-label={tr('项目预览','Project preview')}>
  <Icon name="preview"/><strong>{tr('项目预览','Project preview')}</strong>
  <Select value={folder} onChange={e=>setFolder(e.target.value)} aria-label={tr('项目文件夹','Project folder')}>
   {[...new Set(['.',...folders])].map(f=><option key={f} value={f}>{f==='.'?tr('工作区根目录','Workspace root'):f}</option>)}</Select>
  <Input value={sub} onChange={e=>setSub(e.target.value)} placeholder={tr('子文件夹，如 dist（可留空）','sub-folder, e.g. dist (optional)')} aria-label={tr('子文件夹','Sub-folder')} style={{width:210}}/>
  <Button variant="primary" icon="play" disabled={busy} onClick={()=>void start()}>{tr('启动预览','Start preview')}</Button>
  {st?.running&&<Button icon="debug-stop" disabled={busy} onClick={()=>void run('/preview/stop',{})}>{tr('停止','Stop')}</Button>}
  <span className="muted">{err?err:st?.running?tr('预览中：','Previewing: ')+(st.path==='.'?tr('工作区根目录','workspace root'):st.path)+' · '+st.url:tr('只读；空闲 15 分钟自动停止。','Read-only; stops by itself after 15 minutes idle.')}</span>
 </div>;
}
