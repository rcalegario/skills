// Docs tab: the task's Markdown files (detail.docs) listed beside the one the hash names (&doc=<path>,
// README.md without one), rendered by marked with each mermaid block drawn as a diagram. The libraries come from
// the CDN, pinned, and load once, the first time the tab opens. Raw HTML in a doc shows as text.
import {esc} from "../../format.js";
import {fetchDoc} from "../../api.js";
import {loadScripts} from "../../scripts.js";

const SCRIPTS = [
  "https://cdnjs.cloudflare.com/ajax/libs/marked/15.0.6/marked.min.js",
  "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js",
];
const FAILED = "docs library could not load (reload to try again)";
const DEFAULT = "README.md";

let loading = null;

// Both scripts, and the Markdown parser built once from them.
function libraries() {
  loading ??= loadScripts(SCRIPTS).then(() => {
    /* global marked */
    return new marked.Marked({
      gfm: true,
      renderer: {
        html: ({text}) => esc(text),
        image: ({text}) => esc(text),  // images stay out: their alt text, and nothing fetched
        code: ({text, lang}) => lang === "mermaid" ? `<pre class="mermaid">${esc(text)}</pre>` : false,
      },
    });
  });
  return loading;
}

// The doc the hash names, or README.md.
export const docPath = () => new URLSearchParams(location.hash.slice(1)).get("doc") || DEFAULT;

const docHref = (L, path) => `${L.href("docs")}&doc=${encodeURIComponent(path)}`;

const folderOf = path => path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";

// The docs grouped by folder, in the order the server lists them.
function list(docs, current, L) {
  const groups = new Map();
  for (const doc of docs) {
    const folder = folderOf(doc.path);
    if (!groups.has(folder)) groups.set(folder, []);
    groups.get(folder).push(doc);
  }
  return [...groups].map(([folder, entries]) => `<div class="docs-group">
      ${folder ? `<div class="k">${esc(folder)}/</div>` : ""}
      <ul class="plain">${entries.map(doc => `<li><a href="${docHref(L, doc.path)}"
        ${doc.path === current ? `class="on" aria-current="page"` : ""} title="${esc(doc.path)}">${esc(doc.title)}</a></li>`).join("")}</ul>
    </div>`).join("");
}

export function render(d, L) {
  if (!d.docs?.length) return `<p class="empty">This task has no Markdown files.</p>`;
  const current = docPath();
  return `<div class="docs"><nav class="docs-list" aria-label="Docs">${list(d.docs, current, L)}</nav>
    <article class="md" data-doc><p class="empty">loading ${esc(current)}…</p></article></div>`;
}

// Where a relative link of the doc at `from` points, as a path inside the task ("context/now.md"), without its
// query or fragment; null when it starts at "/", climbs out of the task folder or does not decode.
function resolve(from, href) {
  const rel = href.split(/[?#]/)[0];
  if (!rel || rel.startsWith("/")) return null;
  const parts = folderOf(from) ? folderOf(from).split("/") : [];
  for (const raw of rel.split("/")) {
    let part;
    try {
      part = decodeURIComponent(raw);
    } catch {
      return null;
    }
    if (part === "" || part === ".") continue;
    if (part !== "..") parts.push(part);
    else if (!parts.length) return null;
    else parts.pop();
  }
  return parts.join("/");
}

// A link to a listed doc opens it in this tab; a web link opens a new browser tab; any other link becomes its text.
function links(article, path, docs, L) {
  const listed = new Set(docs.map(doc => doc.path));
  for (const a of article.querySelectorAll("a[href]")) {
    const href = a.getAttribute("href");
    const target = /^[a-z][a-z0-9+.-]*:|^\/\/|^#/i.test(href) ? null : resolve(path, href);
    if (/^https?:\/\//i.test(href)) {
      Object.assign(a, {target: "_blank", rel: "noopener"});
    } else if (target !== null && listed.has(target)) {
      a.setAttribute("href", docHref(L, target));
    } else {
      a.replaceWith(...a.childNodes);
    }
  }
}

// Each id the task defines, in the doc's text outside code, links and diagrams, links to its tab.
function ids(article, L) {
  const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, {
    acceptNode: node => node.parentElement.closest("pre, code, a") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  const texts = [];
  while (walker.nextNode()) texts.push(walker.currentNode);
  for (const node of texts) {
    const html = L.text(node.textContent);
    if (html === esc(node.textContent)) continue;
    const span = document.createElement("span");
    span.innerHTML = html;
    node.replaceWith(...span.childNodes);
  }
}

// Draws each mermaid block of the doc in the page's light or dark theme; a block that fails keeps its source
// with the error under it.
async function diagrams(article) {
  /* global mermaid */
  const blocks = [...article.querySelectorAll("pre.mermaid")];
  if (!blocks.length) return;
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({startOnLoad: false, securityLevel: "strict", theme: dark ? "dark" : "default"});
  for (const block of blocks) {
    try {
      await mermaid.run({nodes: [block]});
    } catch (exc) {
      block.classList.add("mermaid-failed");
      block.insertAdjacentHTML("afterend", `<p class="error">diagram: ${esc(exc.message || exc)}</p>`);
    }
  }
}

// The rendered doc and what it was rendered from. The tab's HTML is rewritten on every refresh and tab switch, so
// each rendering moves this element back in place of the new placeholder; the doc is fetched and rendered again
// only when its file's mtime changed. `mtime` is the one asked for, cleared when the fetch fails. `run` numbers
// each fetch, so one that a newer fetch overtook drops its result instead of writing stale text last.
const shown = {key: null, mtime: null, el: null, run: 0};

// Renders into the kept element; the scroll is put back once the diagrams are drawn, since they change the height.
async function show(article, d, L, path, md, run) {
  const latest = () => shown.run === run;
  let text;
  try {
    text = await fetchDoc(`${d.row.repo}/${d.row.id}`, path);
  } catch (exc) {
    if (!latest()) return;
    shown.mtime = null;
    article.innerHTML = `<p class="empty">${esc(path)} could not be read: ${esc(exc.message)}</p>`;
    return;
  }
  if (!latest()) return;
  if (!article.isConnected) {  // the user left the tab meanwhile: render when it is shown again
    shown.mtime = null;
    return;
  }
  const y = window.scrollY;
  article.innerHTML = md.parse(text);
  links(article, path, d.docs, L);
  ids(article, L);
  await diagrams(article);
  if (latest() && article.isConnected) window.scrollTo(0, y);
}

// Called once the tab's HTML is in the page: loads the libraries the first time, then puts the doc in place,
// fetching it only when it is new or its file changed.
export function mount(tab, d, L) {
  const placeholder = tab.querySelector("[data-doc]");
  if (!placeholder) return;
  const path = docPath(), doc = d.docs.find(entry => entry.path === path);
  if (!doc) {
    placeholder.innerHTML = `<p class="empty">${esc(path)} is not a doc of this task</p>`;
    return;
  }
  const key = `${d.row.repo}/${d.row.id}:${path}`;
  if (shown.key === key && shown.el) {
    placeholder.replaceWith(shown.el);
    if (shown.mtime === doc.mtime) return;
  } else {
    Object.assign(shown, {key, el: placeholder});
  }
  shown.mtime = doc.mtime;
  const article = shown.el, run = ++shown.run;
  libraries().then(md => show(article, d, L, path, md, run),
                   () => { article.innerHTML = `<p class="empty">${FAILED}</p>`; });
}
