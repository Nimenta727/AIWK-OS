import {useState} from 'react';
import {Button,Check,Icon,Input,Notice,Section,Select,Progress} from '../ui/kit';
import {formatTokens} from '../model/observatory.mjs';
import {useAction} from './common';
import type {Tr} from './common';
import type {ObservatoryData} from '../os/useObservatoryData';

/** Grant one mandate (tools, budget, time, actions that need approval), then start the cloud CLI inside it. */
export default function Build({tr,data}:{tr:Tr;data:ObservatoryData}){
 const {builder,reload}=data;
 const act=useAction(reload);
 const [f,setF]=useState({provider:'claude',projectDir:'',prompt:'',inputK:'200',outputK:'60',minutes:'30',turns:'30',tools:'Read,Edit,Write,Bash(npm test)',del:true,install:true,push:true});
 const set=(k:string,v:string|boolean)=>setF(x=>({...x,[k]:v}));
 const start=async()=>{
  if(!f.prompt.trim()||!f.projectDir.trim())return;
  const {api}=await import('../os/api');
  try{
   const approvals=['network','shell','outside-project',...(f.del?['delete']:[]),...(f.install?['install-dependency']:[]),...(f.push?['git-push']:[])];
   const m=await api<{id:string}>('/builder/mandates',{method:'POST',body:JSON.stringify({provider:f.provider,projectDir:f.projectDir.trim(),allowedTools:f.tools.split(',').map(x=>x.trim()).filter(Boolean),
    permissionMode:'default',maxTurns:Number(f.turns),wallClockMinutes:Number(f.minutes),tokenBudget:{input:Number(f.inputK)*1000,output:Number(f.outputK)*1000},needApprovalFor:approvals})});
   if(await act.post('/builder/runs',{mandateId:m.id,prompt:f.prompt}))set('prompt','');
  }catch(e){act.setError(String(e instanceof Error?e.message:e));}
 };
 if(!builder)return <p className="muted pad">…</p>;
 const run=builder.status.active;
 return <div className="build selectable">
  <header><h2>{tr('构建','Build')}</h2><span className="muted">{tr('官方 CLI，在你的授权范围内工作','official CLI, inside your mandate')}</span></header>
  {act.error&&<Notice tone="err">{act.error}</Notice>}
  {!builder.enabled?<Notice tone="warn">{tr('构建通道默认关闭。要启用，请在 ~/.config/aiws/builder.json 写入 {"enabled": true}。默认不隔离，CLI 以当前用户权限运行；专用用户隔离见 os/builder/README.md。','The builder is off by default. Enable it with {"enabled": true} in ~/.config/aiws/builder.json. By default there is no isolation; see os/builder/README.md for the dedicated user.')}</Notice>:<>
   <Notice tone={builder.status.isolation?.mode==='user'?'ok':'warn'}>{builder.status.isolation?.mode==='user'?tr('隔离：专用用户 ','Isolation: dedicated user ')+builder.status.isolation.user+tr('，只能经域名白名单代理联网','; network only through the domain-allowlist proxy'):tr('隔离：无。CLI 以当前用户权限运行。','Isolation: none. The CLI runs with your own privileges.')}</Notice>
   <p className="muted pad">{Object.entries(builder.providers).map(([k,v])=>k+': '+(v.installed?tr('已安装','installed'):tr('本机未安装','not installed'))).join(' · ')}</p>
   {run&&<Section title={tr('正在运行','Running')}><div className="inbox"><div><strong><Icon name="sync" spin/> {run.state}</strong><div className="muted">{tr('轮次','turns')} {run.turns} · {tr('已用','used')} {formatTokens(run.usedInput)}/{formatTokens(run.usedOutput)}</div></div>
    <Button icon="debug-stop" disabled={act.busy} onClick={()=>void act.post('/builder/runs/'+run.runId+'/stop')}>{tr('停止','Stop')}</Button></div></Section>}
   {!run&&<Section title={tr('授权并开始','Grant & start')}><div className="form col">
    <label>{tr('云端模型（官方 CLI）','Provider (official CLI)')}<Select value={f.provider} onChange={e=>set('provider',e.target.value)}>{Object.entries(builder.providers).map(([k,v])=><option key={k} value={k}>{k}{v.installed?'':tr('（本机未安装）',' (not installed)')}</option>)}</Select></label>
    <label>{tr('项目文件夹（工作区内的子文件夹）','Project folder (a sub-folder of the workspace)')}<Input value={f.projectDir} placeholder="app" onChange={e=>set('projectDir',e.target.value)}/></label>
    <label>{tr('要构建什么','What to build')}<textarea className="k-input" rows={4} maxLength={4000} value={f.prompt} onChange={e=>set('prompt',e.target.value)}/></label>
    <div className="grid4"><label>{tr('输入预算 (k)','Input budget (k)')}<Input value={f.inputK} onChange={e=>set('inputK',e.target.value)}/></label><label>{tr('输出预算 (k)','Output budget (k)')}<Input value={f.outputK} onChange={e=>set('outputK',e.target.value)}/></label>
     <label>{tr('最长分钟','Max minutes')}<Input value={f.minutes} onChange={e=>set('minutes',e.target.value)}/></label><label>{tr('最多轮次','Max turns')}<Input value={f.turns} onChange={e=>set('turns',e.target.value)}/></label></div>
    <label>{tr('允许的工具（逗号分隔；不能授予不受限的 Bash）','Allowed tools (comma separated; unrestricted Bash can never be granted)')}<Input value={f.tools} onChange={e=>set('tools',e.target.value)}/></label>
    <fieldset><legend>{tr('下列操作发生时暂停并问你','Pause and ask me before')}</legend><Check label={tr('删除','delete')} checked={f.del} onChange={v=>set('del',v)}/><Check label={tr('安装依赖','install dependencies')} checked={f.install} onChange={v=>set('install',v)}/><Check label="git push" checked={f.push} onChange={v=>set('push',v)}/>
     <p className="muted">{tr('联网、shell、越出项目文件夹：始终需要批准，无法关闭。','Network, shell and leaving the project folder always need approval and cannot be switched off.')}</p></fieldset>
    <div><Button variant="primary" icon="play" disabled={act.busy||!f.prompt.trim()||!f.projectDir.trim()} onClick={()=>void start()}>{tr('授权并开始','Grant and start')}</Button></div></div></Section>}
   <Section title={tr('有效授权','Active mandates')} count={builder.mandates.length}>
    {builder.mandates.slice(0,5).map(m=><div className="kv" key={m.id}><Icon name="key"/><span>{m.provider} · {m.projectDir}</span><div className="grow"><Progress value={m.used.input+m.used.output} max={m.tokenBudget.input+m.tokenBudget.output}/></div>
     <span className="muted">{formatTokens(m.used.input+m.used.output)}/{formatTokens(m.tokenBudget.input+m.tokenBudget.output)}</span><Button variant="ghost" disabled={act.busy} onClick={()=>void act.post('/builder/mandates/'+m.id+'/revoke')}>{tr('撤销','Revoke')}</Button></div>)}
    {!builder.mandates.length&&<p className="muted pad">{tr('没有有效授权。','No active mandates.')}</p>}</Section></>}
 </div>;
}
