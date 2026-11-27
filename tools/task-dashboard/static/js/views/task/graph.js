// Graph tab: the task's items, requirements, decisions, features and validations as one graph (detail.graph),
// laid out by ELK in one column per kind and colored by status. The libraries come from the CDN, pinned,
// and load once, the first time the tab opens.
import {esc} from "../../format.js";
import {loadScripts} from "../../scripts.js";

const SCRIPTS = [
  "https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js",
  "https://cdn.jsdelivr.net/npm/elkjs@0.9.3/lib/elk.bundled.js",
  "https://cdn.jsdelivr.net/npm/cytoscape-elk@2.2.0/dist/cytoscape-elk.js",
];

// Kinds in column order, each with its node shape and the mark the legend shows.
const KINDS = [
  ["item", "Items", "diamond", "◆"],
  ["requirement", "Requirements", "round-rectangle", "▬"],
  ["decision", "Decisions", "hexagon", "⬢"],
  ["feature", "Features", "triangle", "▲"],
  ["validation", "Validations", "ellipse", "●"],
];
const COLUMN = Object.fromEntries(KINDS.map(([kind], i) => [kind, i]));
const SHAPE = Object.fromEntries(KINDS.map(([kind, , shape]) => [kind, shape]));

// Every status of every kind, grouped by the color it takes from the page's palette.
const TONES = [
  ["--s-concluded", "done", ["concluded", "done", "passed"]],
  ["--s-decided", "decided", ["decided"]],
  ["--s-built", "built", ["built"]],
  ["--s-deciding", "in progress", ["deciding", "proposed", "draft", "approved", "building", "review"]],
  ["--bad", "failed", ["failed"]],
  ["--s-discovery", "open", ["open", "pending", "planned", "discovery"]],
  ["--s-dropped", "dropped", ["dropped", "superseded"]],
];
const FADED = ["dropped", "superseded"];

const FAILED = "graph library could not load (reload to try again)";

// The three scripts in order: cytoscape-elk registers itself on the cytoscape and ELK globals.
const libraries = () => loadScripts(SCRIPTS);

function palette() {
  const css = getComputedStyle(document.documentElement);
  const read = name => css.getPropertyValue(name).trim();
  const byStatus = new Map(TONES.flatMap(([name, , statuses]) => statuses.map(s => [s, read(name)])));
  return {status: s => byStatus.get(s) || read("--s-discovery"), text: read("--text"), muted: read("--muted"),
          accent: read("--accent")};
}

function style(colors) {
  return [
    {selector: "node", style: {
      label: "data(label)", "font-size": 10, color: colors.text, "text-valign": "bottom", "text-margin-y": 3,
      width: 22, height: 22, shape: n => SHAPE[n.data("kind")] || "ellipse",
      "background-color": n => colors.status(n.data("status"))}},
    {selector: FADED.map(s => `node[status = "${s}"]`).join(", "), style: {opacity: 0.45}},
    {selector: "edge", style: {
      width: 1, "curve-style": "bezier", "line-color": colors.muted, "line-opacity": 0.5,
      "target-arrow-shape": "triangle", "target-arrow-color": colors.muted, "arrow-scale": 0.7}},
    {selector: ".faded", style: {opacity: 0.12}},
    {selector: "edge.lit", style: {width: 2.5, "line-color": colors.accent, "line-opacity": 1,
                                   "target-arrow-color": colors.accent, "z-index": 9}},
    {selector: "node.lit", style: {"font-weight": 600, "font-size": 11}},
    {selector: "node.picked", style: {"border-width": 3, "border-color": colors.accent}},
  ];
}

const LAYOUT = {
  name: "elk",
  nodeLayoutOptions: n => ({"elk.partitioning.partition": COLUMN[n.data("kind")] ?? 0}),
  elk: {algorithm: "layered", "elk.direction": "RIGHT", "elk.partitioning.activate": true,
        "elk.layered.spacing.nodeNodeBetweenLayers": 110, "elk.spacing.nodeNode": 22},
};

function elements(graph) {
  return [
    ...graph.nodes.map(n => ({group: "nodes", data: {...n}})),
    ...graph.edges.map(e => ({group: "edges", data: {id: `${e.source}>${e.target}`, ...e}})),
  ];
}

// Draws with ELK, or at the positions and view a previous drawing of the same graph left (no layout to wait for).
function draw(container, graph, saved) {
  /* global cytoscape */
  const layout = saved
    ? {name: "preset", positions: n => saved.positions[n.id()], zoom: saved.zoom, pan: saved.pan, fit: false}
    : LAYOUT;
  return cytoscape({container, elements: elements(graph), style: style(palette()), layout,
                    minZoom: 0.2, maxZoom: 3});
}

const HINT = "Click a node to light its path; double-click opens it.";

// The drawn graph and what it was drawn from. The tab's HTML is rewritten on every refresh and tab switch, so
// each rendering draws the graph again; `saved` keeps the positions ELK gave, the view and the lit node, so a
// redraw of the same graph is immediate and looks as the user left it. `ready` is false while ELK runs.
const shown = {cy: null, task: null, shape: "", ready: false, line: null, L: null, saved: null};

const alive = () => shown.cy && !shown.cy.destroyed();

function remember() {
  if (!alive() || !shown.ready) return;
  const cy = shown.cy;
  shown.saved = {task: shown.task, shape: shown.shape, zoom: cy.zoom(), pan: {...cy.pan()},
                 positions: Object.fromEntries(cy.nodes().map(n => [n.id(), {...n.position()}])),
                 picked: cy.$("node.picked").id()};
}

function clear() {
  if (!alive()) return;
  shown.cy.elements().removeClass("faded lit picked");
  if (shown.line) shown.line.textContent = HINT;
  remember();
}

// The node, everything that leads to it and everything it leads to, lit; the rest faded.
function light(node) {
  clear();
  const path = node.predecessors().union(node.successors()).union(node);
  shown.cy.elements().not(path).addClass("faded");
  path.addClass("lit");
  node.addClass("picked");
  const id = node.id(), tab = shown.L.tab(id), linked = path.nodes().length - 1;
  shown.line.innerHTML = `<b>${esc(id)}</b> · ${linked} linked`
    + (tab ? ` · <a href="${shown.L.href(tab, id)}">open ${esc(id)} →</a>` : "") + " · Esc clears";
  remember();
}

function open(node) {
  const tab = shown.L.tab(node.id());
  if (tab) location.hash = shown.L.href(tab, node.id());
}

function listen(cy) {
  cy.on("tap", "node", event => light(event.target));
  cy.on("tap", event => { if (event.target === cy) clear(); });
  cy.on("dbltap", "node", event => open(event.target));
  cy.on("layoutstop", () => { shown.ready = true; remember(); });
  cy.on("viewport dragfree", remember);
}

function legend() {
  const kinds = KINDS.map(([, label, , mark]) => `<span>${mark} ${label}</span>`).join("");
  const tones = TONES.map(([name, label]) =>
    `<span><i class="swatch" style="background:var(${name})"></i>${esc(label)}</span>`).join("");
  return `<div class="legend">${kinds}</div><div class="legend">${tones}</div>`;
}

export function render(d) {
  if (!d.graph.nodes.length) return `<p class="empty">Nothing to draw yet.</p>`;
  return `<div class="graph-head">${legend()}<p class="graph-line" data-graph-line>${HINT}</p></div>
    <div class="graph" data-graph><p class="empty">loading graph…</p></div>`;
}

// The nodes and edges by id: the layout runs again only when this changes.
const shapeOf = graph => JSON.stringify([graph.nodes.map(n => `${n.id}:${n.kind}`).sort(),
                                         graph.edges.map(e => `${e.source}>${e.target}`).sort()]);

// Draws the graph into this rendering of the tab, with the statuses just fetched: at its saved positions and
// view when the task's nodes and edges are the same, else by ELK (keeping the task's zoom and pan).
function attach(tab, placeholder, d, L) {
  const task = `${d.row.repo}/${d.row.id}`, shape = shapeOf(d.graph);
  const saved = shown.saved?.task === task ? shown.saved : null;
  const same = saved?.shape === shape;
  if (alive()) shown.cy.destroy();
  placeholder.textContent = "";
  Object.assign(shown, {line: tab.querySelector("[data-graph-line]"), L, task, shape, ready: same,
                        cy: draw(placeholder, d.graph, same ? saved : null)});
  if (saved && !same) shown.cy.one("layoutstop", () => shown.cy.viewport({zoom: saved.zoom, pan: saved.pan}));
  listen(shown.cy);
  const node = saved?.picked && shown.cy.$id(saved.picked);
  if (node?.length) light(node);
}

function failed(placeholder) {
  Object.assign(shown, {cy: null, task: null, shape: "", ready: false, saved: null});
  placeholder.innerHTML = `<p class="empty">${FAILED}</p>`;
}

let escapes = false;  // Esc clears the lit path; listened once, the first time the graph mounts

// Called once the tab's HTML is in the page: loads the libraries the first time, then draws or reattaches.
export function mount(tab, d, L) {
  const placeholder = tab.querySelector("[data-graph]");
  if (!placeholder) return;
  if (!escapes) {
    document.addEventListener("keydown", event => { if (event.key === "Escape") clear(); });
    escapes = true;
  }
  libraries().then(() => {
    if (!placeholder.isConnected) return;
    try {
      attach(tab, placeholder, d, L);
    } catch {
      if (alive()) shown.cy.destroy();
      failed(placeholder);
    }
  }, () => failed(placeholder));
}
