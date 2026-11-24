import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import {Button,Icon,IconButton,Input,Notice,Section} from '../ui/kit';

type ServiceInfo={service:string;scope:string;status:Record<string,string>};
type Services={services:ServiceInfo[]};
type KernelInfo={runningKernel:string;guestOnly:boolean;kernelDeploymentSupported:boolean;candidateOnly:boolean};
type AuditHealth={valid:boolean;events:number;lastHash:string};
type GuestFile={path:string;sha256:string;text:string};
type TaskCreated={task:{id:string};stages:Array<{state:string;approval:number}>};
const errText=(e:unknown)=>e instanceof Error?e.message:String(e);
const HEX32=/^[a-f0-9]{32}$/;

/** Guest services, kernel candidates and audit health. Read-only views; every action only creates a reviewed DAG task
 *  and opens the plan review page. `.aiws-os-system-console` is a hook of the in-image GUI smoke test. */
export default function GuestSystemConsole({english,onPlanCreated}:{csrf?:string;english:boolean;onPlanCreated:()=>void}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [services,setServices]=useState<Services|null>(null);
 const [kernel,setKernel]=useState<KernelInfo|null>(null);
 const [audit,setAudit]=useState<AuditHealth|null>(null);
 const [candidatePath,setCandidatePath]=useState('aiws-kernel.fragment');
 const [candidateId,setCandidateId]=useState('');
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [ready,setReady]=useState(false);
 const refresh=useCallback(async()=>{
  setError('');setReady(false);
  // each part loads on its own: one unreadable part must not blank the others
  const [s,k,a]=await Promise.allSettled([api<Services>('/guest/services'),api<KernelInfo>('/guest/kernel'),api<AuditHealth>('/audit/verify')]);
  setServices(s.status==='fulfilled'?s.value:null);setKernel(k.status==='fulfilled'?k.value:null);setAudit(a.status==='fulfilled'?a.value:null);
  const failed=[s,k,a].find(x=>x.status==='rejected') as PromiseRejectedResult|undefined;
  if(failed)setError(errText(failed.reason));
  setReady(true);
 },[]);
 useEffect(()=>{void refresh();},[refresh]);
 const create=async(title:string,goal:string,tool:string,args:Record<string,string>)=>{
  if(busy)return;
  setBusy(true);setError('');
  try{
   const saved=await api<TaskCreated>('/tasks',{method:'POST',
    body:JSON.stringify({title,goal,stages:[{key:'operation',label:title,tool,arguments:args,dependsOn:[]}]})});
   if(!saved.task.id||saved.stages.length!==1)throw new Error('Invalid guest task response');
   onPlanCreated();
  }catch(e){setError(errText(e));}
  finally{setBusy(false);}
 };
 const stageKernel=async()=>{
  if(busy)return;
  setBusy(true);setError('');
  try{
   const pathname=candidatePath.trim();
   if(!pathname.endsWith('.fragment')||pathname.startsWith('/')||pathname.split('/').includes('..')||pathname.includes('\\'))
    throw new Error(tr('请输入工作区内的相对 .fragment 路径','Use a guest-relative .fragment path'));
   const file=await api<GuestFile>('/workspace/file?path='+encodeURIComponent(pathname));
   const title=tr('验证并暂存客户机内核配置候选','Stage guest kernel configuration candidate');
   const saved=await api<TaskCreated>('/tasks',{method:'POST',
    body:JSON.stringify({title,goal:tr('仅暂存和哈希验证，不部署内核','Stage and hash only; never install a kernel'),
     stages:[{key:'operation',label:title,tool:'kernel.stage',arguments:{path:pathname,expectedSha256:file.sha256},dependsOn:[]}]})});
   if(!saved.task.id)throw new Error('Missing task ID');
   onPlanCreated();
  }catch(e){setError(errText(e));}
  finally{setBusy(false);}
 };
 const idOk=HEX32.test(candidateId);
 const needId=idOk?undefined:tr('先填入 32 位候选 ID','Enter a 32-character candidate ID first');
 return <div className="gp aiws-os-system-console">
  <header><h2>{tr('系统服务与内核','Services & kernel')}</h2>
   <IconButton icon="refresh" label={tr('刷新','Refresh')} onClick={()=>void refresh()} disabled={!ready}/></header>
  {error&&<Notice tone="err">{error}</Notice>}
  <Section title={tr('客户机系统服务','Guest system services')}>
   <p className="muted pad">{tr('只显示 AIWS 客户机用户服务，不提供宿主机或任意 root/systemd 控制。','Only AIWS guest user services are visible. No host or arbitrary root/systemd controls.')}</p>
   {services?.services.map(s=>{const on=s.status.ActiveState==='active';return <div key={s.service} className="kv">
    <Icon name={on?'pass':'circle-slash'}/><code>{s.service}</code><span className="muted">{s.status.ActiveState||tr('未知','unknown')} / {s.status.SubState||'–'}</span></div>;})}
   {!services&&<p className="muted pad">{ready?tr('系统服务不可读取','Guest service status unavailable'):tr('检查服务中…','Checking services…')}</p>}
   <div className="form"><Button icon="debug-restart" disabled={busy}
    onClick={()=>void create(tr('重启客户机离线模型服务','Restart guest offline model service'),
     tr('仅系统用户级 aiws-local-model 服务，可审核后重启','Review before restarting guest-local model service'),
     'service.restart',{service:'aiws-local-model.service'})}>{tr('创建服务重启审批任务','Request approved model-service restart')}</Button></div>
  </Section>
  <Section title={tr('客户机内核候选版本','Guest kernel candidates')}>
   <div className="kv"><span className="gp-k">{tr('正在运行的内核','Running kernel')}</span><code>{kernel?.runningKernel||tr('无法读取','unavailable')}</code></div>
   <div className="kv"><span className="gp-k">{tr('内核直接部署','Live kernel deployment')}</span><span>{tr('禁用','Disabled')}</span></div>
   <div className="kv"><span className="gp-k">{tr('真实 A/B 引导回滚','A/B boot rollback')}</span><span>{tr('尚未实现','Not implemented')}</span></div>
   <p className="muted pad">{tr('先在 AI 文件管理里新建 .fragment 配置文件。这一步只建立不可变的候选快照，并且要你审批。',
    'Create a .fragment file in AI files first. This only makes a hashed candidate snapshot, after your approval.')}</p>
   <div className="form"><label>{tr('工作区内的候选配置文件路径','Guest project kernel fragment path')}
    <Input value={candidatePath} onChange={e=>setCandidatePath(e.target.value)} maxLength={512}/></label>
    <Button variant="primary" icon="file-code" disabled={busy} onClick={()=>void stageKernel()}>{tr('提交候选验证和暂存审批','Request reviewed staging task')}</Button></div>
   <div className="form"><label>{tr('已有候选 ID（32 位十六进制）','Existing candidate ID (32 hex characters)')}
    <Input value={candidateId} onChange={e=>setCandidateId(e.target.value)} maxLength={32}/></label></div>
   <div className="form">
    <Button disabled={!idOk||busy} title={needId} onClick={()=>void create(tr('校验候选哈希','Verify candidate SHA'),'','kernel.verify',{candidateId})}>{tr('验证哈希','Verify integrity')}</Button>
    <Button disabled={!idOk||busy} title={needId} onClick={()=>void create(tr('生成候选恢复预案','Inspect candidate recovery'),tr('不修改 bootloader 或内核','No bootloader or kernel changes'),'kernel.recovery_plan',{candidateId})}>{tr('恢复预案','Recovery preflight')}</Button>
    <Button disabled={!idOk||busy} title={needId} onClick={()=>void create(tr('撤销未部署候选','Abandon undeployed kernel candidate'),
     tr('需要审批，保留快照；不更改正在运行的内核','Approval required; snapshot retained, live kernel unchanged'),'kernel.abandon',{candidateId})}>{tr('申请撤销候选','Request abandon')}</Button>
   </div>
  </Section>
  <Section title={tr('持久审计健康状况','Durable audit integrity')}>
   <div className="kv"><Icon name={audit?.valid?'pass':'warning'}/><strong>{audit?.valid?tr('审计哈希链校验通过','Audit chain valid'):tr('审计链未校验或存在异常','Audit unavailable or invalid')}</strong>
    <span className="muted">{audit?.events??'–'} {tr('条记录','events')}</span></div>
   {!audit?.valid&&ready&&<Notice tone="warn">{tr('请勿继续执行高权限任务；先排查审计状态。','Do not perform privileged operations until audit state is reviewed.')}</Notice>}
   <p className="muted pad">{tr('本校验能发现简单篡改，但不能抵御已控制客户机 root 的恶意程序。','Hash checks detect simple modifications, not a hostile guest-root process.')}</p>
  </Section>
 </div>;
}
