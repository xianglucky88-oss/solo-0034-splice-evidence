import { meter } from './format.mjs';

export function ruler(canvas) {
  let current;
  const draw = () => {
    if (!current || !canvas.clientWidth) return;
    const { plan, events } = current;
    const ratio = devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const ctx = canvas.getContext('2d');
    ctx.scale(ratio, ratio);
    const x = (at) => 26 + at * (width - 52) / (plan.length_mm || 1);
    ctx.font = '11px system-ui';
    ctx.fillStyle = '#546964';
    ctx.fillText('甲端', 25, 24);
    ctx.textAlign = 'right';
    ctx.fillText('乙端', width - 25, 24);
    for (const lane of [58, 88, 118]) {
      ctx.strokeStyle = '#c6d4c9';
      ctx.beginPath(); ctx.moveTo(x(0), lane); ctx.lineTo(x(plan.length_mm), lane); ctx.stroke();
    }
    ctx.fillStyle = '#354d45';
    ctx.textAlign = 'center';
    let previous = -Infinity;
    for (const site of plan.sites) {
      const left = x(site.at_mm);
      ctx.fillRect(left - 3, 55, 6, 6);
      const half = ctx.measureText(site.site_id).width / 2;
      if (left - half > previous + 7 && left + half < width - 3) {
        ctx.fillText(site.site_id, left, 48);
        previous = left + half;
      }
    }
    for (const at of plan.marks_mm || []) {
      ctx.fillStyle = '#8d471b';
      ctx.beginPath();
      ctx.moveTo(x(at), 52); ctx.lineTo(x(at) + 5, 58); ctx.lineTo(x(at), 64); ctx.lineTo(x(at) - 5, 58);
      ctx.closePath(); ctx.fill();
    }
    for (const event of events) {
      if (!event.along_mm) continue;
      const position = event.along_mm.numerator / event.along_mm.denominator;
      ctx.fillStyle = event.status !== 'matched' ? '#a03922' : event.direction === 'a' ? '#1c8170' : '#9d562a';
      ctx.beginPath();
      ctx.arc(x(position), event.direction === 'a' ? 88 : 118, 4, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = '#546964';
    ctx.textAlign = 'left'; ctx.fillText(meter(0), 25, 149);
    ctx.textAlign = 'right'; ctx.fillText(meter(plan.length_mm), width - 25, 149);
  };
  new ResizeObserver(draw).observe(canvas);
  return (work) => { current = work; draw(); };
}
