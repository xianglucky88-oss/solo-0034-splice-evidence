import { byId } from './dom.mjs';

export function setupIngest(submit) {
  const dialog = byId('ingest');
  const form = byId('ingest-form');
  const text = byId('json');
  const input = byId('file');
  const error = byId('ingest-error');
  let kind;
  let pending = false;
  byId('cancel').addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', (event) => { if (pending) event.preventDefault(); });
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 1024 * 1024) {
      error.textContent = '单个文件不能超过 1 MiB';
      return;
    }
    try {
      const contents = await file.text();
      if (dialog.open && input.files[0] === file) text.value = contents;
    } catch {
      error.textContent = '文件无法读取，请重新选择';
    }
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (pending) return;
    pending = true;
    error.textContent = '';
    const buttons = form.querySelectorAll('button');
    buttons.forEach((button) => { button.disabled = true; });
    try {
      await submit(kind, text.value);
      dialog.close();
    } catch (issue) {
      error.textContent = issue.message;
    } finally {
      pending = false;
      buttons.forEach((button) => { button.disabled = false; });
    }
  });
  return (type) => {
    kind = type;
    form.reset();
    error.textContent = '';
    byId('ingest-title').textContent = type === 'plan' ? '登记验收计划' : '导入仪表凭证';
    byId('sample-link').href = type === 'plan' ? '/examples/plan.json' : '/examples/a.json';
    byId('sample-note').textContent = type === 'trace'
      ? '凭证应同时注明仪表编号与校验批次；缺少时按来源未注明沿用原流程。'
      : '';
    dialog.showModal();
    text.focus();
  };
}
