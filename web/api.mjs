async function request(path, payload) {
  const config = payload === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload,
  };
  const response = await fetch(path, config);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `接口返回 ${response.status}`);
  return value;
}

export const spans = '/api/splice/spans';
export const spanPath = (id) => `${spans}/${encodeURIComponent(id)}`;
export const get = (path) => request(path);
export const post = (path, data) => request(path, JSON.stringify(data));
export const postText = (path, text) => request(path, text);
