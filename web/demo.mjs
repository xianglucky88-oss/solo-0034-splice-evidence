import { get, post, spanPath, spans } from './api.mjs';

export async function loadDemo() {
  const sources = ['plan', 'a', 'b', 'b-repeat'];
  const [plan, ...traces] = await Promise.all(sources.map((sample) => get(`/examples/${sample}.json`)));
  const saved = await post(spans, plan);
  const base = spanPath(plan.span_id);
  for (const trace of traces) await post(`${base}/traces`, trace);
  if (saved.revision === 0) {
    await post(`${base}/selection`, { revision: 0, a: traces[0].trace_id, b: traces[1].trace_id });
  }
  return plan.span_id;
}
