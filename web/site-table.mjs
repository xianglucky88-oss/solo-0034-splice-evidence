import { action, byId, node } from './dom.mjs';
import { blockers, direction, eventStatus, loss, meter, mdb } from './format.mjs';

function observationCell(event, booked, openEvidence) {
  const cell = node('td', event ? null : '—');
  if (event) {
    cell.append(action(event.event_id, () => openEvidence(event)), node('small', loss(2 * event.loss_mdb)));
    if (booked && booked.booked_mdb !== event.loss_mdb) {
      cell.append(node('small', `交割 ${mdb(booked.booked_mdb)}`, 'booked'));
    }
  }
  return cell;
}

export function renderSites(work, openEvidence) {
  const bookedSites = new Map(work.delivery.sites.map((site) => [site.site_id, site]));
  byId('site-rows').replaceChildren(...work.sites.map((site) => {
    const row = node('tr');
    const point = node('td', site.site_id);
    point.append(node('small', meter(site.at_mm)));
    const status = node('td');
    const label = { pass: '通过', over: '超限', incomplete: '待补证' }[site.status];
    status.append(node('span', label, `status ${site.status === 'pass' ? 'good' : 'warn'}`));
    const booked = bookedSites.get(site.site_id);
    row.append(
      point,
      observationCell(site.observations.a, booked?.observations.a, openEvidence),
      observationCell(site.observations.b, booked?.observations.b, openEvidence),
      node('td', loss(site.mean_x2_mdb)),
      node('td', booked ? mdb(booked.mean_x2_mdb) : '—'),
      node('td', loss(2 * site.limit_mdb)), status);
    return row;
  }));
  const exceptions = byId('exceptions');
  const allBlockers = [...work.budget.blockers, ...work.delivery.blockers];
  exceptions.hidden = !allBlockers.length;
  const issues = node('ul');
  for (const event of work.events.filter((value) => value.status !== 'matched')) {
    const issue = node('li');
    issue.append(action(`${direction[event.direction]} ${event.event_id} · ${eventStatus[event.status]}`, () => openEvidence(event)));
    issues.append(issue);
  }
  exceptions.replaceChildren(node('p', allBlockers.map((value) => blockers[value] || value).join(' · '), 'error'), issues);
}

export function renderEvidence({ event, sites, revision }) {
  const list = byId('evidence');
  const fields = [ ['对应修订', revision], ['测量凭证', `${event.trace_id} · 第 ${event.line} 行`],
    ['事件编号', event.event_id], ['仪表里程', meter(event.at_mm)], ['事件损耗', loss(2 * event.loss_mdb)],
    ['归点结果', eventStatus[event.status]], ['候选点位', sites.map((site) => site.site_id).join('、') || '无'] ];
  if (event.along_mm) fields.splice(4, 0, ['统一里程', meter(event.along_mm.numerator / event.along_mm.denominator)]);
  list.replaceChildren(...fields.flatMap(([label, value]) => [node('dt', label), node('dd', value)]));
  byId('review-panel').hidden = false;
}
