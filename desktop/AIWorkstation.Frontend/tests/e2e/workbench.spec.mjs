import {test,expect} from '@playwright/test';

const makeTask=(id,title,createdAt='2026-11-20T08:00:00Z')=>({
 id,title,createdAt,workspace:'C:\\Projects\\AIWS',graphMode:false,promptWarningTokens:2500,promptStopTokens:6000,
 completedCount:0,requestEvents:[],executionRecords:[],
 unified:{schemaVersion:1,goal:'完善用户界面',acceptanceCriteria:'所有操作可用',maxRecommendedActive:1,dispatchRequests:[],plans:[],artifacts:[],agentRuns:[],workItems:[]},
 steps:[{id:`${id}-step`,title:'改进前端',agent:'Codex',status:'Pending',approvalGranted:false,requiresApproval:true,
 dependsOn:[],worktreePath:'',worktreeBaseline:'',runId:'',gitBefore:null,gitAfter:null,instructions:'修复交互',result:'',usage:{input:null,output:null,cachedInput:null,source:''},lastPromptFingerprint:'',startedAt:null,completedAt:null}]
});

async function mountMock(page,{slowCreate=false}={}) {
 await page.addInitScript(({slowCreate})=>{
  const tasks=[
   {id:'original',title:'AIWS 产品重构',createdAt:'2026-11-20T08:00:00Z',workspace:'C:\\Projects\\AIWS',graphMode:false,promptWarningTokens:2500,promptStopTokens:6000,completedCount:0,requestEvents:[],executionRecords:[],
    unified:{schemaVersion:1,goal:'完善用户界面',acceptanceCriteria:'所有操作可用',maxRecommendedActive:1,dispatchRequests:[],plans:[],artifacts:[],agentRuns:[],workItems:[]},
    steps:[{id:'stage-1',title:'改进前端',agent:'Codex',status:'Pending',approvalGranted:false,requiresApproval:true,dependsOn:[],worktreePath:'',worktreeBaseline:'',runId:'',gitBefore:null,gitAfter:null,instructions:'修复交互',result:'',usage:{input:null,output:null,cachedInput:null,source:''},lastPromptFingerprint:'',startedAt:null,completedAt:null}]}
  ];
  const listeners=new Map();
  const actions=[];
  const main={version:'1.8.1',tasks,providers:[{id:'codex',name:'Codex CLI',agent:'Codex',toolName:'codex',available:true,requiresUserLaunch:true,supportsUnattended:false,supportsLocalWorktree:true,canImportStructuredUsage:true,canObserveInternalRequests:false,notice:'本机受控启动'}],agents:{'Codex CLI':true},limitations:[]};
  window.__aiwsTest={actions,tasks,main};
  const send=(msg)=>{for(const fn of listeners.get('message')||[])fn({data:JSON.stringify(msg)});};
  window.chrome=window.chrome||{};
  window.chrome.webview={addEventListener:(type,fn)=>{if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(fn);},postMessage:(raw)=>{
   const req=JSON.parse(raw);actions.push(req.action);
   let value=null;
   switch(req.action){
    case 'state':value={...main,tasks:[...tasks]};break;
    case 'tasks.create':{
     const id='new-'+(tasks.length+1);const s={id,title:req.payload.title,workspace:req.payload.workspace,createdAt:new Date().toISOString(),graphMode:false,promptWarningTokens:2500,promptStopTokens:6000,completedCount:0,requestEvents:[],executionRecords:[],unified:{schemaVersion:1,goal:'',acceptanceCriteria:'',maxRecommendedActive:1,dispatchRequests:[],plans:[],artifacts:[],agentRuns:[],workItems:[]},steps:[{id:'stage-'+id,title:'开始任务',agent:'Codex',status:'Pending',approvalGranted:false,requiresApproval:true,dependsOn:[],worktreePath:'',worktreeBaseline:'',runId:'',gitBefore:null,gitAfter:null,instructions:'完成任务',result:'',usage:{input:null,output:null,cachedInput:null,source:''},lastPromptFingerprint:'',startedAt:null,completedAt:null}]};
     tasks.unshift(s);value={id};break;}
    case 'workspaces.pick':value={path:'C:\\Projects\\AIWS'};break;
    case 'scheduler.plan':value={taskId:req.payload.taskId,mode:'human-supervised',maxRecommendedActive:1,activeStages:0,completedStages:0,readyStages:1,queuedStages:0,nextStageId:'stage-1',evidenceNotice:'本地',stages:[{stageId:'stage-1',title:'改进前端',adapterId:'codex',agent:'Codex',status:'approval',reason:'等待批准',dependencyCount:0,approxTokens:220,canQueue:false,needsApproval:true,isQueued:false,ticketId:null,recommendedAgent:null}]};break;
    case 'diagnostics.health':value={version:'1.8.1',inspectedAt:new Date().toISOString(),tasks:tasks.length,runningStages:0,interruptedStages:0,pendingApprovals:1,queuedStages:0,importedUsageStages:0,unknownUsageStages:1,backupAvailable:true,securityNotice:'安全模式',releaseNotice:'本地 UI 测试'};break;
    case 'plans.list':value={workspace:'C:\\Projects\\AIWS',files:[],checkedAt:new Date().toISOString(),notices:[]};break;
    case 'atlas.flow':value={lanes:[],importedStages:0,unknownUsageStages:1,importedInput:0,importedOutput:0,importedCachedInput:0,importedToolEvents:null};break;
    case 'project.overview':value={workspace:'C:\\Projects\\AIWS',rootName:'AIWS',branch:'main',head:'abcdef012345',files:[],changedCount:0,truncated:false,notices:[]};break;
    case 'project.stageChanges':value={stageId:'stage-1',stageTitle:'改进前端',fromHead:'abcdef',toHead:'abcdef',headChanged:false,files:[],committedFiles:[],partial:true,notice:'尚无检查点',startedAt:null,completedAt:null};break;
    case 'ledger.timeline':value=[];break;
    case 'steps.preflight':value={approxTokens:100,warningTokens:2500,stopTokens:6000,originalCharacters:300,sentCharacters:300,savedCharacters:0,warn:false,blocked:false,duplicate:false,note:'本地预检完成'};break;
    case 'context.bundle':value={version:1,taskId:req.payload.taskId,stageId:req.payload.stepId,adapterId:'codex',fingerprint:'test',approxTokens:100,sentCharacters:300,savedCharacters:0,manifest:[],evidenceNotice:'本地'};break;
    default:value={};
   }
   const reply=()=>send({id:req.id,ok:true,data:value});
   setTimeout(reply,req.action==='tasks.create'&&slowCreate?450:12);
  }};
 },{slowCreate});
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'AI 协作总控台'})).toBeVisible();
}

test('navigation, selection, project, plan, help keyboard and search work',async({page})=>{
 await mountMock(page);
 await expect(page.getByRole('navigation',{name:'核心工作区'})).toBeVisible();
 await page.getByRole('button',{name:'AI 计划中心'}).click();
 await expect(page.getByRole('heading',{name:'计划中心'})).toBeVisible();
 await page.getByRole('button',{name:'可视化工作流'}).click();
 await expect(page.getByRole('heading',{name:'AIWS 产品重构'})).toBeVisible();
 await page.getByRole('button',{name:'文件与 Git 变更'}).click();
 await expect(page.getByRole('heading',{name:'项目文件与 Git 变更'})).toBeVisible();
 await page.keyboard.press('Control+k');
 await expect(page.getByRole('textbox',{name:'搜索最近任务'})).toBeFocused();
 await page.getByRole('textbox',{name:'搜索最近任务'}).fill('不存在');
 await expect(page.getByText('没有匹配的任务。')).toBeVisible();
 await page.getByRole('textbox',{name:'搜索最近任务'}).fill('AIWS');
 await expect(page.getByRole('button',{name:'AIWS 产品重构'})).toBeVisible();
 await page.getByRole('button',{name:'键盘快捷键与帮助'}).click();
 await expect(page.getByRole('heading',{name:'快捷操作与交互说明'})).toBeVisible();
 await page.keyboard.press('Escape');
 await expect(page.getByRole('heading',{name:'快捷操作与交互说明'})).not.toBeVisible();
});

test('create via keyboard only once, retain native result, and close via Escape',async({page})=>{
 await mountMock(page,{slowCreate:true});
 await page.keyboard.press('Control+n');
 await expect(page.getByRole('dialog',{name:'创建协作任务'})).toBeVisible();
 await expect(page.getByRole('textbox',{name:/任务名称/})).toBeFocused();
 await page.keyboard.press('Escape');
 await expect(page.getByRole('dialog',{name:'创建协作任务'})).not.toBeVisible();
 await page.getByRole('button',{name:'新建任务',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'创建协作任务'});
 await modal.getByRole('textbox',{name:/任务名称/}).fill('新版交互质量验证');
 await modal.getByRole('button',{name:'选择目录'}).click();
 await expect(modal.getByRole('textbox',{name:'已选工作目录'})).toHaveValue('C:\\Projects\\AIWS');
 await modal.getByRole('button',{name:/完整交接/}).click();
 await expect(modal.getByRole('button',{name:/完整交接/})).toHaveAttribute('aria-pressed','true');
 await modal.getByRole('button',{name:'创建任务'}).click();
 await expect(page.getByRole('status').filter({hasText:'正在执行已确认的本地操作'})).toBeVisible();
 await expect(modal.getByRole('button',{name:'正在创建…'})).toBeDisabled();
 await expect(modal).not.toBeVisible();
 await expect(page.getByText('任务已创建，已切换到新任务。')).toBeVisible();
 const creates=await page.evaluate(()=>window.__aiwsTest.actions.filter(x=>x==='tasks.create').length);
 expect(creates).toBe(1);
 await expect(page.getByRole('button',{name:'新版交互质量验证'})).toBeVisible();
});

test('compact desktop viewport can open and close workflow inspector',async({page})=>{
 await page.setViewportSize({width:1024,height:780});
 await mountMock(page);
 await page.getByRole('button',{name:'可视化工作流'}).click();
 await expect(page.getByRole('button',{name:'打开阶段详情'})).toBeVisible();
 await page.getByRole('button',{name:'打开阶段详情'}).click();
 await expect(page.getByRole('complementary',{name:'阶段检查器'})).toBeVisible();
 await page.getByRole('button',{name:'关闭阶段详情'}).first().click();
 await expect(page.getByRole('complementary',{name:'阶段检查器'})).not.toBeVisible();
});
