import { get, post, spanPath, spans } from './api.mjs';

const SAMPLES = [
  ['w34', ['plan', 'a', 'b', 'b-repeat']],
  ['w35', ['w35', 'w35-a', 'w35-b']],
];

async function register([, names]) {
  const [plan, ...traces] = await Promise.all(names.map((name) => get(`/examples/${name}.json`)));
  const saved = await post(spans, plan);
  const base = spanPath(plan.span_id);
  for (const trace of traces) await post(`${base}/traces`, trace);
  if (saved.revision === 0) {
    await post(`${base}/selection`, { revision: 0, a: traces[0].trace_id, b: traces[1].trace_id });
  }
  const [work, releases] = await Promise.all([get(base), get(`${base}/releases`)]);
  const frozen = releases.some((item) => item.revision === work.revision);
  if (!frozen) await post(`${base}/releases`, { revision: work.revision });
  return plan.span_id;
}

export async function loadDemo() {
  const ids = [];
  for (const sample of SAMPLES) ids.push(await register(sample));
  const route = await get('/examples/route.json');
  const routes = '/api/splice/routes';
  await post(routes, route);
  return { span: ids[0], route: route.route_id };
}
