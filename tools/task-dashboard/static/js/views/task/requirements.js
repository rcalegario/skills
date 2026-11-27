// Requirements tab: each item with its requirements (status, decision tree, validations, what is missing).
import {esc, chip} from "../../format.js";
import {empty, section} from "./parts.js";

function statusOf(list) {
  return new Map(list.map(e => [e.id, e.status]));
}

function requirement(r, L, decisions) {
  const tree = r.tree.map(id => `${L.ref(id)} ${chip(decisions.get(id))}`).join(" · ");
  const vals = r.validations.map(v => `${L.ref(v.id)} ${chip(v.status)}`).join(" · ");
  return `<li data-key="${esc(r.id)}"><div><b>${L.ref(r.id)}</b> ${chip(r.status)} ${L.text(r.text)}</div>
    <dl class="fields">
      <dt>Decisions</dt><dd>${tree || "<span class=\"sub\">none active</span>"}</dd>
      <dt>Validations</dt><dd>${vals || "<span class=\"sub\">none</span>"}</dd>
      <dt>Missing</dt><dd>${r.missing.length ? `<ul class="plain missing">${r.missing.map(m => `<li>${L.text(m.text)}</li>`).join("")}</ul>`
        : "<span class=\"sub\">nothing</span>"}</dd>
    </dl></li>`;
}

function item(i, L, reqs, decisions) {
  const own = i.requirements.map(id => reqs.get(id)).filter(Boolean);
  return `<div class="item" data-key="${esc(i.id)}"><h4>${esc(i.id)} ${chip(i.status)} <span class="prose">${L.text(i.text)}</span></h4>
    ${i.pr_note ? `<p class="sub">PR note: <span class="prose">${L.text(i.pr_note)}</span></p>` : ""}
    ${own.length ? `<ul class="list">${own.map(r => requirement(r, L, decisions)).join("")}</ul>`
      : empty(i.status === "dropped" ? "Dropped." : "No requirements.")}</div>`;
}

export function render(d, L) {
  const s = d.status;
  const reqs = new Map(s.requirements.map(r => [r.id, r]));
  const decisions = statusOf(d.decisions);
  return section("Items", s.items.length ? s.items.map(i => item(i, L, reqs, decisions)).join("") : empty("No items."));
}
