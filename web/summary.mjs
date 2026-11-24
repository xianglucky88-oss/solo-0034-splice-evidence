import { byId, node } from './dom.mjs';
import { blockers, loss, meter } from './format.mjs';

export function renderSummary(projection, archived) {
  const { plan, budget, sites, revision } = projection;
  byId('span-code').textContent = plan.span_id;
  byId('title').textContent = plan.label;
  byId('endpoints').textContent = `${plan.a_label} ↔ ${plan.b_label} · ${meter(plan.length_mm)}`;
  byId('revision-note').textContent = `${archived ? '签发快照' : '工作修订'} ${revision} · 由甲端起算`;
  const status = byId('release-status');
  status.textContent = archived ? '已签发' : budget.status === 'ready' ? '可签发' : '留置';
  status.className = `status ${archived || budget.status === 'ready' ? 'good' : 'warn'}`;
  status.title = budget.blockers.map((item) => blockers[item]).join('；');
  const joined = sites.filter((item) => item.mean_x2_mdb != null).length;
  const cards = [
    ['双端互证', `${joined} / ${sites.length}`, '已确认双端事件的接续点'],
    ['链路估算', loss(budget.estimate_x2_mdb), `固定损耗 ${loss(2 * plan.fixed_mdb)} 已计入`],
    ['实测总损耗', loss(budget.measured_x2_mdb), `链路限值 ${loss(2 * plan.link_limit_mdb)}`],
    ['闭合差', loss(budget.residual_x2_mdb), `绝对值限值 ${loss(2 * plan.residual_limit_mdb)}`],
  ];
  byId('metrics').replaceChildren(...cards.map(([label, value, note]) => {
    const tile = node('div', null, 'metric');
    tile.append(node('p', label, 'muted'), node('p', value, 'measure'), node('small', note));
    return tile;
  }));
}
