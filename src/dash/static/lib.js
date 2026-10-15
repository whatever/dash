export const $ = (sel) => document.querySelector(sel);

export const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

export async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body && JSON.stringify(opts.body),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.status === 204 ? null : res.json();
}

export function minutes(n) {
  if (n % 1440 === 0) return `${n / 1440} d`;
  if (n % 60 === 0) return `${n / 60} h`;
  return `${n} min`;
}
