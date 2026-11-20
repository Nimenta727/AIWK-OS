/**
 * Adapted from T3 Code apps/web/src/components/ui/table.tsx (MIT, T3 Tools Inc., 2026).
 * Original layout primitives retained; Tailwind and ~/lib/utils removed for AIWS styles.
 * Upstream: https://github.com/pingdotgg/t3code
 */
import type {ComponentProps} from 'react';
function cx(a:string,b?:string){return [a,b].filter(Boolean).join(' ')}
export function ReviewTable({className,...props}:ComponentProps<'table'>){return <div className="review-table-container"><table data-slot="table" className={cx('review-table',className)} {...props}/></div>}
export function ReviewTableHead({className,...props}:ComponentProps<'thead'>){return <thead data-slot="table-header" className={cx('review-table-head',className)} {...props}/>}
export function ReviewTableBody({className,...props}:ComponentProps<'tbody'>){return <tbody data-slot="table-body" className={cx('review-table-body',className)} {...props}/>}
export function ReviewTableRow({className,...props}:ComponentProps<'tr'>){return <tr data-slot="table-row" className={cx('review-table-row',className)} {...props}/>}
export function ReviewTableHeader({className,...props}:ComponentProps<'th'>){return <th data-slot="table-head" className={cx('review-table-th',className)} {...props}/>}
export function ReviewTableCell({className,...props}:ComponentProps<'td'>){return <td data-slot="table-cell" className={cx('review-table-td',className)} {...props}/>}
