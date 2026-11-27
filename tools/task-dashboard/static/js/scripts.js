// Third-party scripts from the CDN, for the tabs that need them. Each script is added to the page once, and the
// promise for a list is kept as it settles: a failure stays until the page reloads, so the 30 s refresh never
// fetches it again.

function script(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = src;
    el.onload = resolve;
    el.onerror = () => reject(new Error(`could not load ${src}`));
    document.head.append(el);
  });
}

const loads = new Map();

// The scripts in the order given, each loaded after the one before (a later one may register itself on an
// earlier one's globals); the same list asked again gets the same promise.
export function loadScripts(srcs) {
  const key = srcs.join(" ");
  if (!loads.has(key)) loads.set(key, srcs.reduce((done, src) => done.then(() => script(src)), Promise.resolve()));
  return loads.get(key);
}
