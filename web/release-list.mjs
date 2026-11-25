import { action, byId, node, options } from './dom.mjs';
import { loss } from './format.mjs';

function resource(href, title) {
  const link = node('a', title);
  link.href = href;
  link.target = '_blank';
  link.rel = 'noopener';
  return link;
}

export function renderReleases(path, releases, open) {
  const entries = releases.map(({ revision, digest }) => {
    const row = node('div', null, 'release-item');
    const button = action(`修订 ${revision}`, () => open(revision));
    button.title = `SHA-256 ${digest}`;
    const source = `${path}/releases/${revision}`;
    row.append(button, resource(source, 'JSON'), resource(`${source}/sites.csv`, '接续点 CSV'));
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
  if (changes.mode === 'review') {
    const list = node('ul');
    for (const member of changes.members) {
      const label = member.kind === 'member_added' ? '新增组员'
        : member.kind === 'member_removed' ? '移除组员'
        : `闭合差 ${loss(member.residual_before)} → ${loss(member.residual_after)}`;
      list.append(node('li', `${member.trace_id} · ${label}`));
    }
    display.replaceChildren(
      node('p', `修订 ${changes.from} → ${changes.to} · 同向复核 ${changes.members.length} 名组员有变化`),
      node('p', `最大组 ${changes.review_before.group.join('、') || '无'} → ${changes.review_after.group.join('、') || '无'}`,
        'muted'), list);
    display.hidden = false;
    return;
  }
  const list = node('ul');
  for (const site of changes.sites) {
    const label = site.delta_x2_mdb === 0 ? '损耗不变，证据有变化' : `变化 ${loss(site.delta_x2_mdb)}`;
    list.append(node('li', `${site.site_id} · ${label}`));
  }
  display.replaceChildren(node('p', `修订 ${changes.from} → ${changes.to} · ${changes.sites.length} 个点位有变化`),
    node('p', `闭合差 ${loss(changes.before.residual_x2_mdb)} → ${loss(changes.after.residual_x2_mdb)}`, 'muted'), list);
  display.hidden = false;
}
