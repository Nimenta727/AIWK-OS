import {useCallback,useEffect,useState} from 'react';
import {Button,Empty,Icon,IconButton,Notice,Select} from '../ui/kit';
import {api} from '../os/api';
import {msg} from './common';
import type {Tr} from './common';

type Ide={installed:boolean;launcherPresent:boolean;running:boolean;version:string|null;port:number};

/** AIWS Code inside the workbench: the real Code - OSS web server (loopback only, token protected) in a tab. It is what carries large projects:
 *  indexing, search, language servers, terminal, debugging and extensions all come from the editor itself, not from this page. */
export default function IdeView({tr,folders}:{tr:Tr;folders:string[]}){
 const [ide,setIde]=useState<Ide|null>(null);
 const [folder,setFolder]=useState('.');
 const [url,setUrl]=useState('');
 const [err,setErr]=useState('');
 const [starting,setStarting]=useState(false);
 const [nonce,setNonce]=useState(0);
 const load=useCallback(async()=>{try{setIde(await api<Ide>('/ide'));}catch(e){setErr(msg(e));}},[]);
 useEffect(()=>{void load();},[load]);
 useEffect(()=>{if(!starting)return;const t=window.setInterval(()=>{void load();},1500);return()=>window.clearInterval(t);},[starting,load]);
 useEffect(()=>{if(ide?.running)setStarting(false);},[ide?.running]);
 const session=useCallback(async(path:string)=>{
  try{const r=await api<{url:string}>('/ide/session',{method:'POST',body:JSON.stringify({path})});setUrl(r.url);setErr('');}
  catch(e){setUrl('');setErr(msg(e));}
 },[]);
 useEffect(()=>{if(ide?.running)void session(folder);},[ide?.running,folder,session]);
 const start=async()=>{setErr('');try{await api('/ide/start',{method:'POST',body:'{}'});setStarting(true);}catch(e){setErr(msg(e));}};
 const window_=async()=>{try{await api('/ide/open',{method:'POST',body:'{}'});}catch(e){setErr(msg(e));}};
 if(!ide)return <p className="muted pad">…</p>;
 if(!ide.installed)return <div className="ide-info"><Empty icon="code" title={tr('AIWS Code 还没有安装在这个镜像里','AIWS Code is not installed in this image')}>
  {tr('AIWS Code 是用 VS Code 开源核心自己构建的编辑器：大型项目、搜索、语言服务、终端、调试和扩展都由它承担。构建方法见 os/ide/README.md；构建好的安装包要在制作镜像时带入。','AIWS Code is our own build of the VS Code open-source core: large projects, search, language servers, terminal, debugging and extensions all come from it. See os/ide/README.md to build it; the package is added when the image is made.')}</Empty>
  {err&&<Notice tone="err">{err}</Notice>}</div>;
 return <div className="ide">
  <div className="ide-bar">
   <Icon name="code"/><strong>AIWS Code</strong>{ide.version&&<span className="muted">{ide.version}</span>}
   <Select value={folder} onChange={e=>setFolder(e.target.value)} aria-label={tr('打开的文件夹','Folder to open')} disabled={!ide.running}>
    {[...new Set(['.',...folders])].map(f=><option key={f} value={f}>{f==='.'?tr('整个工作区','Whole workspace'):f}</option>)}</Select>
   <IconButton icon="refresh" label={tr('重新加载编辑器','Reload the editor')} disabled={!url} onClick={()=>setNonce(n=>n+1)}/>
   <IconButton icon="link-external" label={tr('在独立窗口打开','Open in its own window')} disabled={!ide.launcherPresent} onClick={()=>void window_()}/>
  </div>
  {err&&<Notice tone="err">{err}</Notice>}
  {!ide.running&&<div className="ide-info"><Empty icon="vm" title={starting?tr('正在启动…','Starting…'):tr('AIWS Code 未运行','AIWS Code is not running')}>
   {tr('它只在本机回环地址上运行，启动后会在最后一个窗口关闭时自动退出以节省资源。','It runs on the loopback address only and shuts itself down after the last window closes, to save resources.')}</Empty>
   <div className="ide-start"><Button variant="primary" icon="play" disabled={starting||!ide.launcherPresent} onClick={()=>void start()}>{tr('启动 AIWS Code','Start AIWS Code')}</Button></div></div>}
  {ide.running&&url&&<iframe key={nonce} className="ide-frame" title="AIWS Code" src={url} referrerPolicy="no-referrer"
   sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads allow-pointer-lock" allow="clipboard-read; clipboard-write"/>}
 </div>;
}
