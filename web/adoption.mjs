import { byId, options } from './dom.mjs';
import { credential, stated } from './format.mjs';

export function renderAdoption(work, receipts, archived) {
  byId('apply').disabled = archived;
  for (const side of ['a', 'b']) {
    byId(`label-${side}`).firstChild.textContent = work.plan[`${side}_label`];
    const select = byId(`pick-${side}`);
    const records = receipts.filter((item) => item.direction === side);
    const labels = records.map((item) => {
      const mark = item.notice ? ` · 已撤销 ${item.notice.notice_id}` : item.adopted ? ' · 在用' : '';
      return [item.trace_id, `${item.trace_id} · ${credential(item)}${mark}`];
    });
    options(select, [['', '未采用'], ...labels], work.active[side]?.trace_id);
    select.disabled = archived;
  }
  const adopted = work.handoff?.adopted || [];
  byId('adopted-hint').textContent = adopted.some((item) => !stated(item))
    ? '有采用凭证未注明仪表与校验批次，按来源未注明沿用原流程'
    : '';
}
