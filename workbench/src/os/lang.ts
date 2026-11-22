/** Current UI language, readable from plain functions (api errors) as well as from React. English when `en`. */
let current: 'zh' | 'en' = 'zh';
const listeners = new Set<(l: 'zh' | 'en') => void>();
export const getLang = () => current;
export function setLang(l: 'zh' | 'en') { if (l === current) return; current = l; listeners.forEach(f => f(l)); }
export function onLang(f: (l: 'zh' | 'en') => void) { listeners.add(f); return () => { listeners.delete(f); }; }
