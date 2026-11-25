import { byId, node, options } from './dom.mjs';
import { blockers, direction, loss } from './format.mjs';

const EXCLUSION = {
  pending_events: '存在待处置事件或缺失点位',
  no_unique_majority_group: '无唯一过半的最大相容组',
  outside_largest_group: '不在最大相容组内',
};

function traceOptions(receipts, side, selected) {
  const records = receipts.filter((item) => item.direction === side);
  const select = byId('review-traces');
  options(select, records.map((item) => [item.trace_id, item.trace_id]), null);
  for (const option of select.options) {
    if (selected.includes(option.value)) option.selected = true;
  }
}

export function renderReviewForm(work, receipts, archived, rosters) {
  const form = byId('review-panel-form');
  const directionSelect = byId('review-direction');
  if (work.mode === 'review') {
    directionSelect.value = work.review_direction;
  }
  const active = directionSelect.value || 'b';
  directionSelect.disabled = archived;
  byId('review-tolerance').disabled = archived;
  byId('review-traces').disabled = archived;
  byId('review-save').disabled = archived;
  byId('review-clear').disabled = archived;
  const current = archived && work.mode === 'review'
    ? work.review.roster.map((item) => ({ trace_id: item.trace_id, tolerance_mdb: item.tolerance_mdb }))
    : rosters?.[active] ?? [];
  if (current.length) byId('review-tolerance').value = current[0].tolerance_mdb;
  traceOptions(receipts, active, current.map((item) => item.trace_id));
  const note = byId('review-note');
  if (work.mode === 'review') {
    note.textContent = `当前为 ${direction[active]} 同向重测复核，改名单或容差将确认一次新修订`;
  } else {
    note.textContent = '登记三至九份同向凭证后启动一致性复核；新收件不会自动加入名单';
  }
  form.hidden = false;
}

function rosterTable(work) {
  const review = work.review;
  const table = node('table');
  const head = node('tr');
  head.append(...['凭证', '可入组', '结论 / 未入组原因'].map((text) => node('th', text)));
  const thead = node('thead');
  thead.append(head);
  const body = node('tbody');
  for (const item of review.roster) {
    const row = node('tr');
    const grouped = review.group.includes(item.trace_id);
    const verdict = grouped ? node('span', '组员', 'status good')
      : node('span', item.exclusion ? EXCLUSION[item.exclusion.code] : '未入组', 'status warn');
    row.append(node('td', item.trace_id), node('td', item.eligible ? '是' : '否'), (() => {
      const cell = node('td');
      cell.append(verdict);
      if (item.exclusion?.detail?.missing_sites?.length) {
        cell.append(node('small', `缺点位：${item.exclusion.detail.missing_sites.join('、')}`));
      }
      if (item.exclusion?.detail?.events?.length) {
        cell.append(node('small', `待处置事件：${item.exclusion.detail.events.map((e) => e.event_id).join('、')}`));
      }
      return cell;
    })());
    body.append(row);
  }
  table.append(thead, body);
  return table;
}

function memberTable(work) {
  const review = work.review;
  const counterId = work.active[review.counter_direction]?.trace_id;
  const wrap = node('div', null, 'scroll');
  const table = node('table');
  const head = node('tr');
  head.append(node('th', `组员凭证（对 ${counterId} 逐份核算）`));
  const siteIds = work.plan.sites.map((site) => site.site_id);
  for (const siteId of siteIds) head.append(node('th', siteId));
  head.append(node('th', '估算'), node('th', '实测'), node('th', '闭合差'), node('th', '结论'));
  const thead = node('thead'); thead.append(head);
  const body = node('tbody');
  for (const traceId of review.group) {
    const member = review.members[traceId];
    const row = node('tr');
    row.append(node('td', traceId));
    for (const site of member.sites) {
      row.append(node('td', site.mean_x2_mdb == null ? '—' : loss(site.mean_x2_mdb)));
    }
    row.append(node('td', loss(member.estimate_x2_mdb)), node('td', loss(member.measured_x2_mdb)),
      node('td', loss(member.residual_x2_mdb)),
      node('td', member.status === 'ready' ? node('span', '通过', 'status good') : node('span', '留置', 'status warn')));
    body.append(row);
  }
  table.append(thead, body);
  wrap.append(table);
  return wrap;
}

export function renderReviewResults(work) {
  const box = byId('review-results');
  if (work.mode !== 'review') {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  box.hidden = false;
  const review = work.review;
  box.replaceChildren();
  const head = node('div', null, 'review-head');
  const title = node('h2', `${direction[work.review_direction]}同向重测一致性复核`);
  const groupText = review.group.length
    ? node('span', `唯一过半最大组：${review.group.join('、')}（${review.group.length} / ${review.roster.length} 份）`,
      'status good')
    : node('span', '无组可签', 'status warn');
  head.append(title, groupText);
  box.append(head);
  if (work.budget.blockers.length) {
    box.append(node('p', work.budget.blockers.map((code) => blockers[code]).join(' · '), 'error'));
  }
  box.append(rosterTable(work), memberTable(work));
}

export function reviewSubmission(revision) {
  const directionValue = byId('review-direction').value;
  const traces = Array.from(byId('review-traces').selectedOptions).map((option) => ({ trace_id: option.value }));
  return {
    path: 'rosters',
    payload: {
      revision, direction: directionValue,
      tolerance_mdb: Number(byId('review-tolerance').value), traces,
    },
  };
}

export function reviewClear(revision) {
  return { path: 'rosters/clear', payload: { revision, direction: byId('review-direction').value } };
}
