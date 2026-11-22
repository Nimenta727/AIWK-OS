import {useCallback,useEffect,useState} from 'react';
import {Button,Check,Icon,Input,Notice,Section,Select,Progress} from '../ui/kit';
import {formatTokens} from '../model/observatory.mjs';
import {api} from '../os/api';
import {msg,useAction} from './common';
import type {Tr} from './common';
import type {ObservatoryData} from '../os/useObservatoryData';

const READ=['workspace.tree','file.read','file.stat','code.search','doc.text','git.inspect','ext.rg','ext.jq','ext.gitlog','tools.list'];
const INTERNAL=['plan.propose','plan.update','agent.spawn'];
const EDIT=['file.replace','file.mkdir','file.copy','file.move'];
const DELETE=['file.trash','file.restore'];
type KeyStatus={configured:boolean;source:string|null;last4:string|null;problem:string|null};
const EFFORT_LABEL=(tr:Tr)=>({low:tr('低（快、省）','low (fast, cheap)'),high:tr('高（默认）','high (default)'),max:tr('最高（慢、贵）','max (slow, costly)')} as Record<string,string>);

/** DeepSeek key panel: the key can be set or cleared here but is never shown again (only its last 4 characters). */
function KeyPanel({tr,onChange}:{tr:Tr;onChange:()=>void}){
 const [st,setSt]=useState<KeyStatus|null>(null);
 const [value,setValue]=useState('');
 const act=useAction(async()=>{await load();onChange();});
 const load=useCallback(async()=>{try{setSt(await api<KeyStatus>('/cloud/key'));}catch{/* shown by act.error on actions */}},[]);
 useEffect(()=>{void load();},[load]);
 return <Section title={tr('DeepSeek API 密钥','DeepSeek API key')}>
  <div className="form col">
   {act.error&&<Notice tone="err">{act.error}</Notice>}
   {st?.problem&&<Notice tone="err">{st.problem}</Notice>}
   {st?.configured?<div className="kv"><Icon name="pass"/><span>{tr('已配置','Configured')} · …{st.last4} · {st.source==='env'?tr('来自环境变量','from the environment'):tr('来自私有文件','from a private file')}</span>
     {st.source==='file'&&<Button variant="ghost" disabled={act.busy} onClick={()=>void act.post('/cloud/key',{clear:true})}>{tr('清除','Clear')}</Button>}</div>
    :<form className="form" onSubmit={e=>{e.preventDefault();if(value)void act.post('/cloud/key',{key:value}).then(ok=>{if(ok)setValue('');});}}>
     <Input type="password" autoComplete="off" value={value} placeholder={tr('粘贴 API 密钥','Paste your API key')} onChange={e=>setValue(e.target.value)} aria-label={tr('API 密钥','API key')}/>
     <Button type="submit" variant="primary" disabled={act.busy||!value}>{tr('保存','Save')}</Button></form>}
   <p className="muted">{tr('密钥只保存在你账户下的私有文件（权限 600），不会写入工作区、任务数据或日志；运行时通过管道交给运行器，不进命令行和环境变量。','The key is stored only in a private file (mode 600) in your account: never in the workspace, task data or logs. It is handed to the runner through a pipe, not the command line or environment.')}</p>
  </div></Section>;
}

/** Grant one mandate (tools, budget, time, actions that need approval), then start the cloud run inside it. */
export default function Build({tr,english,data}:{tr:Tr;english:boolean;data:ObservatoryData}){
 const {builder,reload}=data;
 const act=useAction(reload);
 const [f,setF]=useState({provider:'deepseek',projectDir:'',prompt:'',inputK:'400',outputK:'100',minutes:'30',turns:'40',tools:'Read,Edit,Write,Bash(npm test)',del:true,install:true,push:true,
  model:'deepseek-flash',thinking:true,effort:'high',planApproval:true,edit:true,remove:false,askWrite:false});
 const set=(k:string,v:string|boolean)=>setF(x=>({...x,[k]:v}));
 const native=f.provider==='deepseek';
 const start=async()=>{
  if(!f.prompt.trim()||!f.projectDir.trim())return;
  try{
   let body:Record<string,unknown>;
   if(native){
    const tools=[...READ,...INTERNAL,...(f.edit?EDIT:[]),...(f.remove?DELETE:[])];
    body={provider:'deepseek',projectDir:f.projectDir.trim(),allowedTools:tools,model:f.model,thinking:f.thinking,effort:f.effort,planApproval:f.planApproval,maxTurns:Number(f.turns),
     wallClockMinutes:Number(f.minutes),tokenBudget:{input:Number(f.inputK)*1000,output:Number(f.outputK)*1000},
     needApprovalFor:['network','shell','outside-project',...(f.remove?['delete']:[]),...(f.askWrite?['write']:[])]};
   }else{
    const approvals=['network','shell','outside-project',...(f.del?['delete']:[]),...(f.install?['install-dependency']:[]),...(f.push?['git-push']:[])];
    body={provider:f.provider,projectDir:f.projectDir.trim(),allowedTools:f.tools.split(',').map(x=>x.trim()).filter(Boolean),permissionMode:'default',maxTurns:Number(f.turns),
     wallClockMinutes:Number(f.minutes),tokenBudget:{input:Number(f.inputK)*1000,output:Number(f.outputK)*1000},needApprovalFor:approvals};
   }
   const m=await api<{id:string}>('/builder/mandates',{method:'POST',body:JSON.stringify(body)});
   if(await act.post('/builder/runs',{mandateId:m.id,prompt:f.prompt,language:english?'en':'zh'}))set('prompt','');
  }catch(e){act.setError(msg(e));}
 };
 if(!builder)return <p className="muted pad">…</p>;
 const run=builder.status.active;
 const ds=builder.providers.deepseek;
 const blocked=native&&!ds?.keyConfigured;
 const providerLabel=(k:string,v:{installed:boolean})=>k==='deepseek'?'DeepSeek ('+(v.installed?tr('密钥已配置','key set'):tr('未配置密钥','no key'))+')':k+(v.installed?'':tr('（本机未安装）',' (not installed)'));
 return <div className="build selectable">
  <header><h2>{tr('构建','Build')}</h2><span className="muted">{tr('云端模型在你的授权范围内工作','the cloud model works inside your mandate')}</span></header>
  {act.error&&<Notice tone="err">{act.error}</Notice>}
  {!builder.enabled?<Notice tone="warn">{tr('构建通道默认关闭。要启用，请在 ~/.config/aiws/builder.json 写入 {"enabled": true}。默认不隔离，运行器以当前用户权限运行；专用用户隔离见 os/builder/README.md。','The builder is off by default. Enable it with {"enabled": true} in ~/.config/aiws/builder.json. By default there is no isolation; see os/builder/README.md for the dedicated user.')}</Notice>:<>
   <Notice tone={builder.status.isolation?.mode==='user'?'ok':'warn'}>{builder.status.isolation?.mode==='user'?tr('隔离：专用用户 ','Isolation: dedicated user ')+builder.status.isolation.user+tr('，只能经域名白名单代理联网','; network only through the domain-allowlist proxy'):tr('隔离：无。运行器以当前用户权限运行。','Isolation: none. The runner runs with your own privileges.')}</Notice>
   {builder.lastResult&&<Section title={tr('最近一次运行的结果','Result of the latest run')}><pre className="result selectable">{builder.lastResult.text}</pre></Section>}
   {run&&<Section title={tr('正在运行','Running')}><div className="inbox"><div><strong><Icon name="sync" spin/> {run.state}</strong><div className="muted">{tr('轮次','turns')} {run.turns} · {tr('已用','used')} {formatTokens(run.usedInput)}/{formatTokens(run.usedOutput)}</div></div>
    <Button icon="debug-stop" disabled={act.busy} onClick={()=>void act.post('/builder/runs/'+run.runId+'/stop')}>{tr('停止','Stop')}</Button></div></Section>}
   {native&&<KeyPanel tr={tr} onChange={()=>void reload()}/>}
   {!run&&<Section title={tr('授权并开始','Grant & start')}><div className="form col">
    <label>{tr('云端模型','Provider')}<Select value={f.provider} onChange={e=>set('provider',e.target.value)}>{Object.entries(builder.providers).map(([k,v])=><option key={k} value={k}>{providerLabel(k,v)}</option>)}</Select></label>
    {native&&<div className="grid4"><label>{tr('模型','Model')}<Select value={f.model} onChange={e=>set('model',e.target.value)}>{(ds?.models||['deepseek-flash']).map(m=><option key={m} value={m}>{m}</option>)}</Select></label>
     <label>{tr('推理强度','Reasoning effort')}<Select value={f.effort} disabled={!f.thinking} onChange={e=>set('effort',e.target.value)}>{Object.entries(EFFORT_LABEL(tr)).map(([k,v])=><option key={k} value={k}>{v}</option>)}</Select></label>
     <Check label={tr('思考模式','Thinking mode')} checked={f.thinking} onChange={v=>set('thinking',v)}/></div>}
    <label>{tr('项目文件夹（工作区内的子文件夹）','Project folder (a sub-folder of the workspace)')}<Input value={f.projectDir} placeholder="app" onChange={e=>set('projectDir',e.target.value)}/></label>
    <label>{tr('要构建什么','What to build')}<textarea className="k-input" rows={4} maxLength={4000} value={f.prompt} onChange={e=>set('prompt',e.target.value)}/></label>
    <div className="grid4"><label>{tr('输入预算 (k)','Input budget (k)')}<Input value={f.inputK} onChange={e=>set('inputK',e.target.value)}/></label><label>{tr('输出预算 (k)','Output budget (k)')}<Input value={f.outputK} onChange={e=>set('outputK',e.target.value)}/></label>
     <label>{tr('最长分钟','Max minutes')}<Input value={f.minutes} onChange={e=>set('minutes',e.target.value)}/></label><label>{tr('最多调用次数','Max model calls')}<Input value={f.turns} onChange={e=>set('turns',e.target.value)}/></label></div>
    {native?<fieldset><legend>{tr('它可以做什么','What it may do')}</legend>
      <Check label={tr('读取、搜索、查看变更（始终允许）','Read, search, inspect changes (always)')} checked disabled onChange={()=>undefined}/>
      <Check label={tr('创建/修改/复制/移动文件','Create / edit / copy / move files')} checked={f.edit} onChange={v=>set('edit',v)}/>
      <Check label={tr('删除（进回收站，每次都要你批准）','Delete (to trash, always needs your approval)')} checked={f.remove} onChange={v=>set('remove',v)}/>
      <Check label={tr('每次写入文件前先问我','Ask me before every file write')} checked={f.askWrite} disabled={!f.edit} onChange={v=>set('askWrite',v)}/>
      <Check label={tr('动手前先给我看计划，等我批准','Show me a plan first and wait for my approval')} checked={f.planApproval} onChange={v=>set('planApproval',v)}/>
      <p className="muted">{tr('这个运行器没有 shell，也不能联网访问别的地址；它只能用上面的文件工具，并被限制在项目文件夹内。','This runner has no shell and cannot reach any other address; it only has the file tools above, confined to the project folder.')}</p></fieldset>
     :<><label>{tr('允许的工具（逗号分隔；不能授予不受限的 Bash）','Allowed tools (comma separated; unrestricted Bash can never be granted)')}<Input value={f.tools} onChange={e=>set('tools',e.target.value)}/></label>
      <fieldset><legend>{tr('下列操作发生时暂停并问你','Pause and ask me before')}</legend><Check label={tr('删除','delete')} checked={f.del} onChange={v=>set('del',v)}/><Check label={tr('安装依赖','install dependencies')} checked={f.install} onChange={v=>set('install',v)}/><Check label="git push" checked={f.push} onChange={v=>set('push',v)}/>
       <p className="muted">{tr('联网、shell、越出项目文件夹：始终需要批准，无法关闭。','Network, shell and leaving the project folder always need approval and cannot be switched off.')}</p></fieldset></>}
    <div><Button variant="primary" icon="play" disabled={act.busy||blocked||!f.prompt.trim()||!f.projectDir.trim()} onClick={()=>void start()}>{tr('授权并开始','Grant and start')}</Button>
     {blocked&&<span className="muted"> {tr('先在上面保存 API 密钥','Save the API key above first')}</span>}</div></div></Section>}
   <Section title={tr('有效授权','Active mandates')} count={builder.mandates.length}>
    {builder.mandates.slice(0,5).map(m=><div className="kv" key={m.id}><Icon name="key"/><span>{m.provider}{m.model?' · '+m.model:''} · {m.projectDir}</span><div className="grow"><Progress value={m.used.input+m.used.output} max={m.tokenBudget.input+m.tokenBudget.output}/></div>
     <span className="muted">{formatTokens(m.used.input+m.used.output)}/{formatTokens(m.tokenBudget.input+m.tokenBudget.output)}</span><Button variant="ghost" disabled={act.busy} onClick={()=>void act.post('/builder/mandates/'+m.id+'/revoke')}>{tr('撤销','Revoke')}</Button></div>)}
    {!builder.mandates.length&&<p className="muted pad">{tr('没有有效授权。','No active mandates.')}</p>}</Section></>}
 </div>;
}
