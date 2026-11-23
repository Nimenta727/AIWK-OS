import {useCallback,useEffect,useState} from 'react';
import {Button,Icon,IconButton,Input,Notice,Section,Select} from '../ui/kit';
import {Dialog} from '../ui/Layout';
import {api} from '../os/api';
import {msg} from './common';
import {localizeError} from '../model/errors.mjs';
import type {Tr} from './common';

type Output={name:string;modes:string[];current:string|null};
type Wifi={ssid:string;signal:number|null;secured:boolean;inUse:boolean};
type Status={display:{outputs?:Output[];error?:string};input:{installed:boolean;running:boolean;active:string|null};
 network:{installed:boolean;devices:{device:string;type:string;state:string;connection:string|null}[];wifi:Wifi[]}};
const IME=['keyboard-us','pinyin'];

/** Display, input method, network, power: everything a desktop panel used to do. Each control calls one fixed endpoint, then re-reads the system. */
export default function SystemPage({tr}:{tr:Tr}){
 const [st,setSt]=useState<Status|null>(null);
 const [note,setNote]=useState<{tone:'ok'|'err';text:string}|null>(null);
 const [busy,setBusy]=useState(false);
 const [ssid,setSsid]=useState('');const [pw,setPw]=useState('');
 const [power,setPower]=useState<''|'poweroff'|'reboot'>('');
 const load=useCallback(async()=>{try{setSt(await api<Status>('/system'));}catch(e){setNote({tone:'err',text:msg(e)});}},[]);
 useEffect(()=>{void load();},[load]);
 const run=async(kind:string,body:object,done:string)=>{
  if(busy)return false;setBusy(true);setNote(null);
  try{await api('/system/'+kind,{method:'POST',body:JSON.stringify(body)});setNote({tone:'ok',text:done});await load();return true;}
  catch(e){setNote({tone:'err',text:msg(e)});return false;}finally{setBusy(false);}
 };
 const out=st?.display.outputs?.[0];
 return <div className="sys selectable">
  <header><h2>{tr('系统','System')}</h2><IconButton icon="refresh" label={tr('刷新','Refresh')} onClick={()=>void load()}/></header>
  {note&&<Notice tone={note.tone}>{note.text}</Notice>}
  <Section title={tr('显示','Display')}>
   <div className="form">{out?<label>{out.name}<Select value={out.current||''} disabled={busy} onChange={e=>void run('display',{output:out.name,mode:e.target.value},tr('分辨率已切换','Resolution changed'))}>{out.modes.map(m=><option key={m} value={m}>{m}</option>)}</Select></label>:<span className="muted">{st?.display.error?localizeError(st.display.error,tr('zh','en')==='en'):tr('未检测到显示器','No display detected')}</span>}</div>
  </Section>
  <Section title={tr('输入法','Input method')}>
   <div className="form">{st?.input.installed?(st.input.running?
    <label>{tr('当前','Active')}<Select value={st.input.active||''} disabled={busy} onChange={e=>void run('input',{name:e.target.value},tr('输入法已切换','Input method switched'))}>{[...new Set([st.input.active||'',...IME])].filter(Boolean).map(n=><option key={n} value={n}>{n}</option>)}</Select></label>:<span className="muted">{tr('输入法服务未运行','Input method service is not running')}</span>)
    :<span className="muted">{tr('本镜像未安装输入法','No input method installed')}</span>}</div>
   <p className="muted pad">{tr('在任意输入框中直接输入；切换快捷键 Ctrl+Space。','Type in any field; switch with Ctrl+Space.')}</p>
  </Section>
  <Section title={tr('网络','Network')}>
   {st?.network.installed?<>
    {st.network.devices.map(d=><div className="kv" key={d.device}><Icon name={d.state==='connected'?'pass':'circle-slash'}/><code>{d.device}</code><span>{d.type}</span><span className="muted">{d.state}{d.connection?' · '+d.connection:''}</span></div>)}
    {st.network.wifi.length>0&&<form className="form" onSubmit={e=>{e.preventDefault();if(ssid)void run('network',pw?{ssid,password:pw}:{ssid},tr('已发起连接','Connecting')).then(ok=>{if(ok)setPw('');});}}>
     <Select value={ssid} onChange={e=>setSsid(e.target.value)} aria-label="Wi-Fi"><option value="">{tr('选择 Wi-Fi','Choose Wi-Fi')}</option>{st.network.wifi.map(w=><option key={w.ssid} value={w.ssid}>{w.ssid}{w.secured?' 🔒':''}{w.signal!==null?' · '+w.signal+'%':''}</option>)}</Select>
     <Input type="password" autoComplete="off" value={pw} placeholder={tr('密码（开放网络留空）','Password (blank if open)')} onChange={e=>setPw(e.target.value)}/>
     <Button type="submit" variant="primary" disabled={busy||!ssid}>{tr('连接','Connect')}</Button></form>}
   </>:<p className="muted pad">{tr('本镜像未安装网络管理器','NetworkManager is not installed')}</p>}
  </Section>
  <Section title={tr('电源','Power')}><div className="form"><Button icon="debug-restart" onClick={()=>setPower('reboot')}>{tr('重启','Reboot')}</Button><Button icon="stop-circle" onClick={()=>setPower('poweroff')}>{tr('关机','Power off')}</Button></div></Section>
  {power&&<Dialog title={power==='poweroff'?tr('确认关机？','Power off now?'):tr('确认重启？','Reboot now?')} onClose={()=>setPower('')}
   actions={<><Button onClick={()=>setPower('')} autoFocus>{tr('取消','Cancel')}</Button><Button variant="primary" disabled={busy} onClick={()=>{const a=power;setPower('');void run('power',{action:a,confirm:'I-CONFIRM'},tr('已发送','Sent'));}}>{tr('确认','Confirm')}</Button></>}>
   <p>{tr('未保存的工作会丢失。','Unsaved work will be lost.')}</p></Dialog>}
 </div>;
}
