// Features tab: the roadmap's milestones and their features; a feature unfolds into its tasks,
// its criteria with their checks, and its review findings.
import {esc, chip} from "../../format.js";
import {fields, ids, empty, section} from "./parts.js";
import {featureKey} from "./links.js";

function tasks(f) {
  if (!f.tasks?.length) return "";
  return `<h4>Tasks</h4><ul class="list">${f.tasks.map(t => `<li><b>${esc(t.id)}</b> ${chip(t.status)} ${esc(t.title)}
    ${t.sha ? `<code>${esc(t.sha)}</code>` : ""}${t.covers?.length ? ` <span class="sub">covers ${esc(t.covers.join(", "))}</span>` : ""}</li>`).join("")}</ul>`;
}

function criteria(f, L) {
  if (!f.acceptance?.length) return "";
  const checks = new Map((f.checks || []).map(c => [c.ac, c]));
  return `<h4>Criteria</h4><ul class="list">${f.acceptance.map(ac => {
    const c = checks.get(ac.id);
    const how = c ? (c.test ? `<code>${esc(c.test)}</code>` : c.manual ? `manual: <span class="prose">${L.text(c.manual)}</span>` : "") : "";
    return `<li><b>${esc(ac.id)}</b> ${chip(c?.status ?? "no check")} <span class="prose">${L.text(ac.text)}</span>
      ${how ? `<div class="sub">${how}</div>` : ""}</li>`;
  }).join("")}</ul>`;
}

function findings(f, L, key) {
  const review = f.review;
  if (!review) return `<h4>Review</h4>${empty("Not reviewed yet.")}`;
  const list = review.findings || [];
  if (!list.length) return `<h4>Review</h4>${empty("Clean review.")}`;
  return `<h4>Review</h4><ul class="list">${list.map(r => {
    const where = r.file ? `<code>${esc(r.file)}${r.line ? `:${esc(r.line)}` : ""}</code>` : "";
    const outcome = r.action === "fix" ? `fix in ${esc(r.task ?? "?")}` : r.action === "wontfix" ? `won't fix: ${L.text(r.reason, key)}`
      : r.action ? esc(r.action) : "no action yet";
    return `<li data-key="${esc(`${key}:${r.id}`)}"><b>${esc(r.id)}</b> ${chip(r.severity)} <span class="prose">${L.text(r.text, key)}</span>
      <div class="sub">${where} ${r.source ? `· ${esc(r.source)}` : ""} · ${outcome}</div></li>`;
  }).join("")}</ul>`;
}

function feature(rf, f, L) {
  const key = String(rf.id);
  const story = f?.story || {};
  const body = f ? `${fields(f, [["Folder", "folder"], ["Size", "size"], ["Repo", "repo"], ["Base", "base"], ["PR", "pr"]], L)}
      ${story.decisions?.length || story.validations?.length
        ? `<dl class="fields"><dt>Story</dt><dd>${ids(story.decisions, L)}${story.decisions?.length && story.validations?.length ? " · " : ""}${ids(story.validations, L)}</dd></dl>` : ""}
      ${tasks(f)}${criteria(f, L)}${findings(f, L, key)}`
    : empty("No spec yet.");
  return `<details class="entry" data-key="${esc(key)}"><summary><b>${esc(key)}</b> <span>${esc(rf.title ?? f?.title ?? "")}</span> ${chip(rf.status ?? f?.status)}</summary>
    ${rf.goal ? `<p class="prose">${L.text(rf.goal)}</p>` : ""}
    ${rf.blocked_by?.length ? `<p class="sub">blocked by ${ids(rf.blocked_by, L)}</p>` : ""}${body}</details>`;
}

export function render(d, L) {
  const roadmap = d.status.roadmap;
  const specs = new Map(d.features.map(f => [featureKey(f), f]));
  const listed = new Set(roadmap.flatMap(m => m.features.map(f => String(f.id))));
  const others = d.features.filter(f => !listed.has(featureKey(f)));
  if (!roadmap.length && !others.length) return empty("No roadmap yet.");
  return roadmap.map(m => section(`${m.id} · ${m.title ?? ""}`,
      `${chip(m.status)} ${m.outcome ? `<span class="prose sub">${L.text(m.outcome)}</span>` : ""}
       ${m.features.map(rf => feature(rf, specs.get(String(rf.id)), L)).join("") || empty("No features.")}`)).join("")
    + (others.length ? section("Not in the roadmap", others.map(f => feature({id: featureKey(f)}, f, L)).join("")) : "");
}
