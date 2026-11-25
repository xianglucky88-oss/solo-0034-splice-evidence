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
  byId('rejudge').hidden = true;
}

function limitShift(before, after) {
  if (before == null || after == null) return '未判限值';
  if (before === after) return `限值不变 ${loss(2 * before)}`;
  return `限值 ${loss(2 * before)} → ${loss(2 * after)}`;
}

export function renderChanges(changes) {
  const display = byId('changes');
  const measurement = node('ul');
  for (const row of changes.measurement.sites) {
    const label = row.delta_x2_mdb === 0 ? '测量不变，证据有变化' : `测量变化 ${loss(row.delta_x2_mdb)}`;
    measurement.append(node('li', `${row.site_id} · ${label}`));
  }
  const limits = node('ul');
  for (const row of changes.limits.sites) {
    if (row.before_mdb === row.after_mdb) continue;
    limits.append(node('li', `${row.site_id} · ${limitShift(row.before_mdb, row.after_mdb)}`));
  }
  if (changes.limits.link.before_mdb !== changes.limits.link.after_mdb) {
    limits.append(node('li', `链路 · ${limitShift(changes.limits.link.before_mdb, changes.limits.link.after_mdb)}`));
  }
  if (changes.limits.residual.before_mdb !== changes.limits.residual.after_mdb) {
    limits.append(node('li', `闭合差 · ${limitShift(changes.limits.residual.before_mdb, changes.limits.residual.after_mdb)}`));
  }
  if (!limits.childNodes.length) limits.append(node('li', '两份签件的限值一致', 'muted'));
  const tierBefore = changes.tier_before?.tier_id || '未启用限值档';
  const tierAfter = changes.tier_after?.tier_id || '未启用限值档';
  display.replaceChildren(
    node('p', `修订 ${changes.from} → ${changes.to} · ${changes.sites.length} 个点位有变化`),
    node('p', `限值档 ${tierBefore} → ${tierAfter}`, 'muted'),
    node('p', '测量与核算', 'muted'), measurement,
    node('p', `实测 ${loss(changes.measurement.measured_before_mdb)} → ${loss(changes.measurement.measured_after_mdb)} · `
      + `估计 ${loss(changes.accounting.estimate_before_mdb)} → ${loss(changes.accounting.estimate_after_mdb)}`, 'muted'),
    node('p', `闭合差 ${loss(changes.accounting.residual_before_mdb)} → ${loss(changes.accounting.residual_after_mdb)}`, 'muted'),
    node('p', '限值变化', 'muted'), limits);
  display.hidden = false;
}
