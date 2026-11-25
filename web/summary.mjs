import { byId, node } from './dom.mjs';
import { blockers, loss, meter, mdb } from './format.mjs';

export function renderSummary(projection, archived) {
  const { plan, budget, delivery, sites, revision } = projection;
  byId('span-code').textContent = plan.span_id;
  byId('title').textContent = plan.label;
  byId('endpoints').textContent = `${plan.a_label} ↔ ${plan.b_label} · ${meter(plan.length_mm)}`;
  byId('revision-note').textContent = `${archived ? '签发快照' : '工作修订'} ${revision} · 由甲端起算`;
  const status = byId('release-status');
  const ready = budget.status === 'ready' && delivery.status === 'ready';
  status.textContent = archived ? '已签发' : ready ? '可签发' : '留置';
  status.className = `status ${archived || ready ? 'good' : 'warn'}`;
  status.title = [...budget.blockers, ...delivery.blockers].map((item) => blockers[item] || item).join('；');
  const joined = sites.filter((item) => item.mean_x2_mdb != null).length;
  const cards = [
    ['双端互证', `${joined} / ${sites.length}`, '已确认双端事件的接续点'],
    ['链路估算', loss(budget.estimate_x2_mdb), `固定损耗 ${loss(2 * plan.fixed_mdb)} 已计入`],
    ['实测总损耗', loss(budget.measured_x2_mdb), `链路限值 ${loss(2 * plan.link_limit_mdb)}`],
    ['闭合差', loss(budget.residual_x2_mdb), `绝对值限值 ${loss(2 * plan.residual_limit_mdb)}`],
    ['整数交割', delivery.status === 'ready' ? '就绪' : '留置',
      delivery.status === 'ready'
        ? `入账实测 ${mdb(delivery.measured_x2_mdb)} · 闭合 ${mdb(delivery.residual_x2_mdb)}`
        : (delivery.blockers.map((item) => blockers[item] || item).join('；') || '等待双端证据')],
  ];
  byId('metrics').replaceChildren(...cards.map(([label, value, note]) => {
    const tile = node('div', null, 'metric');
    tile.append(node('p', label, 'muted'), node('p', value, 'measure'), node('small', note));
    return tile;
  }));
}
