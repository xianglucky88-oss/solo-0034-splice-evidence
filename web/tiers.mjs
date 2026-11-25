import { byId, node, options } from './dom.mjs';
import { blockers, loss } from './format.mjs';

function tierItem(tier, active) {
  const item = node('div', active ? 'release-item active-tier' : 'release-item');
  item.append(node('strong', `${tier.tier_id}${active ? ' · 当前' : ''}`),
    node('small', `${tier.start_on} 至 ${tier.end_on}（不含） · 链路 ${loss(2 * tier.link_limit_mdb)} · 闭合 ${loss(2 * tier.residual_limit_mdb)}`));
  return item;
}

export function renderTiers(work, archive, archived) {
  const container = byId('tiers');
  const tier = work.tier;
  if (tier.status === 'disabled') {
    container.replaceChildren(node('p', '该光段未启用限值档，验收沿用计划限值。', 'muted'));
    return;
  }
  const tiers = archived && tier.tier ? [tier.tier] : (archive?.current?.tiers || []);
  const head = archived
    ? node('p', `签发所用档 ${tier.tier_id} · 登记版本 ${tier.registry_version}`, 'muted')
    : tier.status === 'resolved'
      ? node('p', `当前命中 ${tier.tier_id} · 登记版本 ${tier.registry_version}`, 'muted')
      : node('p', '尚未唯一命中限值档，验收暂按留置处理。', 'error');
  const list = node('div');
  for (const item of tiers) list.append(tierItem(item, !archived && item.tier_id === tier.tier_id));
  container.replaceChildren(head, list);
  if (!archived && tier.problems.length) {
    const issues = node('ul');
    for (const problem of tier.problems) issues.append(node('li', problem.message));
    container.append(issues);
  }
}

export function renderRejudgeOptions(rejudgeOptions) {
  const form = byId('rejudge');
  form.hidden = !rejudgeOptions.length;
  options(byId('rejudge-tier'),
    rejudgeOptions.map((item) => [`${item.registry_version}:${item.tier_id}`,
      `${item.tier_id} · 登记版本 ${item.registry_version}`]));
}

function verdict(part) {
  if (part.judgment.status === 'ready') return '通过';
  return `暂缓（${part.judgment.blockers.map((item) => blockers[item]).join('；')}）`;
}

function line(label, part) {
  const original = part.original.status === 'ready' ? '通过' : '暂缓';
  return `${label}：原结论 ${original} · 原件档 ${part.tier?.tier_id || '未启用'} · 复核 ${verdict(part)} · `
    + `摘要 ${part.digest.slice(0, 12)}`;
}

export function renderRejudge(result) {
  const display = byId('changes');
  const { before, after } = result;
  display.replaceChildren(
    node('p', `按限值档 ${result.tier_id} · 登记版本 ${result.registry_version} 复核两件`),
    node('p', line('原版本', before), 'muted'),
    node('p', line('新版本', after), 'muted'),
    node('p', `复核闭合差 ${loss(before.judgment.residual_x2_mdb)} → ${loss(after.judgment.residual_x2_mdb)}`, 'muted'));
  display.hidden = false;
}
