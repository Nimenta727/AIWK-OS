import {useEffect,useRef,useState} from 'react';
import {Terminal as XTerminal} from '@xterm/xterm';
import {FitAddon} from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import {bridge,type WorkTask} from '../bridge';
import {Play,Square,ShieldAlert} from 'lucide-react';

type TerminalData={sessionId:string;text?:string;code?:number};
/** ConPTY terminal. Input comes exclusively from the user-facing xterm.js; never a model tool. */
export function TerminalPanel({task}:{task:WorkTask|null}){
 const container=useRef<HTMLDivElement|null>(null);
 const terminal=useRef<XTerminal|null>(null);
 const sid=useRef('');
 const inputQueue=useRef('');
 const sendingInput=useRef(false);
 const [active,setActive]=useState(false);
 const [busy,setBusy]=useState(false);
 const [notice,setNotice]=useState('终端由你手动控制，不会自动向模型传递输入或输出。');
 const [stageId,setStageId]=useState('');
 useEffect(()=>{if(task?.id)setStageId(task.steps.find(s=>s.status==='Running')?.id||task.steps[0]?.id||'');},[task?.id]);
 useEffect(()=>{
   if(!container.current)return;
   const x=new XTerminal({cursorBlink:true,fontFamily:'Cascadia Code,Consolas,monospace',fontSize:13,
    theme:{background:'#16191e',foreground:'#e7e4df',cursor:'#dcb49b'},scrollback:1500,convertEol:false});
   const fit=new FitAddon();x.loadAddon(fit);x.open(container.current);fit.fit();terminal.current=x;
   // Coalesce fast keystrokes and await native acknowledgements in order.
   // A per-keystroke bridge call can fill the 64-request limit and drop input.
   const flush=async()=>{
    if(sendingInput.current||!sid.current)return;
    sendingInput.current=true;
    try{
     while(inputQueue.current&&sid.current){
      const session=sid.current;
      const chunk=inputQueue.current.slice(0,2048);
      inputQueue.current=inputQueue.current.slice(chunk.length);
      await bridge.call('terminal.write',{sessionId:session,text:chunk});
      if(sid.current!==session)inputQueue.current='';
     }
    }catch(err){inputQueue.current='';setNotice(`终端输入发送失败；请检查会话状态，输入未自动重试：${String(err)}`);}
    finally{sendingInput.current=false;if(inputQueue.current&&sid.current)void flush();}
   };
   const data=x.onData(input=>{
    if(!sid.current)return;
    if(inputQueue.current.length>32_768){setNotice('输入队列已达到本地安全上限，请停止粘贴并检查终端状态。');return;}
    inputQueue.current+=input;
    void flush();
   });
   const output=bridge.onEvent('terminal.output',(v)=>{const evt=v as TerminalData;if(evt.sessionId===sid.current)x.write(evt.text||'');});
   const exited=bridge.onEvent('terminal.exited',(v)=>{const evt=v as TerminalData;if(evt.sessionId===sid.current){x.writeln('\r\n[终端已退出，exit '+evt.code+']');sid.current='';inputQueue.current='';setActive(false);}});
   const resize=()=>{fit.fit();if(sid.current)void bridge.call('terminal.resize',{sessionId:sid.current,columns:x.cols,rows:x.rows}).catch(()=>{});};
   window.addEventListener('resize',resize);
   const observer=new ResizeObserver(resize);observer.observe(container.current);
   return ()=>{observer.disconnect();window.removeEventListener('resize',resize);output();exited();data.dispose();x.dispose();terminal.current=null;
      inputQueue.current='';if(sid.current){const id=sid.current;sid.current='';void bridge.call('terminal.close',{sessionId:id}).catch(()=>{});}};
 },[task?.id]);
 const start=async()=>{if(!task||!stageId||active||busy)return;setBusy(true);inputQueue.current='';setNotice('');try{
  const result=await bridge.call<{sessionId:string}>('terminal.start',{taskId:task.id,stepId:stageId});
  sid.current=result.sessionId;setActive(true);terminal.current?.focus();
 }catch(e){setNotice(e instanceof Error?e.message:String(e));}finally{setBusy(false);}};
 const stop=async()=>{if(!sid.current||busy)return;const current=sid.current;
  setBusy(true);
  try{await bridge.call('terminal.close',{sessionId:current});if(sid.current===current)sid.current='';inputQueue.current='';setActive(false);setNotice('已关闭本地终端。');}
  catch(e){setNotice('关闭操作尚未得到确认，请检查终端状态：'+String(e));}
  finally{setBusy(false);}};
 return <div className="native-terminal"><div className="page-heading"><div><div className="eyebrow">LOCAL CONPTY SESSION</div><h1>集成 Windows 终端</h1><p>终端输出只保留在当前界面，不自动保存或提交给任何模型。</p></div></div>
  <div className="terminal-controls"><select disabled={active} value={stageId} onChange={e=>setStageId(e.target.value)}>
  {task?.steps.map(s=><option key={s.id} value={s.id}>{s.title}{s.worktreePath?' · Worktree':''}</option>)}</select>
  <button className="button dark small" disabled={!task||active||busy} onClick={start}><Play size={15}/> 启动</button>
  <button className="button secondary small" disabled={!active||busy} onClick={stop}><Square size={15}/> 关闭</button></div>
  <div ref={container} className="xterm-host" role="region" aria-label="用户控制的 Windows PowerShell 终端"/>
  <p className="terminal-note"><ShieldAlert size={14}/>{notice||'该终端拥有当前 Windows 用户权限；请勿粘贴不可信命令。'}</p>
 </div>;
}
