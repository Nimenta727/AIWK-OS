/** Shapes returned by /api/v1/observatory and /api/v1/builder. */
export type Bilingual={zh:string;en:string};
export type Totals={in:number|null;out:number|null;cacheRead:number|null;cacheWrite:number|null;knownSessions:number;unknownSessions:number;unverifiedSessions:number};
export type SessionRow={session:string;agent:string;status:string;events:number;toolCalls:number;toolErrors:number;errors:number;unrecognizedEvents:number;
 tokens:{in:number|null;out:number|null;cacheRead:number|null;cacheWrite:number|null;basis:string;verified:boolean;unknownUsageEvents:number};costUsd:number|null;truncated:boolean};
export type Waiting={taskId:string;stageKey:string;tool:string;label:string;taskTitle:string;ready:boolean};
export type Failure={taskId:string;stageKey:string;tool:string;label:string;error:string};
export type RecentTask={id:string;title:string;createdAt:number;stages:Record<string,number>};
export type Budget={mandateId:string;used:number;limit:number;input:{used:number;limit:number};output:{used:number;limit:number}};
export type RunApproval={runId:string;category:string;tool:string;detail:string};
export type Mandate={id:string;provider:string;projectDir:string;allowedTools:string[];tokenBudget:{input:number;output:number};used:{input:number;output:number};state:string;wallClockMinutes:number;maxTurns:number};
export type BuilderInfo={enabled:boolean;providers:Record<string,{installed:boolean}>;mandates:Mandate[];status:{isolation?:{mode:string;user:string};active:{runId:string;state:string;turns:number;usedInput:number;usedOutput:number}|null}};
export type Summary={demo:boolean;runApprovals:RunApproval[];
 status:{localModel:{configured:boolean;online:boolean;weightsPresent:boolean;gate?:{loaded:boolean;rssMiB?:number}|null};builder:{state:string;enabled?:boolean;runId?:string|null;turns?:number};router:{externalEnabled:boolean}};
 tokens:{total:Totals;byAgent:Record<string,Totals>;budget:Budget|null};
 tasks:{tasks:number;stages:Record<string,number>;needsApproval:Waiting[];failures:Failure[];recent:RecentTask[]};
 sessions:SessionRow[];recent:Array<{ts:number;source:string;label:string;status:string}>;
 verdict:{level:string;sentences:Bilingual[]};audit:{valid:boolean;events:number}};
export type EventRow={seq:number;ts:number;kind:string;tool?:string;status?:string;detail?:string;tokens?:{in:number|null;out:number|null;source:string;scope:string}};
