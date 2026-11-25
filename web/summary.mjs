import { byId, node } from './dom.mjs';
import { blockers, credential, direction, loss, meter } from './format.mjs';

export function renderSummary(projection, archived) {
  const { plan, budget, sites, revision, handoff: hand } = projection;
  byId('span-code').textContent = plan.span_id;
  byId('title').textContent = plan.label;
  byId('endpoints').textContent = `${plan.a_label} ↔ ${plan.b_label} · ${meter(plan.length_mm)}`;
  byId('revision-note').textContent = `${archived ? '签发快照' : '工作修订'} ${revision} · 由甲端起算`;
  const hold = hand ? hand.status !== 'clear' : budget.blockers.includes('revoked_calibration');
  const state = byId('release-status');
  state.textContent = hold ? '现时不可交接' : archived ? '已签发' : budget.status === 'ready' ? '可签发' : '留置';
  state.className = `status ${hold ? 'warn' : archived || budget.status === 'ready' ? 'good' : 'warn'}`;
  state.title = budget.blockers.map((item) => blockers[item]).join('；');
  byId('handoff').textContent = hand
    ? `${hand.affected.length ? '现时不可交接' : archived ? '已签发 · 现时仍可交接' : '现时可交接'}${hand.affected.length ? ` · 受影响凭证 ${hand.affected.map((item) => `${direction[item.side]} ${credential(item)}`).join('、')}` : ''}`
    : '来源未注明的旧收件沿用原流程，不按校验批次撤销';
  byId('handoff').className = `muted ${hold ? 'error' : ''}`;
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
  const adopted = (hand && hand.adopted) || [];
  byId('adopted-source').replaceChildren(...(adopted.length ? adopted.flatMap((item) => [
    node('dt', direction[item.side]),
    node('dd', `${credential(item)}${item.notice ? ` · 已撤销 ${item.notice.notice_id}` : ''}`, item.notice ? 'error' : null),
  ]) : [node('p', '尚未采用任何凭证', 'muted')]));
}
