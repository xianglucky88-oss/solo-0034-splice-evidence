export const byId = (id) => document.getElementById(id);

export function node(tag, content, className) {
  const element = document.createElement(tag);
  if (content != null) element.textContent = content;
  if (className) element.className = className;
  return element;
}

export function action(text, run) {
  const button = node('button', text, 'link-button');
  button.type = 'button';
  button.addEventListener('click', run);
  return button;
}

export function options(select, items, value) {
  select.replaceChildren(...items.map(([id, label]) => new Option(label, id)));
  if (value != null) select.value = value;
}
