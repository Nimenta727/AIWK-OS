/** UI-only deterministic helpers. No model calls or native file writes. */
export function filterTaskList(tasks, query) {
  const needle = String(query || '').trim().toLocaleLowerCase();
  return [...(tasks || [])]
    .filter(t => !needle || String(t.title || '').toLocaleLowerCase().includes(needle))
    .sort((a,b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
}

export function shouldActivateShortcut(event) {
  return Boolean((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && !event.repeat);
}

/** Never silently retry a native action with side effects on a transport timeout. */
export function timeoutMessage(action, readOnly) {
  return readOnly
    ? `本地读取“${action}”超时。可刷新后再查看，未自动重试。`
    : `本地操作“${action}”等待确认超时。结果尚不确定，请先刷新并核实状态，切勿直接重复提交。`;
}
