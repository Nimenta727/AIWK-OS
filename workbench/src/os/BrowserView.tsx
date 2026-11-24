import {useEffect,useRef,useState} from 'react';
import {Button,IconButton,Input} from '../ui/kit';
import {resolveBrowserTarget} from '../model/apps.mjs';

type Target={kind:string;url?:string;path?:string};

/** Preview browser. Embeds ONLY loopback dev servers and sandboxed workspace HTML. Any other web address is never rendered
 *  inside the workbench: it is offered to the system browser, so remote pages cannot run next to the guest API. */
export default function BrowserView({english,openExternal,canOpenExternal,navigateTo}:{english:boolean;openExternal:()=>void;canOpenExternal:boolean;navigateTo?:{url:string;nonce:number}|null}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [input,setInput]=useState('');
 const [target,setTarget]=useState<Target|null>(null);
 const [history,setHistory]=useState<Target[]>([]);
 const [note,setNote]=useState('');
 const frame=useRef<HTMLIFrameElement>(null);
 const go=(text:string,push=true)=>{
  const t=resolveBrowserTarget(text) as Target;
  setNote('');
  if(t.kind==='invalid'){setNote(tr('不支持这个地址。可以输入本机开发服务（如 localhost:5173）、工作区里的 .html 文件，或网站地址（将交给系统浏览器）。','Unsupported address. Enter a local dev server (e.g. localhost:5173), a .html file in the workspace, or a web address (handed to the system browser).'));return;}
  if(t.kind==='external'){setTarget(t);setNote(tr('出于安全，外部网站不会嵌入工作台。请在系统浏览器中打开：','For safety, external sites are not embedded in the workbench. Open it in the system browser: ')+t.url);return;}
  if(t.kind==='local'&&t.url&&new URL(t.url).port===window.location.port){setNote(tr('这是工作台自己的端口，不能嵌入。','That is the workbench\'s own port and cannot be embedded.'));return;}
  if(push&&target&&target.kind!=='external')setHistory(h=>[...h.slice(-19),target]);
  setTarget(t);
 };
 // eslint-disable-next-line react-hooks/exhaustive-deps
 useEffect(()=>{if(navigateTo){setInput(navigateTo.url);go(navigateTo.url);}},[navigateTo?.nonce]);
 const back=()=>{const prev=history[history.length-1];if(!prev)return;setHistory(h=>h.slice(0,-1));setTarget(prev);setInput(prev.kind==='workspace'?prev.path||'':prev.url||'');};
 const reload=()=>{if(frame.current&&target?.url)frame.current.src=target.url;};
 return <div className="aiws-sh-file aiws-sh-fill">
  <form className="aiws-sh-urlbar" onSubmit={e=>{e.preventDefault();go(input);}} role="search">
   <IconButton icon="arrow-left" label={history.length?tr('后退','Back'):tr('后退（还没有上一页）','Back (nothing to go back to)')} disabled={!history.length} onClick={back}/>
   <IconButton icon="refresh" label={target?.url&&target.kind!=='external'?tr('刷新','Reload'):tr('刷新（还没有打开页面）','Reload (no page open)')} disabled={!target?.url||target.kind==='external'} onClick={reload}/>
   <Input className="k-input aiws-sh-url" value={input} onChange={e=>setInput(e.target.value)} aria-label={tr('地址','Address')}
    placeholder={tr('localhost:5173 · docs/index.html · https://…','localhost:5173 · docs/index.html · https://…')}/>
   <Button type="submit" variant="primary">{tr('打开','Go')}</Button>
   <IconButton icon="link-external" label={canOpenExternal?tr('在 Chromium 窗口中打开','Open a Chromium window'):tr('在 Chromium 窗口中打开（本镜像没有 Chromium）','Open a Chromium window (Chromium is not installed)')} disabled={!canOpenExternal} onClick={openExternal}/>
  </form>
  {note&&<p className="muted pad" role="status">{note}</p>}
  {target&&target.kind!=='external'&&target.url&&<iframe ref={frame} className="aiws-sh-frame" title={tr('预览','Preview')} src={target.url}
   sandbox={target.kind==='workspace'?'allow-scripts':'allow-scripts allow-forms allow-same-origin allow-popups'} referrerPolicy="no-referrer"/>}
  {!target&&<div className="aiws-sh-welcome"><h1>{tr('内置预览浏览器','Preview browser')}</h1>
   <p>{tr('用来查看你正在开发的页面：本机开发服务器（localhost）和工作区里的 HTML 文件。想浏览普通网站，请用系统浏览器。','For the page you are building: a local dev server (localhost) or an HTML file in the workspace. Use the system browser for ordinary websites.')}</p></div>}
 </div>;
}
