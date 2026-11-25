import { action, byId, node, options } from './dom.mjs';
import { credential, direction, handoff, loss } from './format.mjs';

function resource(href, title) {
  const link = node('a', title);
  link.href = href;
  link.target = '_blank';
  link.rel = 'noopener';
  return link;
}

export function renderReleases(path, releases, open) {
  const entries = releases.map(({ revision, digest, handoff: hand }) => {
    const row = node('div', null, 'release-item');
    const button = action(`修订 ${revision}`, () => open(revision));
    button.title = `SHA-256 ${digest}`;
    const source = `${path}/releases/${revision}`;
    const status = node('span', handoff[hand?.status || 'clear'],
      `status ${hand && hand.status !== 'clear' ? 'warn' : 'good'}`);
    const affected = (hand?.affected || []).map((item) => `${direction[item.side]} ${credential(item)}`);
    const note = affected.length ? node('small', `撤销 ${affected.join('、')} · 原凭证与历史结论保留`, 'error') : null;
    row.append(button, status, resource(source, 'JSON'), resource(`${source}/sites.csv`, '接续点 CSV'));
    if (note) row.append(note);
    return row;
  });
  byId('releases').replaceChildren(...(entries.length ? entries : [node('p', '尚无签发记录', 'muted')]));
  byId('comparison').hidden = releases.length < 2;
  const versions = releases.map(({ revision }) => [revision, `修订 ${revision}`]);
  options(byId('to'), versions, releases[0]?.revision);
  options(byId('from'), versions, releases[1]?.revision);
  byId('changes').hidden = true;
}

export function renderChanges(changes) {
  const display = byId('changes');
  const list = node('ul');
  for (const site of changes.sites) {
    const label = site.delta_x2_mdb === 0 ? '损耗不变，证据有变化' : `变化 ${loss(site.delta_x2_mdb)}`;
    list.append(node('li', `${site.site_id} · ${label}`));
  }
  const blocked = (hand) => (hand?.affected || []).map((item) => `${direction[item.side]} ${credential(item)}`)
    .join('、') || '无';
  display.replaceChildren(node('p', `修订 ${changes.from} → ${changes.to} · ${changes.sites.length} 个点位有变化`),
    node('p', `闭合差 ${loss(changes.before.residual_x2_mdb)} → ${loss(changes.after.residual_x2_mdb)}`, 'muted'),
    node('p', `现时交接：${handoff[changes.handoff_before?.status || 'clear']} → ${handoff[changes.handoff_after?.status || 'clear']}`, 'muted'),
    node('p', `受影响凭证：${blocked(changes.handoff_before)} → ${blocked(changes.handoff_after)}`, 'muted'), list);
  display.hidden = false;
}
