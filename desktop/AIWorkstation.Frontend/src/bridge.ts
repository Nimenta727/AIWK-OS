export type TokenUsage = { input: number|null; output:number|null; cachedInput:number|null; source:string; isMeasured?:boolean };
export type TraceEvent = { at:string; stageId:string; kind:string; summary:string };
export type GitObservedFile = {path:string;status:string;signature:string};
export type GitCheckpoint = {capturedAt:string;head:string;files:GitObservedFile[];partial:boolean;problem:string};
export type ProjectFile = {path:string;isDirectory:boolean;status:string;size:number|null;isLink:boolean};
export type ProjectOverview = {workspace:string;rootName:string;branch:string;head:string;files:ProjectFile[];changedCount:number;truncated:boolean;notices:string[]};
export type FileReview = {path:string;status:string;diff:string;truncated:boolean;isPreview:boolean;note:string};
export type StageChangeReport = {stageId:string;stageTitle:string;fromHead:string;toHead:string;headChanged:boolean;files:{path:string;kind:string;before:string;after:string}[];committedFiles:string[];partial:boolean;notice:string;startedAt:string|null;completedAt:string|null};
export type ExecutionRecord = {id:string;stageId:string;runId:string;kind:string;source:string;evidence:'observed'|'imported'|'inferred'|'unknown';at:string;metadata:string};
export type WorkStep = { dependsOn:string[];worktreePath:string;worktreeBaseline:string;runId:string;  gitBefore:GitCheckpoint|null;gitAfter:GitCheckpoint|null; id:string; title:string; agent:'ClaudeCode'|'Codex'|'Manual'; status:'Pending'|'Running'|'Completed'|'Failed'|'Interrupted'; approvalGranted:boolean; requiresApproval:boolean; instructions:string; result:string; usage:TokenUsage; lastPromptFingerprint:string; startedAt:string|null; completedAt:string|null };
export type WorkTask = { id:string; title:string; workspace:string; graphMode:boolean; promptWarningTokens:number; promptStopTokens:number; executionRecords:ExecutionRecord[]; createdAt:string; steps:WorkStep[]; requestEvents:TraceEvent[]; completedCount:number };
export type Snapshot = { version:string; tasks:WorkTask[]; agents:Record<string,boolean>; limitations:string[] };
type Pending = { resolve:(x:unknown)=>void; reject:(e:Error)=>void };
type Message = {id:number;action:string;payload:Record<string,unknown>};
declare global { interface Window { chrome?:{webview?:{postMessage:(x:string)=>void;addEventListener:(name:string,fn:(event:MessageEvent)=>void)=>void}} } }
class WorkstationBridge {
  private serial = 0;
  private listeners = new Map<string,Set<(data:unknown)=>void>>();
  onEvent(name:string,callback:(data:unknown)=>void):()=>void {
    const callbacks=this.listeners.get(name)||new Set<(data:unknown)=>void>();
    callbacks.add(callback);this.listeners.set(name,callbacks);
    return ()=>{callbacks.delete(callback);if(!callbacks.size)this.listeners.delete(name);};
  }
  private pending = new Map<number,Pending>();
  constructor(){
    window.chrome?.webview?.addEventListener('message',e => {
      try {
        const msg = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
        if(!msg)return;
        if(typeof msg.eventName==='string'){
          for(const callback of this.listeners.get(msg.eventName)||[])callback(msg.data);
          return;
        }
        if(typeof msg.id !== 'number') return;
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

// V1.7 Execution Atlas: projections only. No model call is issued by these actions.
export type FlowNode = {id:string;stepId:string;phase:string;title:string;subtitle:string;state:'Planned'|'Recorded'|'Imported'|'Unknown'|'Attention';detail:string;evidence:string;usageText:string;durationText:string;recordedAt:string|null};
export type ProviderEvidence = {sequence:number;kind:string;toolCategory:string;input:number|null;output:number|null;cachedInput:number|null};
export type FlowLane = {stepId:string;header:string;agent:string;state:string;nodes:FlowNode[];importedEvents:ProviderEvidence[]};
export type AtlasFlow = {lanes:FlowLane[];importedStages:number;unknownUsageStages:number;importedInput:number;importedOutput:number;importedCachedInput:number;importedToolEvents:number|null};
export type StructureEntry = {path:string;isDirectory:boolean;before:boolean;after:boolean;change:'added'|'removed'|'modified'|'touched'|'replaced'|'unchanged'|'unknown'|'moved-in'|'moved-out';evidence:string};
export type StructureReport = {stageId:string;stageTitle:string;workspace:string;hasBefore:boolean;hasAfter:boolean;partial:boolean;notice:string;beforeAt:string|null;afterAt:string|null;entries:StructureEntry[];added:number;removed:number;modified:number;changedDirectories:number;committedFiles:string[];renamedFiles:{fromPath:string;toPath:string}[]};
export type ContextPart = {kind:string;title:string;characters:number;source:string;included:boolean;evidence:string};
export type ContextReport = {stageId:string;characters:number;originalCharacters:number;savedCharacters:number;approxTokens:number;fingerprint:string;truncated:boolean;text:string;parts:ContextPart[];notice:string};
export type RelatedStage = {stageId:string;title:string;agent:string;workspace:string;evidence:string;partial:boolean};
export type RelatedStageLookup = {stages:RelatedStage[];partial:boolean;notice:string};

// Local Markdown plan evidence, not model-generated JSON or provider telemetry.
export type PlanFile = {path:string;name:string;bytes:number;updatedAt:string;version:string};
export type PlanCatalog = {workspace:string;files:PlanFile[];checkedAt:string;notices:string[]};
export type PlanDocument = {path:string;text:string;version:string;updatedAt:string;bytes:number;sha256:string};

// AIWS local *estimated* handoff size. Not billing, provider-side token usage,
// or a hard limit on an external interactive CLI's internal context.
export type PromptBudgetAssessment = {approxTokens:number;warningTokens:number;stopTokens:number;originalCharacters:number;sentCharacters:number;savedCharacters:number;warn:boolean;blocked:boolean;duplicate:boolean;note:string};
