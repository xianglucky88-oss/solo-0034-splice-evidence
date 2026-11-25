import { renderAdoption, selectedTraces } from './adoption.mjs';
import { get, post, postText, spanPath, spans } from './api.mjs';
import { loadDemo } from './demo.mjs';
import { byId, options } from './dom.mjs';
import { setupIngest } from './ingest.mjs';
import { renderChanges, renderReleases } from './release-list.mjs';
import { ruler } from './ruler.mjs';
import { renderEvidence, renderSites } from './site-table.mjs';
import { renderSummary } from './summary.mjs';

const draw = ruler(byId('ruler'));
const state = { id: null, revision: null, archived: null, version: 0, evidence: 0, compare: 0, pending: false };

function flash(message, error = false) {
  byId('flash').textContent = message;
  byId('flash').classList.toggle('error', error);
}

async function guarded(run) {
  if (state.pending) return;
  state.pending = true;
  try {
    await run();
  } catch (issue) {
    flash(issue.message, true);
  } finally {
    state.pending = false;
  }
}

async function evidence(event) {
  const { version, archived, id } = state;
  const index = ++state.evidence;
  const base = spanPath(id) + (archived == null ? '' : `/releases/${archived}`);
  try {
    const result = await get(`${base}/evidence/${event.trace_id}/${event.event_id}`);
    if (state.version === version && state.evidence === index && result.revision === state.revision) renderEvidence(result);
  } catch (issue) {
    if (state.version === version && state.evidence === index) flash(issue.message, true);
  }
}

async function show(id, archived = null) {
  const version = ++state.version;
  const base = spanPath(id);
  const detail = archived == null ? get(base) : get(`${base}/releases/${archived}`).then((result) => result.snapshot);
  const [work, receipts, releases] = await Promise.all([detail, get(`${base}/traces`), get(`${base}/releases`)]);
  if (state.version !== version) return;
  Object.assign(state, { id, archived, revision: work.revision });
  byId('span').value = id;
  byId('empty').hidden = true;
  byId('workspace').hidden = false;
  byId('live').hidden = archived == null;
  byId('import-trace').disabled = archived != null;
  byId('issue').disabled = archived != null || work.budget.status !== 'ready'
    || work.delivery.status !== 'ready';
  byId('review-panel').hidden = true;
  renderSummary(work, archived != null);
  renderSites(work, evidence);
  renderAdoption(work, receipts, archived != null);
  renderReleases(base, releases, (revision) => guarded(() => show(id, revision)));
  draw(work);
}

async function refreshSpans(preferred) {
  const items = await get(spans);
  options(byId('span'), items.map((item) => [item.span_id, `${item.span_id} · ${item.label}`]), preferred);
  byId('span').disabled = !items.length;
  if (items.length) await show(items.some((item) => item.span_id === preferred) ? preferred : items[0].span_id);
  else byId('empty').hidden = false;
}

const openIngest = setupIngest(async (type, text) => {
  if (type === 'plan') {
    const saved = await postText(spans, text);
    await refreshSpans(saved.plan.span_id);
    flash('已登记验收计划');
  } else {
    const id = state.id;
    const saved = await postText(`${spanPath(id)}/traces`, text);
    await show(id);
    flash(saved.replayed ? '该凭证已在收件档案中' : '凭证已收件，可在右侧采用');
  }
});

byId('new-plan').addEventListener('click', () => { if (!state.pending) openIngest('plan'); });
byId('import-trace').addEventListener('click', () => { if (!state.pending) openIngest('trace'); });
byId('span').addEventListener('change', (event) => {
  if (state.pending) { event.target.value = state.id; return; }
  const id = event.target.value;
  event.target.value = state.id;
  guarded(async () => { await show(id); flash(''); });
});
byId('demo').addEventListener('click', () => guarded(async () => {
  await refreshSpans(await loadDemo());
  flash('演示资料已入库');
}));
byId('live').addEventListener('click', () => guarded(() => show(state.id)));
byId('close-evidence').addEventListener('click', () => { state.evidence++; byId('review-panel').hidden = true; });
byId('selection').addEventListener('submit', (event) => {
  event.preventDefault();
  guarded(async () => {
    const id = state.id;
    await post(`${spanPath(id)}/selection`, selectedTraces(state.revision));
    await show(id);
    flash('采用凭证已保存');
  });
});
byId('issue').addEventListener('click', () => guarded(async () => {
  const id = state.id;
  const result = await post(`${spanPath(id)}/releases`, { revision: state.revision });
  await show(id, result.snapshot.revision);
  flash('当前修订已签发');
}));
byId('comparison').addEventListener('submit', async (event) => {
  event.preventDefault();
  const { id, version } = state;
  const index = ++state.compare;
  try {
    const changes = await get(`${spanPath(id)}/compare/${byId('from').value}/${byId('to').value}`);
    if (state.version === version && state.compare === index) renderChanges(changes);
  } catch (issue) {
    if (state.version === version && state.compare === index) flash(issue.message, true);
  }
});
await guarded(() => refreshSpans());
