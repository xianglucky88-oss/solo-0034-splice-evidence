// Minimal DOM shim to exercise review/summary rendering without a browser.
class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attributes = {}; this.classList = new Set();
    this._text = ''; this.options = []; this.hidden = false; this.disabled = false;
    this.value = ''; this.title = ''; this.selected = false;
  }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); this.children = []; }
  append(...kids) { for (const k of kids) this.children.push(k); }
  appendChild(k) { this.children.push(k); }
  replaceChildren(...kids) {
    this.children = [...kids];
    this.options = kids.filter((k) => k instanceof Option);
  }
  addEventListener() {}
  closest() { return { hidden: false }; }
  querySelector() { return new El('thead'); }
}
class Option extends El {
  constructor(label, value) { super('option'); this.textContent = label; this.value = value; }
}
global.Option = Option;

const ids = {};
function byId(id) { return ids[id] ?? (ids[id] = new El('div')); }

global.document = {
  getElementById: byId,
  createElement: (tag) => new El(tag),
};
global.ResizeObserver = class { observe() {} };
global.devicePixelRatio = 1;

const work = {
  mode: 'review', review_direction: 'b', revision: 7,
  plan: { span_id: 'RV-W1', label: '复核段', a_label: '甲', b_label: '乙', length_mm: 1600000,
          fixed_mdb: 100, link_limit_mdb: 5000, residual_limit_mdb: 2000,
          sites: [{ site_id: 'J01' }, { site_id: 'J02' }, { site_id: 'J03' }] },
  active: { a: { trace_id: 'A-1' }, b: null },
  budget: { status: 'held', blockers: ['review_no_majority'] },
  review: {
    direction: 'b', counter_direction: 'a', tolerance_mdb: 10,
    roster: [
      { trace_id: 'B-301', eligible: true, exclusion: { code: 'no_unique_majority_group', detail: {} } },
      { trace_id: 'B-302', eligible: false, exclusion: { code: 'pending_events', detail: { missing_sites: ['J03'] } } },
    ],
    group: [], members: {},
  },
};

const receipts = [
  { trace_id: 'B-301', direction: 'b' }, { trace_id: 'B-302', direction: 'b' },
  { trace_id: 'B-304', direction: 'b' }, { trace_id: 'A-1', direction: 'a' },
];
const rosters = { b: [{ trace_id: 'B-301', tolerance_mdb: 10 }, { trace_id: 'B-302', tolerance_mdb: 10 }] };

const review = await import('../web/review.mjs');
const summary = await import('../web/summary.mjs');

review.renderReviewForm(work, receipts, false, rosters);
review.renderReviewResults(work);
summary.renderSummary(work, false);

const results = byId('review-results');
function dump(el, depth = 0) {
  const pad = '  '.repeat(depth);
  let line = `${pad}<${el.tag}>${el._text ? ' ' + el._text : ''}${el.hidden ? ' [hidden]' : ''}`;
  console.log(line);
  for (const c of el.children) dump(c, depth + 1);
}
console.log('--- review-results ---');
dump(results);
console.log('--- metrics ---');
dump(byId('metrics'));
console.log('--- review-traces options selected ---');
console.log('direction select value:', byId('review-direction').value);
console.log('tolerance:', byId('review-tolerance').value);
// submission payload
byId('review-direction').value = 'b';
byId('review-tolerance').value = '10';
byId('review-traces').selectedOptions = [{ value: 'B-301' }, { value: 'B-302' }, { value: 'B-304' }];
const sub = review.reviewSubmission(7);
console.log('submission:', JSON.stringify(sub));
const clear = review.reviewClear(7);
console.log('clear:', JSON.stringify(clear));
console.log('SHIM OK');
