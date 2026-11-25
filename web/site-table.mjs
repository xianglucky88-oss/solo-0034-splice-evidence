import { action, byId, node } from './dom.mjs';
import { blockers, credential, direction, eventStatus, loss, meter } from './format.mjs';

function observationCell(event, openEvidence, noticed) {
  const cell = node('td', event ? null : '—');
  if (event) {
    cell.append(action(event.event_id, () => openEvidence(event)), node('small', loss(2 * event.loss_mdb)));
    if (event.credential) cell.append(node('small', credential(event.credential)));
    const notice = event.notice || noticed;
    if (notice) cell.append(node('small', `撤销 ${notice.notice_id}`, 'error'));
  }
  return cell;
}

export function renderSites(work, openEvidence) {
  const notices = Object.fromEntries((work.handoff?.adopted || [])
    .filter((item) => item.notice).map((item) => [item.trace_id, item.notice]));
  byId('site-rows').replaceChildren(...work.sites.map((site) => {
    const row = node('tr');
    const point = node('td', site.site_id);
    point.append(node('small', meter(site.at_mm)));
    const status = node('td');
    const label = { pass: '通过', over: '超限', incomplete: '待补证' }[site.status];
    status.append(node('span', label, `status ${site.status === 'pass' ? 'good' : 'warn'}`));
    row.append(point, observationCell(site.observations.a, openEvidence, notices[site.observations.a?.trace_id]),
      observationCell(site.observations.b, openEvidence, notices[site.observations.b?.trace_id]),
      node('td', loss(site.mean_x2_mdb)), node('td', loss(2 * site.limit_mdb)), status);
    return row;
  }));
  const exceptions = byId('exceptions');
  exceptions.hidden = !work.budget.blockers.length;
  const issues = node('ul');
  for (const event of work.events.filter((value) => value.status !== 'matched')) {
    const issue = node('li');
    issue.append(action(`${direction[event.direction]} ${event.event_id} · ${eventStatus[event.status]}`, () => openEvidence(event)));
    issues.append(issue);
  }
  exceptions.replaceChildren(node('p', work.budget.blockers.map((value) => blockers[value]).join(' · '), 'error'), issues);
}

export function renderEvidence({ event, sites, revision, credential: source, notice }) {
  const list = byId('evidence');
  const fields = [ ['对应修订', revision], ['测量凭证', `${event.trace_id} · 第 ${event.line} 行`],
    ['事件编号', event.event_id], ['仪表里程', meter(event.at_mm)], ['事件损耗', loss(2 * event.loss_mdb)],
    ['归点结果', eventStatus[event.status]], ['候选点位', sites.map((site) => site.site_id).join('、') || '无'],
    ['仪表与校验批次', source ? credential(source) : '来源未注明'] ];
  if (notice) fields.push(['撤销通知', `${notice.notice_id} · ${notice.revoked_at}${notice.note ? ` · ${notice.note}` : ''}`]);
  if (event.along_mm) fields.splice(4, 0, ['统一里程', meter(event.along_mm.numerator / event.along_mm.denominator)]);
  list.replaceChildren(...fields.flatMap(([label, value]) => [node('dt', label), node('dd', value)]));
  byId('review-panel').hidden = false;
}
