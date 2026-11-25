import { renderAdoption, selectedTraces } from './adoption.mjs';
import { get, post, postText, spanPath, spans } from './api.mjs';
import { loadDemo } from './demo.mjs';
import { byId, options } from './dom.mjs';
import { setupIngest } from './ingest.mjs';
import { renderChanges, renderReleases } from './release-list.mjs';
import { ruler } from './ruler.mjs';
import { renderEvidence, renderSites } from './site-table.mjs';
import { renderSummary } from './summary.mjs';
import { reconcileOptions, renderReconcile, renderRelations, renderVersions } from './versions.mjs';

const draw = ruler(byId('ruler'));
const state = {
  id: null, version: 1, revision: null, archived: null, view: 0, evidence: 0, compare: 0,
  pending: false, versions: [], releasesByVersion: {},
};

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

const base = () => spanPath(state.id);
const versioned = () => state.version > 1;
const versionBase = () => (versioned() ? `${base()}/versions/${state.version}` : base());
const releaseBase = (revision) => `${versionBase()}/releases/${revision}`;

async function evidence(event) {
  const { view, archived, id, version } = state;
  const index = ++state.evidence;
  const prefix = archived == null ? versionBase() : releaseBase(archived);
  try {
    const result = await get(`${prefix}/evidence/${event.trace_id}/${event.event_id}`);
    if (state.view === view && state.evidence === index && result.revision === state.revision) renderEvidence(result);
  } catch (issue) {
    if (state.view === view && state.evidence === index) flash(issue.message, true);
  }
}

async function loadReleasesByVersion() {
  const map = { 1: await get(`${base()}/releases`) };
  for (const item of state.versions.filter((entry) => entry.plan_version > 1)) {
    map[item.plan_version] = await get(`${base()}/versions/${item.plan_version}/releases`);
  }
  state.releasesByVersion = map;
}

async function show(id, version = 1, archived = null) {
  const view = ++state.view;
  const detail = archived == null
    ? get(version > 1 ? `${base()}/versions/${version}` : base())
    : get(`${base()}${version > 1 ? `/versions/${version}` : ''}/releases/${archived}`).then((r) => r.snapshot);
  const [work, versions] = await Promise.all([
    detail,
    get(`${base()}/versions`).catch(() => [{ plan_version: 1, basis: '初始登记计划' }]),
  ]);
  state.id = id;
  state.versions = versions;
  await loadReleasesByVersion();
  const receipts = await get(`${version > 1 ? `${base()}/versions/${version}` : base()}/traces`);
  if (state.view !== view) return;
  Object.assign(state, { id, version, archived, revision: work.revision });
  byId('span').value = id;
  byId('empty').hidden = true;
  byId('workspace').hidden = false;
  byId('live').hidden = archived == null;
  byId('import-trace').disabled = archived != null;
  byId('issue').disabled = archived != null || work.budget.status !== 'ready';
  byId('review-panel').hidden = true;
  renderSummary(work, archived != null);
  renderSites(work, evidence);
  renderAdoption(work, receipts, archived != null);
  renderVersionChrome(work, version, archived != null);
  draw(work);
}

function renderVersionChrome(work, version, archived) {
  byId('version-note').textContent = version > 1 ? `计划版本 ${version}` : '计划版本 1（首版）';
  const multi = state.versions.length > 1;
  byId('version-panel').hidden = !multi;
  byId('reconcile-panel').hidden = !multi;
  if (multi) {
    renderVersions(state.versions, version, state.releasesByVersion, (number) => guarded(() => show(state.id, number)));
    if (version > 1) {
      get(`${base()}/versions/${version}/relations`).then(renderRelations);
    } else {
      renderRelations([]);
    }
    reconcileOptions(state.versions, state.releasesByVersion, [
      { side: 'left' }, { side: 'right' },
    ]);
  }
  const releases = state.releasesByVersion[version] || [];
  renderReleases(versionBase(), releases, (revision) => guarded(() => show(state.id, version, revision)));
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
    const saved = await postText(`${versionBase()}/traces`, text);
    await show(id, state.version);
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
byId('live').addEventListener('click', () => guarded(() => show(state.id, state.version)));
byId('close-evidence').addEventListener('click', () => { state.evidence++; byId('review-panel').hidden = true; });
byId('selection').addEventListener('submit', (event) => {
  event.preventDefault();
  guarded(async () => {
    const { id, version } = state;
    await post(`${versionBase()}/selection`, selectedTraces(state.revision));
    await show(id, version);
    flash('采用凭证已保存');
  });
});
byId('issue').addEventListener('click', () => guarded(async () => {
  const { id, version } = state;
  const result = await post(`${versionBase()}/releases`, { revision: state.revision });
  await show(id, version, result.snapshot.revision);
  flash('当前修订已签发');
}));
byId('comparison').addEventListener('submit', async (event) => {
  event.preventDefault();
  const { id, view } = state;
  const index = ++state.compare;
  try {
    const changes = await get(`${base()}/compare/${byId('from').value}/${byId('to').value}`);
    if (state.view === view && state.compare === index) renderChanges(changes);
  } catch (issue) {
    if (state.view === view && state.compare === index) flash(issue.message, true);
  }
});
byId('reconcile-form').addEventListener('submit', (event) => {
  event.preventDefault();
  guarded(async () => {
    const lv = byId('reconcile-left-version').value;
    const lr = byId('reconcile-left-revision').value;
    const rv = byId('reconcile-right-version').value;
    const rr = byId('reconcile-right-revision').value;
    const report = await get(`${base()}/reconcile/${lv}/${lr}/${rv}/${rr}`);
    renderReconcile(report);
  });
});
await guarded(() => refreshSpans());
