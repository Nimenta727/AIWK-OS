import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import {Activity,AlertTriangle,Cpu,FileCheck2,RefreshCw,RotateCcw,ShieldCheck} from 'lucide-react';

type ServiceInfo={service:string;scope:string;status:Record<string,string>};
type Services={services:ServiceInfo[]};
type KernelInfo={runningKernel:string;guestOnly:boolean;kernelDeploymentSupported:boolean;candidateOnly:boolean};
type AuditHealth={valid:boolean;events:number;lastHash:string};
type GuestFile={path:string;sha256:string;text:string};
type TaskCreated={task:{id:string};stages:Array<{state:string;approval:number}>};
// shared client: localized errors and one automatic CSRF refresh, like every other page
const guest=<T,>(path:string,options?:RequestInit):Promise<T>=>api<T>(path,options);

export default function GuestSystemConsole({csrf,english,onPlanCreated}:{
 csrf:string;english:boolean;onPlanCreated:()=>void;
}){
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
  try{
   const [s,k,a]=await Promise.all([
    guest<Services>('/guest/services'),
    guest<KernelInfo>('/guest/kernel'),
    guest<AuditHealth>('/audit/verify')
   ]);
   setServices(s);setKernel(k);setAudit(a);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setReady(true);}
 },[]);
 useEffect(()=>{void refresh();},[refresh]);
 const headers={'Content-Type':'application/json','X-AIWS-CSRF':csrf};
 const create=async(title:string,goal:string,tool:string,args:Record<string,string>)=>{
  if(!csrf||busy)return;
  setBusy(true);setError('');
  try{
   const saved=await guest<TaskCreated>('/tasks',{
    method:'POST',headers,
    body:JSON.stringify({title,goal,
     stages:[{key:'operation',label:title,tool,arguments:args,dependsOn:[]}]})
   });
   if(!saved.task.id||saved.stages.length!==1)throw new Error('Invalid guest task response');
   onPlanCreated();
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 const stageKernel=async()=>{
  if(!csrf||busy)return;
  setBusy(true);setError('');
  try{
   const pathname=candidatePath.trim();
   if(!pathname.endsWith('.fragment')||pathname.startsWith('/')||
     pathname.split('/').includes('..')||pathname.includes('\\')){
    throw new Error(tr('请输入工作区内的相对 .fragment 路径','Use a guest-relative .fragment path'));
   }
   const file=await guest<GuestFile>('/workspace/file?path='+encodeURIComponent(pathname));
   const title=tr('验证并暂存客户机内核配置候选','Stage guest kernel configuration candidate');
   const saved=await guest<TaskCreated>('/tasks',{method:'POST',headers,
    body:JSON.stringify({title,goal:tr('仅暂存和哈希验证，不部署内核','Stage and hash only; never install a kernel'),
     stages:[{key:'operation',label:title,tool:'kernel.stage',
      arguments:{path:pathname,expectedSha256:file.sha256},dependsOn:[]}]})
   });
   if(!saved.task.id)throw new Error('Missing task ID');
   onPlanCreated();
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 return <div className="aiws-os-stack aiws-os-system-console">
  {error&&<div className="aiws-os-error" role="alert">{error}</div>}
  <section className="aiws-os-card">
   <div className="aiws-os-studio-title"><h2><Activity size={19}/>{tr('客户机系统服务','Guest system services')}</h2>
    <button type="button" aria-label={tr('刷新','Refresh')} onClick={()=>void refresh()} disabled={!ready}>
     <RefreshCw size={16}/></button></div>
   <p className="aiws-os-muted">{tr('只显示 AIWS 客户机用户服务，不提供宿主机或任意 root/systemd 控制。',
    'Only AIWS guest user services are visible. No host or arbitrary root/systemd controls.')}</p>
   {services?.services.map(s=><div key={s.service} className="aiws-os-guest-service">
    <strong>{s.service}</strong><span>{s.status.ActiveState||'unknown'} / {s.status.SubState||'n/a'}</span>
   </div>)}
   {!services&&<p className="aiws-os-muted">{ready?tr('系统服务不可读取','Guest service status unavailable'):tr('检查服务中','Checking services')}</p>}
   <button type="button" className="aiws-os-primary" disabled={!csrf||busy}
    onClick={()=>void create(tr('重启客户机离线模型服务','Restart guest offline model service'),
      tr('仅系统用户级 aiws-local-model 服务，可审核后重启','Review before restarting guest-local model service'),
      'service.restart',{service:'aiws-local-model.service'})}>
    <RotateCcw size={16}/>{tr('创建服务重启审批任务','Request approved model-service restart')}</button>
  </section>
  <section className="aiws-os-card">
   <h2><Cpu size={18}/>{tr('客户机内核候选版本','Guest kernel candidates')}</h2>
   <dl><dt>{tr('正在运行的内核','Running kernel')}</dt><dd>{kernel?.runningKernel||tr('无法读取','unavailable')}</dd>
    <dt>{tr('内核直接部署','Live kernel deployment')}</dt><dd>{tr('禁用','Disabled')}</dd>
    <dt>{tr('真实 A/B 引导回滚','A/B boot rollback')}</dt><dd>{tr('尚未实现','Not implemented')}</dd></dl>
   <p className="aiws-os-muted">{tr('先在客户机文件管理器中新建 .fragment 配置文件。本步骤只建立不可变候选快照；需要任务审批。',
    'Create a .fragment file in guest files first. This stage only makes a hashed candidate snapshot after DAG approval.')}</p>
   <label>{tr('工作区内的候选配置文件路径','Guest project kernel fragment path')}
    <input value={candidatePath} onChange={e=>setCandidatePath(e.target.value)} maxLength={512}/></label>
   <button type="button" className="aiws-os-primary" disabled={!csrf||busy}
    onClick={()=>void stageKernel()}><FileCheck2 size={16}/>{tr('提交候选验证和暂存审批','Request reviewed staging task')}</button>
   <div className="aiws-os-divider-line"/>
   <label>{tr('已有候选 ID（32 位十六进制）','Existing candidate ID (32 hex characters)')}
    <input value={candidateId} onChange={e=>setCandidateId(e.target.value)} maxLength={32}/></label>
   <div className="aiws-os-studio-actions">
    <button type="button" disabled={!/^[a-f0-9]{32}$/.test(candidateId)||busy}
     onClick={()=>void create(tr('校验候选哈希','Verify candidate SHA'),'',
      'kernel.verify',{candidateId})}>{tr('验证哈希','Verify integrity')}</button>
    <button type="button" disabled={!/^[a-f0-9]{32}$/.test(candidateId)||busy}
     onClick={()=>void create(tr('生成候选恢复预案','Inspect candidate recovery'),
      tr('不修改 bootloader 或内核','No bootloader or kernel changes'),
      'kernel.recovery_plan',{candidateId})}>{tr('恢复预案','Recovery preflight')}</button>
    <button type="button" disabled={!/^[a-f0-9]{32}$/.test(candidateId)||busy}
     onClick={()=>void create(tr('撤销未部署候选','Abandon undeployed kernel candidate'),
      tr('需要审批，保留快照；不更改正在运行的内核','Approval required; snapshot retained, live kernel unchanged'),
      'kernel.abandon',{candidateId})}>{tr('申请撤销候选','Request abandon')}</button>
   </div>
  </section>
  <section className="aiws-os-card">
   <h2><ShieldCheck size={18}/>{tr('持久审计健康状况','Durable audit integrity')}</h2>
   <div className="aiws-os-guest-service">
    <strong>{audit?.valid?tr('审计哈希链校验通过','Audit chain valid'):tr('审计链未校验或存在异常','Audit unavailable or invalid')}</strong>
    <span>{audit?.events??'–'} {tr('条记录','events')}</span>
   </div>
   {!audit?.valid&&<p className="aiws-os-error"><AlertTriangle size={15}/>{tr('请勿继续执行高权限任务；先排查审计状态。','Do not perform privileged operations until audit state is reviewed.')}</p>}
   <p className="aiws-os-muted">{tr('本校验能发现简单篡改，但不能抵御已控制客户机 root 的恶意程序。',
    'Hash checks detect simple modifications, not a hostile guest-root process.')}</p>
  </section>
 </div>;
}
