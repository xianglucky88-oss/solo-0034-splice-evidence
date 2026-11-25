import { byId, node } from './dom.mjs';
import { blockers, loss, meter } from './format.mjs';

const length = (mm) => mm == null ? '—' : meter(mm);
const measured = (mdb) => mdb == null ? '—' : loss(2 * mdb);

export function renderRoute(work, archived) {
  byId('route-code').textContent = work.route_id;
  byId('route-title').textContent = work.label;
  byId('route-endpoints').textContent = `${work.plan.start.box}/${work.plan.start.port} ↔ ${work.plan.end.box}/${work.plan.end.port}`;
  byId('route-note').textContent = `${archived ? '验收快照' : '整路核算'} · 由起点端口起算`;
  const status = byId('route-status');
  status.textContent = archived ? '已验收' : work.budget.status === 'ready' ? '可验收' : '留置';
  status.className = `status ${archived || work.budget.status === 'ready' ? 'good' : 'warn'}`;
  status.title = work.budget.blockers.map((item) => blockers[item] || item).join('；');
  const budget = work.budget;
  const cards = [
    ['拼接光段', `${work.segments.length} 段 / ${work.bridges.length} 桥接`, `整路长度 ${length(budget.total_length_mm)}`],
    ['全路估算', loss(budget.estimate_x2_mdb), `含各段与桥接估算 · 限值 ${loss(2 * budget.link_limit_mdb)}`],
    ['全路实测均值', loss(budget.measured_x2_mdb), `各向 ${measured(budget.measured_a_mdb)} + ${measured(budget.measured_b_mdb)}`],
    ['闭合差', loss(budget.residual_x2_mdb), `绝对值限值 ${loss(2 * budget.residual_limit_mdb)}`],
  ];
  byId('route-metrics').replaceChildren(...cards.map(([label, value, note]) => {
    const tile = node('div', null, 'metric');
    tile.append(node('p', label, 'muted'), node('p', value, 'measure'), node('small', note));
    return tile;
  }));

  byId('segment-rows').replaceChildren(...work.segments.map((segment) => {
    const row = node('tr');
    row.append(
      node('td', segment.order == null ? '—' : String(segment.order)),
      node('td', segment.span_id),
      node('td', segment.orientation === 'reverse' ? '反向' : '正向'),
      node('td', `${length(segment.start_mm)} → ${length(segment.end_mm)}`),
      node('td', measured(segment.forward_mdb)),
      node('td', measured(segment.backward_mdb)),
      node('td', loss(segment.estimate_x2_mdb)),
      node('td', `修订 ${segment.revision}`),
    );
    return row;
  }));

  byId('bridge-rows').replaceChildren(...work.bridges.map((bridge) => {
    const row = node('tr');
    const route = node('td', `${bridge.from.box}/${bridge.from.port} → ${bridge.to.box}/${bridge.to.port}`);
    if (bridge.reversed) route.append(node('small', '记录方向与行进方向相反'));
    if (bridge.record_count > 1) route.append(node('small', `同一实物连接共 ${bridge.record_count} 份记录，只计一次`));
    row.append(
      node('td', bridge.order == null ? '—' : String(bridge.order)),
      route,
      node('td', `${length(bridge.start_mm)} → ${length(bridge.end_mm)}`),
      node('td', length(bridge.gap_mm)),
      node('td', measured(bridge.forward_mdb)),
      node('td', measured(bridge.backward_mdb)),
      node('td', loss(2 * bridge.estimate_mdb)),
    );
    return row;
  }));

  byId('route-site-rows').replaceChildren(...work.sites.map((site) => {
    const row = node('tr');
    const point = node('td', `${site.span_id} · ${site.site_id}`);
    point.append(node('small', length(site.at_mm)));
    const status = node('td');
    const label = { pass: '通过', over: '超限', incomplete: '待补证' }[site.status] || site.status;
    status.append(node('span', label, `status ${site.status === 'pass' ? 'good' : 'warn'}`));
    const cell = (event) => {
      const cell = node('td');
      if (!event) { cell.textContent = '—'; return cell; }
      const link = node('a', `${event.event_id} · ${event.source_side === 'a' ? '甲' : '乙'}`);
      link.href = `/api/splice/spans/${encodeURIComponent(site.span_id)}/releases/${site.revision}`
        + `/evidence/${encodeURIComponent(event.trace_id)}/${encodeURIComponent(event.event_id)}`;
      link.target = '_blank';
      link.rel = 'noopener';
      link.title = `原凭证 ${event.trace_id} 第 ${event.line} 行`;
      cell.append(link);
      return cell;
    };
    row.append(point, cell(site.observations.a), cell(site.observations.b), node('td', loss(site.mean_x2_mdb)),
      node('td', loss(2 * site.limit_mdb)), status);
    return row;
  }));

  const exceptions = byId('route-exceptions');
  const list = node('ul');
  for (const issue of budget.issues || []) list.append(node('li', issue.detail));
  exceptions.hidden = !list.childElementCount;
  exceptions.replaceChildren(
    node('p', budget.blockers.map((item) => blockers[item] || item).join(' · '), 'error'), list);
}

export function renderRouteReleases(path, releases, open) {
  const entries = releases.map(({ digest, sequence }) => {
    const row = node('div', null, 'release-item');
    const button = node('button', `验收 ${sequence}`, 'link-button');
    button.type = 'button';
    button.title = `SHA-256 ${digest}`;
    button.addEventListener('click', () => open(digest));
    const source = `${path}/releases/${digest}`;
    const json = node('a', 'JSON');
    json.href = source;
    json.target = '_blank';
    json.rel = 'noopener';
    const csv = node('a', '整路 CSV');
    csv.href = `${source}/parts.csv`;
    csv.target = '_blank';
    csv.rel = 'noopener';
    row.append(button, json, csv);
    return row;
  });
  byId('route-releases').replaceChildren(...(entries.length ? entries : [node('p', '尚无整路验收记录', 'muted')]));
}
