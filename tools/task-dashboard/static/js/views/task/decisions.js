// Decisions tab: every decision folded, open and proposed first; unfolded, its file in full.
import {esc, chip} from "../../format.js";
import {fields, empty} from "./parts.js";

const FIRST = ["open", "proposed"];
const rank = d => FIRST.includes(d.status) ? FIRST.indexOf(d.status) : FIRST.length;
const byNumber = (a, b) => a.id.localeCompare(b.id, undefined, {numeric: true});

function option(o, L) {
  return `<li class="option">${chip(o.status)} <b>${esc(o.name ?? o.title ?? "")}</b>
    ${fields(o, [["How", "how"], ["Pros", "pros"], ["Cons", "cons"]], L)}</li>`;
}

function decision(d, L) {
  const options = d.options?.length
    ? `<dt>Options</dt><dd><ul class="plain options">${d.options.map(o => option(o, L)).join("")}</ul></dd>` : "";
  return `<details class="entry" data-key="${esc(d.id)}"><summary><b>${esc(d.id)}</b> <span>${esc(d.title)}</span> ${chip(d.status)}</summary>
    ${fields(d, [["Question", "question"], ["Decision", "decision"], ["Why", "why"]], L)}
    ${options ? `<dl class="fields">${options}</dl>` : ""}
    ${fields(d, [["Born from", "born_from"], ["Discuss with", "discuss_with"], ["Supersedes", "supersedes"],
                 ["Superseded by", "superseded_by"], ["Context", "context"], ["Consequences", "consequences"],
                 ["Open points", "open_points"], ["Needs code", "needs_code"], ["PR note", "pr_note"],
                 ["Date", "date"], ["File", "file"]], L)}</details>`;
}

export function render(d, L) {
  if (!d.decisions.length) return empty("No decisions.");
  const sorted = [...d.decisions].sort((a, b) => rank(a) - rank(b) || byNumber(a, b));
  return sorted.map(x => decision(x, L)).join("");
}
