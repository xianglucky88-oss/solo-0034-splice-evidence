import { byId, options } from './dom.mjs';

export function renderAdoption(work, receipts, archived) {
  byId('apply').disabled = archived;
  byId('apply-dates').disabled = archived || work.tier.status === 'disabled';
  byId('date-a').value = work.tier.measured_on.a || '';
  byId('date-b').value = work.tier.measured_on.b || '';
  byId('date-a').disabled = archived;
  byId('date-b').disabled = archived;
  for (const side of ['a', 'b']) {
    byId(`label-${side}`).firstChild.textContent = work.plan[`${side}_label`];
    const select = byId(`pick-${side}`);
    const records = receipts.filter((item) => item.direction === side);
    options(select, [['', '未采用'], ...records.map((item) => [item.trace_id, item.trace_id])], work.active[side]?.trace_id);
    select.disabled = archived;
  }
}

export function selectedTraces(revision) {
  return { revision, a: byId('pick-a').value || null, b: byId('pick-b').value || null };
}
