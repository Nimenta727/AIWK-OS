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
