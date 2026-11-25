import { action, byId, node, options } from './dom.mjs';
import { loss } from './format.mjs';

const RELATION_LABEL = {
  split: '拆分', merge: '合并', continue: '沿用', added: '新增', retired: '退役',
};

function relationBadge(kind) {
  return node('span', RELATION_LABEL[kind] || kind, 'status');
}

function siteList(sites) {
  return sites.length ? sites.map((site) => site.site_id).join('、') : '—';
}

function lossCell(value) {
  return node('td', value == null ? '—' : loss(value));
}

export function renderVersions(versions, current, releasesByVersion, onOpen) {
  const panel = byId('versions');
  panel.replaceChildren();
  const head = node('div', null, 'panel-head');
  head.append(node('h2', '计划版本与拆并关系'));
  panel.append(head);
  const body = node('div', null, 'releases');
  for (const version of versions) {
    const number = version.plan_version;
    const row = node('div', null, 'release-item');
    const button = action(`版本 ${number}${number === current ? '（当前）' : ''}`, () => onOpen(number));
    const note = node('small', version.basis, 'muted');
    row.append(button, note);
    const issued = releasesByVersion[number] || [];
    if (issued.length) {
      const tags = issued.map((item) => node('span', `签件 r${item.revision}`, 'status'));
      row.append(...tags);
    }
    body.append(row);
  }
  panel.append(body);
}

export function renderRelations(relations) {
  const box = byId('version-relations');
  box.replaceChildren();
  if (!relations || !relations.length) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const list = node('ul');
  for (const item of relations) {
    const line = node('li');
    line.append(
      relationBadge(item.relation),
      node('span', ` ${siteList(item.from_sites)} → ${siteList(item.to_sites)}`),
    );
    list.append(line);
  }
  box.replaceChildren(node('p', '确认的工程关系', 'muted'), list);
}

export function renderReconcile(report) {
  const box = byId('reconcile-result');
  box.hidden = false;
  const table = node('table');
  const head = node('thead');
  const headRow = node('tr');
  ['关系', '本版点位', '本版损耗合计', '对方点位', '对方损耗合计', '差额', '变更次数'].forEach((text) => {
    headRow.append(node('th', text));
  });
  head.append(headRow);
  table.append(head);
  const body = node('tbody');
  const draw = (group, sideTag) => {
    const row = node('tr');
    const kinds = node('td');
    kinds.append(...group.relations.map(relationBadge));
    if (sideTag) kinds.append(node('br'), node('small', sideTag));
    row.append(
      kinds,
      node('td', siteList(group.left_sites)), lossCell(group.left_loss_total_x2_mdb),
      node('td', siteList(group.right_sites)), lossCell(group.right_loss_total_x2_mdb),
      lossCell(group.delta_x2_mdb), node('td', String(group.change_count)),
    );
    body.append(row);
  };
  report.groups.forEach((group) => draw(group));
  report.single_side_groups.forEach((group) => draw(group, group.side === 'left' ? '仅本版（退役）' : '仅对方（新增）'));
  table.append(body);
  box.replaceChildren(
    node('p', `版本 ${report.left.plan_version} 签件 r${report.left.revision} → 版本 ${report.right.plan_version} 签件 r${report.right.revision}`, 'muted'),
    table,
  );
}

export function reconcileOptions(versions, releasesByVersion, selects) {
  for (const { side, versionKey, revisionKey } of selects) {
    const versionSelect = byId(`reconcile-${side}-version`);
    const revisionSelect = byId(`reconcile-${side}-revision`);
    options(versionSelect, versions.map((item) => [item.plan_version, `版本 ${item.plan_version}`]));
    const syncRevisions = () => {
      const version = Number(versionSelect.value);
      const releases = releasesByVersion[version] || [];
      options(revisionSelect, releases.map((item) => [item.revision, `签件 r${item.revision}`]));
    };
    versionSelect.addEventListener('change', syncRevisions);
    syncRevisions();
  }
}
