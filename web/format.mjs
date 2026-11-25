export const meter = (mm) => `${(mm / 1000).toLocaleString('zh-CN', { maximumFractionDigits: 3 })} 米`;
export const loss = (doubled) => doubled == null ? '—' : `${(doubled / 2000).toFixed(doubled % 2 ? 4 : 3)} dB`;
export const position = (coordinate) => coordinate ? meter(coordinate.numerator / coordinate.denominator) : '—';
export const direction = { a: '甲端', b: '乙端' };
export const eventStatus = {
  matched: '唯一归点', ambiguous: '多窗口重叠', collision: '同端多事件', contested: '归属竞争',
  undetermined: '归属未定', outside: '在端点标记之外', unmapped: '未落入任何窗口', held: '该向留置',
};
export const eventBasis = {
  overlap: '所有最多配对都使用该事件，但对点位意见不一',
  competing: '不采用该事件也能配出同样多的事件',
  same_end: '同端事件争用同一候选点，均不能独占',
  same_mileage: '同向事件里程相同，至多配出一个',
  endpoint: '仪表读数落在近远端标记之外',
  no_window: '里程不在任何归点窗口内',
  mark_count: '中间标记数量与计划不符',
  mark_order: '仪表标记乱序',
};
export const calibrationStatus = {
  ok: '三处标记换算', legacy: '无中间标记，沿用原换算', held: '该向留置',
};
export const markRole = { near: '近端标记', middle: '中间标记', far: '远端标记' };
export const blockers = {
  missing_trace: '缺少测量方向', calibration_held: '有测量方向因标记不符或乱序留置',
  unassigned_events: '有事件没有唯一归点', incomplete_sites: '有接续点缺少双端证据',
  site_over_limit: '有接续点超限', link_over_limit: '链路损耗超限', closure_over_limit: '估算与实测闭合差超限',
};
