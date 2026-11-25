import { byId, options } from './dom.mjs';

export function renderAdoption(work, receipts, archived) {
  byId('apply').disabled = archived;
  const reviewMode = work.mode === 'review';
  const reviewDirection = work.review_direction;
  for (const side of ['a', 'b']) {
    byId(`label-${side}`).firstChild.textContent = work.plan[`${side}_label`];
    const select = byId(`pick-${side}`);
    const records = receipts.filter((item) => item.direction === side);
    options(select, [['', '未采用'], ...records.map((item) => [item.trace_id, item.trace_id])],
      work.active[side]?.trace_id);
    const lockedByReview = reviewMode && side === reviewDirection;
    select.disabled = archived || lockedByReview;
    if (lockedByReview) {
      select.title = '该方向由同向重测复核名单接管，请在下方名单中管理';
    } else {
      select.title = '';
    }
  }
}

export function selectedTraces(revision) {
  return { revision, a: byId('pick-a').value || null, b: byId('pick-b').value || null };
}
