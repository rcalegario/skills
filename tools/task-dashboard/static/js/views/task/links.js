// Ids inside a task page: which tab holds each, a link that opens it there, and text with its ids linked.
// An entry carries data-key="<id>" (a finding "<feature>:R-n"), so a link can unfold it and scroll to it.
import {esc} from "../../format.js";

// Anything shaped like an id; only the ids the task defines become links.
const ID = /\b(?:[A-Z]{1,4}-\d+(?:\.\d+)?|F\d+\.\d+)\b/g;
// A review finding's id, numbered per feature.
const FINDING = /^R-\d+$/;

export const taskHref = task => `#task=${encodeURIComponent(task).replace(/%2F/g, "/")}`;

// A feature's key: its roadmap id (F1.1), or its folder when the roadmap does not list it.
export const featureKey = f => String(f.roadmap ?? f.folder);

// The ids this task defines, each with the tab that holds it.
function tabsById(detail) {
  const s = detail.status;
  const groups = [
    ["decisions", detail.decisions.map(d => d.id)],
    ["requirements", [...s.items.map(i => i.id), ...s.requirements.map(r => r.id)]],
    ["validations", detail.validations.map(v => v.id)],
    ["pending", detail.pending.map(p => p.id)],
    ["journal", detail.journal.map(n => n.id)],
    ["features", [...s.roadmap.flatMap(m => m.features.map(f => f.id)), ...detail.features.map(featureKey),
                  ...detail.features.flatMap(f => (f.review?.findings || []).map(r => `${featureKey(f)}:${r.id}`))]],
  ];
  return new Map(groups.flatMap(([tab, list]) => list.filter(Boolean).map(id => [String(id), tab])));
}

export function links(task, detail) {
  const tabs = tabsById(detail);
  const href = (tab, focus) => `${taskHref(task)}&tab=${tab}${focus ? `&focus=${encodeURIComponent(focus)}` : ""}`;
  // A finding id (R-n) is linked only inside its feature, since every feature numbers its own.
  const ref = (id, feature) => {
    const key = feature && FINDING.test(id) ? `${feature}:${id}` : String(id);
    return tabs.has(key) ? `<a class="ref" href="${href(tabs.get(key), key)}">${esc(id)}</a>` : esc(id);
  };
  const text = (value, feature) => esc(value).replace(ID, id => ref(id, feature));
  // The tab that holds an id, or undefined when the task does not define it.
  const tab = id => tabs.get(String(id));
  return {href, ref, text, tab};
}

// Unfolds the entry with this key (and the entries around it) and scrolls it into view.
export function reveal(root, key) {
  const target = root.querySelector(`[data-key="${CSS.escape(key)}"]`);
  if (!target) return;
  for (let el = target; el && el !== root; el = el.parentElement) {
    if (el.tagName === "DETAILS") el.open = true;
  }
  target.scrollIntoView({block: "start"});
  target.classList.remove("flash");
  void target.offsetWidth;  // restarts the highlight when the same id is clicked again
  target.classList.add("flash");
}
