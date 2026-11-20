/** Pure presentation logic. Git evidence never implies model attribution. */
export function describeGitStatus(raw) {
  if (raw === '??') return {label:'新建 / 未追踪',short:'U',tone:'added'};
  if (!raw) return {label:'没有未提交状态',short:'',tone:'muted'};
  if (raw.includes('D')) return {label:'已删除',short:'D',tone:'deleted'};
  if (raw.includes('R')) return {label:'已重命名',short:'R',tone:'modified'};
  if (raw.includes('A')) return {label:'已新增',short:'A',tone:'added'};
  if (raw.includes('M')) return {label:'已修改',short:'M',tone:'modified'};
  return {label:'Git 状态：'+raw,short:raw.trim(),tone:'muted'};
}
export function describeObservedChange(kind){return ({appeared:'新出现',changed:'内容/状态变化',cleared:'不再显示为未提交'})[kind]||'其他变化'}
export function formatShortHead(head){return head?.length>=7?head.slice(0,8):'无提交记录'}


// In "changed" mode preserve affected folder ancestors, instead of rendering
// changed files floating without a directory hierarchy. Input is read-only.
export function visibleProjectFiles(files,mode,collapsed) {
  const items=files||[];
  const changedFolders=new Set();
  if(mode==='changed') for(const f of items) if(!f.isDirectory&&f.status) {
    const parts=String(f.path).split('/');
    for(let n=1;n<parts.length;n++)changedFolders.add(parts.slice(0,n).join('/'));
  }
  return items.filter(f=>{
    if(mode==='changed' && !(f.isDirectory?changedFolders.has(f.path):Boolean(f.status)))return false;
    const parents=String(f.path).split('/').slice(0,-1);
    for(let n=1;n<=parents.length;n++)if(collapsed?.has(parents.slice(0,n).join('/')))return false;
    return true;
  });
}
