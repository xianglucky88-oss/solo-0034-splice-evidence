export const meter = (mm) => `${(mm / 1000).toLocaleString('zh-CN', { maximumFractionDigits: 3 })} 米`;
export const loss = (doubled) => doubled == null ? '—' : `${(doubled / 2000).toFixed(doubled % 2 ? 4 : 3)} dB`;
export const position = (coordinate) => coordinate ? meter(coordinate.numerator / coordinate.denominator) : '—';
export const direction = { a: '甲端', b: '乙端' };
export const eventStatus = {
  matched: '唯一归点', ambiguous: '多窗口重叠', collision: '同端多事件', outside: '在端点标记之外', unmapped: '未落入任何窗口',
};
export const blockers = {
  missing_trace: '缺少测量方向', unassigned_events: '有事件没有唯一归点', incomplete_sites: '有接续点缺少双端证据',
  site_over_limit: '有接续点超限', link_over_limit: '链路损耗超限', closure_over_limit: '估算与实测闭合差超限',
  revoked_calibration: '所采用的校验批次已撤销',
};
export const handoff = { clear: '现时可交接', blocked: '现时不可交接' };
export const stated = (item) => item && item.source === 'stated';
export const credential = (item) => stated(item)
  ? `${item.instrument_id} · ${item.calibration_batch}` : '来源未注明';
