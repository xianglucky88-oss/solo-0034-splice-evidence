export const meter = (mm) => `${(mm / 1000).toLocaleString('zh-CN', { maximumFractionDigits: 3 })} 米`;
export const loss = (doubled) => doubled == null ? '—' : `${(doubled / 2000).toFixed(Number.isInteger(doubled) && doubled % 2 === 0 ? 3 : 4)} dB`;
export const mdb = (value) => value == null ? '—' : `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 3 })} mdb`;
export const position = (coordinate) => coordinate ? meter(coordinate.numerator / coordinate.denominator) : '—';
export const direction = { a: '甲端', b: '乙端' };
export const eventStatus = {
  matched: '唯一归点', ambiguous: '多窗口重叠', collision: '同端多事件', outside: '在端点标记之外', unmapped: '未落入任何窗口',
};
export const blockers = {
  missing_trace: '缺少测量方向', unassigned_events: '有事件没有唯一归点', incomplete_sites: '有接续点缺少双端证据',
  site_over_limit: '有接续点超限', link_over_limit: '链路损耗超限', closure_over_limit: '估算与实测闭合差超限',
  delivery_unallocable: '交割明细无法满足每向守恒', delivery_site_over_limit: '整数交割点位超限',
  delivery_link_over_limit: '整数交割链路超限', delivery_closure_over_limit: '整数交割闭合差超限',
};
