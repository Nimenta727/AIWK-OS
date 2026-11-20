/** UI command selector has no arbitrary argv or shell command field. Native host independently validates. */
export const READ_ONLY_VIEWS = Object.freeze([
  {id:'status',label:'工作树状态',command:'git status --short'},
  {id:'summary',label:'变更概览',command:'git diff --stat'},
  {id:'diff',label:'工作树 Diff',command:'git diff'},
  {id:'staged',label:'已暂存 Diff',command:'git diff --cached'},
  {id:'history',label:'最近提交',command:'git log -n 12'},
  {id:'branch',label:'当前分支',command:'git branch --show-current'}
]);
export function resolveReadOnlyView(view){return READ_ONLY_VIEWS.find(v=>v.id===view)??null}
export function normalizeOutput(value,max=120000){return String(value??'').slice(0,max)}
