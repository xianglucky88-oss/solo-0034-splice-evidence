import { byId, node } from './dom.mjs';
import { credential, direction } from './format.mjs';

export function setupRevocation(submit) {
  const dialog = byId('revocation');
  const form = byId('revocation-form');
  const error = byId('revocation-error');
  let pending = false;
  byId('revocation-cancel').addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', (event) => { if (pending) event.preventDefault(); });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (pending) return;
    pending = true;
    error.textContent = '';
    const buttons = form.querySelectorAll('button');
    buttons.forEach((button) => { button.disabled = true; });
    try {
      const values = Object.fromEntries(new FormData(form).entries());
      const payload = { instrument_id: values.instrument_id.trim(), calibration_batch: values.calibration_batch.trim() };
      if (values.notice_id.trim()) payload.notice_id = values.notice_id.trim();
      if (values.note.trim()) payload.note = values.note.trim();
      await submit(payload);
      dialog.close();
    } catch (issue) {
      error.textContent = issue.message;
    } finally {
      pending = false;
      buttons.forEach((button) => { button.disabled = false; });
    }
  });
  return () => {
    form.reset();
    error.textContent = '';
    dialog.showModal();
    byId('revocation-instrument').focus();
  };
}

function line(label, detail, broken = false) {
  return [node('dt', label), node('dd', detail, broken ? 'error' : null)];
}

export function renderRevocationImpact(work, notices, spanId) {
  const hand = work.handoff || { status: 'clear', adopted: [], affected: [] };
  const detail = byId('revocations');
  const head = node('p', hand.status === 'clear' ? '现时可交接' : '现时不可交接',
    `status ${hand.status === 'clear' ? 'good' : 'warn'}`);
  const list = node('dl', null, 'detail nested');
  const adopted = hand.adopted || [];
  list.replaceChildren(...(adopted.length ? adopted.flatMap((item) => [
    ...line(`${direction[item.side]} 工作修订`, `${credential(item)}${item.notice ? ' · 已撤销' : ''}`, Boolean(item.notice)),
    ...(item.notice ? line('撤销通知', `${item.notice.notice_id} · ${item.notice.revoked_at}${item.notice.note ? ` · ${item.notice.note}` : ''}`, true) : []),
  ]) : [node('p', '尚未采用任何凭证', 'muted')]));
  detail.replaceChildren(head, list);

  const scope = byId('revocation-scope');
  const entries = notices.map((notice) => {
    const receipts = notice.impacts.receipts;
    const working = notice.impacts.working;
    const releases = notice.impacts.releases;
    const unadopted = receipts.filter((entry) => !entry.adopted);
    const item = node('div', null, 'revocation-item');
    item.append(node('p', `${notice.instrument_id} · ${notice.calibration_batch}`, 'release-title'),
      node('small', `通知 ${notice.notice_id} · ${notice.revoked_at}${notice.note ? ` · ${notice.note}` : ''}`, 'muted'),
      node('small', `收件影响 ${receipts.length} 份 · 在用修订 ${working.length} · 已签件 ${releases.length}`, 'muted'));
    for (const entry of releases) {
      const sides = entry.affected.map((mark) => direction[mark.side]).join('、');
      item.append(node('small', `${entry.span_id} 修订 ${entry.revision} · ${sides} · 现时不可交接 · 摘要 ${entry.digest.slice(0, 12)}`, 'error'));
    }
    for (const entry of working) {
      item.append(node('small', `${entry.span_id} 工作修订 ${entry.revision} · ${direction[entry.side]} · 须留置`, 'error'));
    }
    if (unadopted.length) {
      item.append(node('small', `未采用仅记收件影响：${unadopted.map((entry) => `${entry.span_id}/${entry.trace_id}`).join('、')}`, 'muted'));
    }
    if (!releases.length && !working.length) {
      item.append(node('small', '无在用或已签件受影响，沿用原流程', 'muted'));
    }
    return item;
  });
  scope.replaceChildren(...(entries.length ? entries : [node('p', '尚无撤销通知', 'muted')]));
  byId('revocation-current').textContent = `本光段 ${spanId}：${hand.status === 'clear' ? '现时可交接' : '现时不可交接'}`;
}
