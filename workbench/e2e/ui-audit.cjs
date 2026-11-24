#!/usr/bin/env node
/* Browser audit of the built workbench against the REAL guest service (os/verify/fixtures/serve_workbench.py).
 *
 *   node e2e/ui-audit.cjs [outDir]          (run `npm run build` first; needs the `playwright` package and Chromium)
 *
 * For every view, in dark 1440x900, light 1440x900 and dark 1024x700, it fails on:
 *   page errors · a page wider than the window · text clipped or spilling out of the editor · a visible control with no
 *   click handler ("fake button") · a button without an accessible name · an icon that renders blank · text below WCAG
 *   contrast (4.5:1, large 3:1) · a whole English sentence in the Chinese UI.
 * Then it clicks every enabled button of every view and fails on one that changes nothing and sends nothing, and it
 * replays the steps of the in-image GUI smoke test (aiws_gui_smoke.py). Power actions are blocked at the network layer.
 * HTTP errors are reported, not failed: some are expected here (no agent service, not root, …).
 * Screenshots and report.json go to outDir (default e2e-out/).
 */
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');

const ROOT=path.resolve(__dirname,'..','..');
const OUT=path.resolve(process.argv[2]||path.join(__dirname,'..','e2e-out'));
const VIEWS=[['home','总览'],['plans','计划审核'],['agents','云端智能体'],['changes','变更审查'],['build','构建'],['files','AI 文件管理'],
 ['tasks','持久任务与 DAG'],['assistant','本地助手'],['model','本地模型开关'],['ide','代码编辑器'],['system','系统'],['advanced','系统服务与内核'],['browser','内置浏览器']];
const SETTINGS=[{theme:'dark',w:1440,h:900},{theme:'light',w:1440,h:900},{theme:'dark',w:1024,h:700}];

function startServer(){
 return new Promise((resolve,reject)=>{
  const py=spawn('python3',[path.join(ROOT,'os/verify/fixtures/serve_workbench.py'),'--ui',path.join(ROOT,'workbench/dist')],{stdio:['ignore','pipe','inherit']});
  let buf='';
  py.stdout.on('data',d=>{buf+=d;const m=buf.match(/ready (\d+)/);if(m)resolve({py,base:'http://127.0.0.1:'+m[1]+'/'});});
  py.on('exit',code=>reject(new Error('server exited '+code)));
  setTimeout(()=>reject(new Error('server did not start')),20000);
 });
}

async function newPage(browser,base,s){
 const ctx=await browser.newContext({viewport:{width:s.w,height:s.h},locale:'zh-CN'});
 await ctx.route('**/api/v1/system/power',r=>r.abort());
 const page=await ctx.newPage();
 const log=[];
 page.on('pageerror',e=>log.push({kind:'pageerror',text:String(e).slice(0,300)}));
 page.on('response',r=>{if(r.status()>=400)log.push({kind:'http',text:r.status()+' '+r.request().method()+' '+r.url().replace(base,'/')});});
 await page.addInitScript(t=>{try{localStorage.setItem('aiws.lang','zh');localStorage.setItem('aiws.shell.prefs',JSON.stringify({theme:t,sidebar:true,panel:false,activity:'home'}));}catch{/* private mode */}},s.theme);
 await page.goto(base);await page.waitForSelector('.app .tabs');await page.waitForTimeout(800);
 return {ctx,page,log};
}
async function openView(page,label){
 await page.keyboard.press('Escape');
 await page.keyboard.press('Control+Shift+P');await page.fill('.pal input','打开：'+label);
 // pick the option itself (the palette runs commands on mousedown): Enter would go wherever focus was left by the last click
 await page.locator('.pal li[role=option]').first().dispatchEvent('mousedown');
 await page.waitForSelector('.pal',{state:'detached'});await page.waitForTimeout(600);
}

// runs in the page: every check that does not need clicking
function inspect(){
 const vis=e=>{const s=getComputedStyle(e);const b=e.getBoundingClientRect();return s.visibility!=='hidden'&&s.display!=='none'&&b.width>0&&b.height>0;};
 const name=e=>(e.getAttribute('aria-label')||e.getAttribute('title')||e.textContent||'').trim().replace(/\s+/g,' ').slice(0,60);
 const props=e=>{const k=Object.keys(e).find(k=>k.startsWith('__reactProps$'));return k?e[k]:{};};
 const root=document.querySelector('.app');
 const fake=[],noname=[];
 for(const e of root.querySelectorAll('button,[role=button],[role=tab],[role=option],[role=treeitem],a')){
  if(!vis(e)||e.disabled||e.getAttribute('aria-disabled')==='true')continue;
  const p=props(e);
  let handled=p.onClick||p.onMouseDown||p.onPointerDown||(e.tagName==='A'&&e.getAttribute('href'))||(e.type==='submit'&&e.closest('form'));
  for(let a=e.parentElement,i=0;!handled&&a&&i<3;a=a.parentElement,i++){const q=props(a);if(q.onClick||q.onMouseDown)handled=true;}
  if(!handled)fake.push(e.tagName.toLowerCase()+' «'+name(e)+'»');
  if(!name(e))noname.push(e.outerHTML.slice(0,120));
 }
 const editor=document.querySelector('.editor').getBoundingClientRect();
 const clipped=new Set();
 for(const e of root.querySelectorAll('.editor *')){
  if(!vis(e)||![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))continue;
  const s=getComputedStyle(e);
  if(e.scrollWidth>e.clientWidth+2&&s.overflowX==='hidden'&&s.textOverflow!=='ellipsis')clipped.add(name(e));
  if(e.getBoundingClientRect().right>editor.right+2&&s.position!=='fixed')clipped.add('outside the editor: '+name(e));
 }
 const lum=c=>{const m=c.match(/[\d.]+/g);if(!m||(m.length>3&&+m[3]===0))return null;return m.slice(0,3).map(Number).map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}).reduce((s,v,i)=>s+v*[0.2126,0.7152,0.0722][i],0);};
 const bg=e=>{for(;e;e=e.parentElement){const m=getComputedStyle(e).backgroundColor.match(/[\d.]+/g);if(m&&(m.length<4||+m[3]>0.5))return getComputedStyle(e).backgroundColor;}return 'rgb(255,255,255)';};
 const low=new Map();
 for(const e of root.querySelectorAll('*')){
  if(!vis(e)||e.closest('[disabled],[aria-disabled=true]')||![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim().length>1))continue;
  const s=getComputedStyle(e);const L1=lum(s.color),L2=lum(bg(e));if(L1==null||L2==null)continue;
  const ratio=(Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);const big=parseFloat(s.fontSize)>=18.66||(parseFloat(s.fontSize)>=14&&+s.fontWeight>=700);
  if(ratio<(big?3:4.5)||+s.opacity<0.6)low.set(name(e).slice(0,30),ratio.toFixed(2)+' '+s.fontSize);
 }
 const blankIcons=[...root.querySelectorAll('.codicon')].filter(e=>vis(e)&&['none','normal','""'].includes(getComputedStyle(e,'::before').content)).map(e=>e.className);
 // the glyph is set by CSS even when the font never arrives (that was the shipped bug): the codicon face itself must be loaded
 if(root.querySelector('.codicon')&&![...document.fonts].some(f=>/codicon/i.test(f.family)&&f.status==='loaded'))blankIcons.push('the codicon font is not loaded');
 const english=new Set();const tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;
 while((n=tw.nextNode())){const t=n.textContent.trim();if(/^[A-Za-z][A-Za-z ,.'’()-]{14,}$/.test(t)&&(t.match(/ /g)||[]).length>=2&&n.parentElement&&vis(n.parentElement)&&!n.parentElement.closest('code,pre,kbd,.selectable'))english.add(t.slice(0,60));}
 const de=document.scrollingElement;
 return {hscroll:de.scrollWidth>de.clientWidth+1,fake,noname,clipped:[...clipped],lowContrast:[...low],blankIcons,english:[...english]};
}

async function auditViews(browser,base,s,report){
 const {ctx,page,log}=await newPage(browser,base,s);
 const key=s.theme+'-'+s.w;
 report.http.push(...log.splice(0).map(l=>({...l,where:key+'/initial'})));
 await page.evaluate(()=>document.fonts.ready);
 for(const [id,label] of VIEWS){
  await openView(page,label);
  const r=await page.evaluate(inspect);
  await page.screenshot({path:path.join(OUT,key+'-'+id+'.png')});
  const issues=Object.fromEntries(Object.entries(r).filter(([k,v])=>k==='hscroll'?v:v.length));
  for(const l of log.splice(0))(l.kind==='pageerror'?(issues.pageerror=issues.pageerror||[]).push(l.text):report.http.push({...l,where:key+'/'+id}));
  if(Object.keys(issues).length)report.failures.push({where:key+'/'+id,issues});
 }
 await ctx.close();
}

async function clickEverything(browser,base,report){
 const {ctx,page}=await newPage(browser,base,SETTINGS[0]);
 let requests=0;page.on('request',()=>requests++);
 const sel='.editor button:not([disabled]):visible, .editor [role=button]:visible, .editor [role=tab]:visible';
 for(const [id,label] of VIEWS){
  await openView(page,label);
  const n=await page.locator(sel).count();
  for(let i=0;i<n;i++){
   await openView(page,label);
   const btn=page.locator(sel).nth(i);if(!(await btn.count()))continue;
   const label2=((await btn.getAttribute('aria-label'))||(await btn.innerText().catch(()=>''))||'').trim().slice(0,40);
   const before=await page.evaluate(()=>document.querySelector('.app').innerHTML);const r0=requests;
   try{await btn.click({timeout:2000});}catch(e){report.failures.push({where:'click/'+id,issues:{notClickable:[label2+': '+String(e).split('\n')[0].slice(0,80)]}});continue;}
   await page.waitForTimeout(600);
   if(await page.evaluate(()=>document.querySelector('.app').innerHTML)===before&&requests===r0)report.failures.push({where:'click/'+id,issues:{noEffect:[label2||'(no label)']}});
   report.clicked++;
  }
 }
 await ctx.close();
}

async function smokeReplay(browser,base,report){
 const {ctx,page}=await newPage(browser,base,{theme:'dark',w:1280,h:800});
 const go=l=>openView(page,l).catch(()=>{});
 const step=async(name,fn)=>{try{await fn();report.smoke.push({step:name,ok:true});}catch(e){report.smoke.push({step:name,ok:false,error:String(e).split('\n')[0]});report.failures.push({where:'smoke/'+name,issues:{error:[String(e).split('\n')[0]]}});}};
 await step('files: click and read',async()=>{await go('AI 文件管理');
  await page.locator("xpath=//*[contains(@class,'aiws-os-file-list')]//*[@role='treeitem'][contains(.,'AIWS-GUEST-SMOKE.txt')]").click();
  await page.waitForFunction(()=>document.querySelector('.aiws-os-file-detail pre')?.textContent.includes('guest-only file manager acceptance fixture'),null,{timeout:8000});});
 await step('tasks: save and run a stage',async()=>{await go('持久任务与 DAG');
  await page.locator('.aiws-os-studio input').first().fill('GUI guest smoke');await page.locator('.aiws-os-studio textarea').first().fill('List guest workspace');
  await page.locator("xpath=//button[contains(.,'保存任务与 DAG')]").click();await page.waitForSelector('.aiws-os-stage-status');
  await page.locator("xpath=//button[contains(.,'运行客户机阶段')]").click();
  await page.waitForFunction(()=>document.querySelector('.aiws-os-stage-status')?.getAttribute('data-state')==='completed',null,{timeout:15000});});
 await step('model switch: no weights shipped',async()=>{await go('本地模型开关');const t=await page.locator('.aiws-os-studio').innerText();
  if(!(t.includes('未启用')&&t.includes('Qwen3.5-9B')))throw new Error('unexpected text: '+t.slice(0,160));});
 await step('kernel candidate opens plan review',async()=>{await go('系统服务与内核');await page.waitForSelector('.aiws-os-system-console');
  await page.locator("xpath=//button[contains(.,'提交候选验证和暂存审批')]").click();await page.waitForSelector("xpath=//button[contains(.,'批准并运行')]",{timeout:8000});});
 await ctx.close();
}

(async()=>{
 fs.mkdirSync(OUT,{recursive:true});
 const report={failures:[],http:[],clicked:0,smoke:[]};
 const {py,base}=await startServer();
 const browser=await chromium.launch();
 try{
  for(const s of SETTINGS)await auditViews(browser,base,s,report);
  await clickEverything(browser,base,report);
  await smokeReplay(browser,base,report);
 }finally{await browser.close();py.kill('SIGTERM');}
 // an error on a UI file (script, style, font, image) is a broken page, not an expected API refusal
 for(const h of report.http)if(!/ \/api\//.test(h.text))report.failures.push({where:h.where,issues:{asset:[h.text]}});
 fs.writeFileSync(path.join(OUT,'report.json'),JSON.stringify(report,null,1));
 console.log('views: '+VIEWS.length+' x '+SETTINGS.length+' settings · buttons clicked: '+report.clicked+' · smoke steps: '+report.smoke.filter(s=>s.ok).length+'/'+report.smoke.length);
 const http=[...new Set(report.http.map(h=>h.text))];
 if(http.length)console.log('HTTP errors seen (reported, not failed):\n  '+http.join('\n  '));
 if(report.failures.length){console.error('UI AUDIT FAILED:\n'+report.failures.map(f=>'  '+f.where+' '+JSON.stringify(f.issues)).join('\n'));process.exit(1);}
 console.log('UI AUDIT PASSED');
})().catch(e=>{console.error(e);process.exit(2);});
