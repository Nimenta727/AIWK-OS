import {useCallback,useEffect,useState} from 'react';
import {Monitor,Keyboard,Wifi,Power,RefreshCw} from 'lucide-react';
import {api} from './api';

type Output={name:string;modes:string[];current:string|null};
type Wifi={ssid:string;signal:number|null;secured:boolean;inUse:boolean};
type Status={
 display:{outputs?:Output[];error?:string};
 input:{installed:boolean;running:boolean;active:string|null;composing?:boolean};
 network:{installed:boolean;devices:Array<{device:string;type:string;state:string;connection:string|null}>;wifi:Wifi[]};
};
const IME_CHOICES=['keyboard-us','pinyin'];

/** Everything a desktop panel used to do. Each control calls one fixed, validated endpoint; results are re-read from the system. */
export default function SystemControls({english}:{english:boolean}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [st,setSt]=useState<Status|null>(null);
 const [note,setNote]=useState('');
 const [busy,setBusy]=useState(false);
 const [ssid,setSsid]=useState('');
 const [password,setPassword]=useState('');
 const [armed,setArmed]=useState<''|'poweroff'|'reboot'>('');
 const load=useCallback(async()=>{try{setSt(await api<Status>('/system'));}catch(e){setNote(String(e instanceof Error?e.message:e));}},[]);
 useEffect(()=>{void load();},[load]);
 const run=async(kind:string,body:object,done:string)=>{
  if(busy)return;setBusy(true);setNote('');
  try{await api('/system/'+kind,{method:'POST',body:JSON.stringify(body)});setNote(done);await load();}
  catch(e){setNote(String(e instanceof Error?e.message:e));}
  finally{setBusy(false);}
 };
 const out=st?.display.outputs?.[0];
 return <div className="aiws-sc">
  <header><h2>{tr('系统','System')}</h2><button type="button" onClick={()=>void load()} title={tr('刷新','Refresh')}><RefreshCw size={14}/></button></header>
  {note&&<div className="aiws-sc-note" role="status">{note}</div>}
  <section><h3><Monitor size={15}/>{tr('显示','Display')}</h3>
   {out?<label>{out.name}
    <select value={out.current||''} disabled={busy} onChange={e=>void run('display',{output:out.name,mode:e.target.value},tr('分辨率已切换','Resolution changed'))}>
     {out.modes.map(m=><option key={m} value={m}>{m}</option>)}</select></label>
    :<p>{st?.display.error||tr('未检测到显示器','No display detected')}</p>}</section>
  <section><h3><Keyboard size={15}/>{tr('输入法','Input method')}</h3>
   {st?.input.installed?(st.input.running?
    <label>{tr('当前','Active')}: {st.input.active||'—'}
     <select value={st.input.active||''} disabled={busy} onChange={e=>void run('input',{name:e.target.value},tr('输入法已切换','Input method switched'))}>
      {[...new Set([st.input.active||'',...IME_CHOICES])].filter(Boolean).map(n=><option key={n} value={n}>{n}</option>)}</select></label>
    :<p>{tr('输入法服务未运行','Input method service is not running')}</p>)
   :<p>{tr('本镜像未安装输入法','No input method installed')}</p>}
   <p className="aiws-sc-hint">{tr('在任意输入框中可直接输入；切换快捷键 Ctrl+Space。','Type in any field; switch with Ctrl+Space.')}</p></section>
  <section><h3><Wifi size={15}/>{tr('网络','Network')}</h3>
   {st?.network.installed?<>
    <ul>{st.network.devices.map(d=><li key={d.device}>{d.device} · {d.type} · {d.state}{d.connection?' · '+d.connection:''}</li>)}</ul>
    {st.network.wifi.length>0&&<form onSubmit={e=>{e.preventDefault();if(ssid)void run('network',password?{ssid,password}:{ssid},tr('已发起连接','Connecting')).then(()=>setPassword(''));}}>
     <select value={ssid} onChange={e=>setSsid(e.target.value)}><option value="">{tr('选择 Wi-Fi','Choose Wi-Fi')}</option>
      {st.network.wifi.map(w=><option key={w.ssid} value={w.ssid}>{w.ssid}{w.secured?' 🔒':''}{w.signal!==null?' · '+w.signal+'%':''}</option>)}</select>
     <input type="password" autoComplete="off" value={password} placeholder={tr('密码（开放网络留空）','Password (blank if open)')} onChange={e=>setPassword(e.target.value)}/>
     <button type="submit" disabled={busy||!ssid}>{tr('连接','Connect')}</button></form>}
   </>:<p>{tr('本镜像未安装网络管理器','NetworkManager is not installed')}</p>}</section>
  <section><h3><Power size={15}/>{tr('电源','Power')}</h3>
   {armed?<div className="aiws-sc-confirm"><span>{armed==='poweroff'?tr('确认关机？','Power off now?'):tr('确认重启？','Reboot now?')}</span>
     <button type="button" disabled={busy} onClick={()=>void run('power',{action:armed,confirm:'I-CONFIRM'},tr('已发送','Sent')).then(()=>setArmed(''))}>{tr('确认','Confirm')}</button>
     <button type="button" onClick={()=>setArmed('')}>{tr('取消','Cancel')}</button></div>
    :<div><button type="button" onClick={()=>setArmed('poweroff')}>{tr('关机','Power off')}</button> <button type="button" onClick={()=>setArmed('reboot')}>{tr('重启','Reboot')}</button></div>}</section>
 </div>;
}
