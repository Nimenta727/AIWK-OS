export type TokenUsage = { input: number|null; output:number|null; cachedInput:number|null; source:string; isMeasured?:boolean };
export type TraceEvent = { at:string; stageId:string; kind:string; summary:string };
export type GitObservedFile = {path:string;status:string;signature:string};
export type GitCheckpoint = {capturedAt:string;head:string;files:GitObservedFile[];partial:boolean;problem:string};
export type ProjectFile = {path:string;isDirectory:boolean;status:string;size:number|null;isLink:boolean};
export type ProjectOverview = {workspace:string;rootName:string;branch:string;head:string;files:ProjectFile[];changedCount:number;truncated:boolean;notices:string[]};
export type FileReview = {path:string;status:string;diff:string;truncated:boolean;isPreview:boolean;note:string};
export type StageChangeReport = {stageId:string;stageTitle:string;fromHead:string;toHead:string;headChanged:boolean;files:{path:string;kind:string;before:string;after:string}[];committedFiles:string[];partial:boolean;notice:string;startedAt:string|null;completedAt:string|null};
export type WorkStep = { gitBefore:GitCheckpoint|null;gitAfter:GitCheckpoint|null; id:string; title:string; agent:'ClaudeCode'|'Codex'|'Manual'; status:'Pending'|'Running'|'Completed'|'Failed'|'Interrupted'; approvalGranted:boolean; requiresApproval:boolean; instructions:string; result:string; usage:TokenUsage; lastPromptFingerprint:string; startedAt:string|null; completedAt:string|null };
export type WorkTask = { id:string; title:string; workspace:string; createdAt:string; steps:WorkStep[]; requestEvents:TraceEvent[]; completedCount:number };
export type Snapshot = { version:string; tasks:WorkTask[]; agents:Record<string,boolean>; limitations:string[] };
type Pending = { resolve:(x:unknown)=>void; reject:(e:Error)=>void };
type Message = {id:number;action:string;payload:Record<string,unknown>};
declare global { interface Window { chrome?:{webview?:{postMessage:(x:string)=>void;addEventListener:(name:string,fn:(event:MessageEvent)=>void)=>void}} } }
class WorkstationBridge {
  private serial = 0;
  private pending = new Map<number,Pending>();
  constructor(){
    window.chrome?.webview?.addEventListener('message',e => {
      try {
        const msg = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
        if(!msg || typeof msg.id !== 'number') return;
        const op = this.pending.get(msg.id); if(!op) return;
        this.pending.delete(msg.id);
        if(msg.ok) op.resolve(msg.data); else op.reject(new Error(String(msg.error || '原生服务请求失败')));
      } catch { /* Unrecognized host event; not a model response. */ }
    });
  }
  call<T>(action:string,payload:Record<string,unknown>={}):Promise<T>{
    const host=window.chrome?.webview;
    if(!host) return Promise.reject(new Error('当前是前端预览环境。请从 WindowsAIWorkstation.exe 启动以使用本地任务。'));
    const id=++this.serial;
    const request:Message={id,action,payload};
    return new Promise<T>((resolve,reject)=>{
      this.pending.set(id,{resolve:resolve as (x:unknown)=>void,reject});
      host.postMessage(JSON.stringify(request));
      // No hidden polling or model calls. The native host always replies on the same ID.
    });
  }
}
export const bridge=new WorkstationBridge();
