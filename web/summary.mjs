import { byId, node } from './dom.mjs';
import { blockers, direction, loss, meter, tierProblems } from './format.mjs';

function tierLine(tier) {
  if (!tier || tier.status === 'disabled') return '未启用限值档 · 按计划限值验收';
  if (tier.status === 'resolved') {
    return `限值档 ${tier.tier.tier_id} · ${tier.tier.label} · ${tier.tier.start_on} 起至 ${tier.tier.end_on} 止（不含）`;
  }
  const problems = tier.problems.map((item) => `${direction[item.direction]}${tierProblems[item.code]}`);
  return `限值档未能唯一命中：${problems.join('；')}`;
}

export function renderSummary(projection, archived) {
  const { plan, budget, sites, revision, tier } = projection;
  byId('span-code').textContent = plan.span_id;
  byId('title').textContent = plan.label;
  byId('endpoints').textContent = `${plan.a_label} ↔ ${plan.b_label} · ${meter(plan.length_mm)}`;
  byId('revision-note').textContent = `${archived ? '签发快照' : '工作修订'} ${revision} · 由甲端起算`;
  byId('tier-note').textContent = tierLine(tier);
  byId('tier-note').className = tier && tier.status === 'resolved' ? 'muted' : 'muted warn-text';
  const status = byId('release-status');
  status.textContent = archived ? '已签发' : budget.status === 'ready' ? '可签发' : '留置';
  status.className = `status ${archived || budget.status === 'ready' ? 'good' : 'warn'}`;
  status.title = budget.blockers.map((item) => blockers[item]).join('；');
  const joined = sites.filter((item) => item.mean_x2_mdb != null).length;
  const linkLimit = budget.link_limit_mdb ?? plan.link_limit_mdb;
  const residualLimit = budget.residual_limit_mdb ?? plan.residual_limit_mdb;
  const cards = [
    ['双端互证', `${joined} / ${sites.length}`, '已确认双端事件的接续点'],
    ['链路估算', loss(budget.estimate_x2_mdb), `固定损耗 ${loss(2 * plan.fixed_mdb)} 已计入`],
    ['实测总损耗', loss(budget.measured_x2_mdb), `链路限值 ${loss(2 * linkLimit)}`],
    ['闭合差', loss(budget.residual_x2_mdb), `绝对值限值 ${loss(2 * residualLimit)}`],
  ];
  byId('metrics').replaceChildren(...cards.map(([label, value, note]) => {
    const tile = node('div', null, 'metric');
    tile.append(node('p', label, 'muted'), node('p', value, 'measure'), node('small', note));
    return tile;
  }));
}
