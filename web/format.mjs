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
  missing_bridge: '相邻段之间缺少认可桥接', missing_segment_release: '引用的分段修订尚未签发',
  segment_not_ready: '引用的分段修订仍在留置', conflicting_segment: '同一光段的引用互相矛盾',
  conflicting_bridge: '同一实物连接存在冲突记录', unknown_port: '端口无法唯一对应实物',
  unused_segment: '有光段不在独特的起终链上', unused_bridge: '有桥接不连接相邻光段',
  ambiguous_assembly: '拼接方式不唯一',
};
