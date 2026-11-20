/**
 * Adapted from T3 Code's ConnectionStatusDot.tsx (MIT, T3 Tools Inc., 2026).
 * https://github.com/pingdotgg/t3code/blob/8e8ff9b243e5a4c3a837c9033a134b62aac7dade/apps/web/src/components/ConnectionStatusDot.tsx
 * T3-owned tooltip, state types and cn utility were removed, leaving a reusable
 * visual primitive that now receives AIWS task-state data only.
 */
type Phase = 'connected' | 'connecting' | 'reconnecting' | 'error' | 'unknown';
export function connectionPhaseDotClassName(phase: Phase): string {
  switch (phase) {
    case 'connected': return 'status-good';
    case 'connecting':
    case 'reconnecting': return 'status-warn';
    case 'error': return 'status-error';
    default: return 'status-muted';
  }
}
export function T3StatusDot({ phase, label }: {phase: Phase; label: string}) {
  return <span className={`status-dot ${connectionPhaseDotClassName(phase)}`} title={label} aria-label={label} />;
}
