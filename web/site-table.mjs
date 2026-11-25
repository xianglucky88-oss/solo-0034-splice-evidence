import { action, byId, node } from './dom.mjs';
import { blockers, calibrationStatus, direction, eventBasis, eventStatus, loss, markRole, meter } from './format.mjs';

function observationCell(event, openEvidence) {
  const cell = node('td', event ? null : '—');
  if (event) {
    cell.append(action(event.event_id, () => openEvidence(event)), node('small', loss(2 * event.loss_mdb)));
  }
  return cell;
}

export function renderSites(work, openEvidence) {
  byId('site-rows').replaceChildren(...work.sites.map((site) => {
    const row = node('tr');
    const point = node('td', site.site_id);
    point.append(node('small', meter(site.at_mm)));
    const status = node('td');
    const label = { pass: '通过', over: '超限', incomplete: '待补证' }[site.status];
    status.append(node('span', label, `status ${site.status === 'pass' ? 'good' : 'warn'}`));
    row.append(point, observationCell(site.observations.a, openEvidence), observationCell(site.observations.b, openEvidence),
      node('td', loss(site.mean_x2_mdb)), node('td', loss(2 * site.limit_mdb)), status);
    return row;
  }));
  renderCalibrations(work);
  const exceptions = byId('exceptions');
  exceptions.hidden = !work.budget.blockers.length;
  const issues = node('ul');
  for (const event of work.events.filter((value) => value.status !== 'matched')) {
    const reason = event.basis ? ` · ${eventBasis[event.basis]}` : '';
    const issue = node('li');
    issue.append(action(`${direction[event.direction]} ${event.event_id} · ${eventStatus[event.status] || event.status}${reason}`,
      () => openEvidence(event)));
    issues.append(issue);
  }
  exceptions.replaceChildren(node('p', work.budget.blockers.map((value) => blockers[value]).join(' · '), 'error'), issues);
}

function renderCalibrations(work) {
  const calibrations = work.calibrations || [];
  const target = byId('calibrations');
  target.hidden = !calibrations.length;
  target.replaceChildren(...calibrations.map((entry) => {
    const card = node('div', null, 'calibration');
    const head = node('p');
    head.append(node('strong', `${direction[entry.direction]} ${entry.trace_id}`), ' · ',
      node('span', calibrationStatus[entry.status], `status ${entry.status === 'held' ? 'warn' : 'good'}`));
    card.append(head);
    if (entry.status !== 'legacy') {
      const list = node('ol');
      for (const mark of entry.marks) {
        const item = node('li');
        item.append(node('span', `${markRole[mark.role]} ${meter(mark.read_mm)}`), ' → ',
          node('span', mark.at_mm ? meter(mark.at_mm.numerator / mark.at_mm.denominator) : '—', 'muted'));
        list.append(item);
      }
      card.append(list);
    } else {
      card.append(node('p', '计划未设中间标记，按近远端两点换算。', 'muted'));
    }
    return card;
  }));
}

export function renderEvidence({ event, sites, revision, calibration }) {
  const list = byId('evidence');
  list.replaceChildren();
  const fields = [ ['对应修订', revision], ['测量凭证', `${event.trace_id} · 第 ${event.line} 行`],
    ['事件编号', event.event_id], ['仪表里程', meter(event.at_mm)], ['事件损耗', loss(2 * event.loss_mdb)],
    ['归点结果', eventStatus[event.status] || event.status] ];
  if (event.along_mm) fields.splice(4, 0, ['统一里程', meter(event.along_mm.numerator / event.along_mm.denominator)]);
  fields.push(['候选点位', sites.map((site) => site.site_id).join('、') || '无']);
  if (event.basis) fields.push(['判定依据', eventBasis[event.basis] || event.basis]);
  if (calibration) {
    fields.push(['该向换算', calibrationStatus[calibration.status]]);
    const marks = calibration.marks.map((mark) => `${markRole[mark.role]} ${meter(mark.read_mm)} → ` +
      (mark.at_mm ? meter(mark.at_mm.numerator / mark.at_mm.denominator) : '—')).join('；');
    fields.push(['三处标记', marks || '无']);
  }
  list.replaceChildren(...fields.flatMap(([label, value]) => [node('dt', label), node('dd', value)]));
  byId('review-panel').hidden = false;
}
