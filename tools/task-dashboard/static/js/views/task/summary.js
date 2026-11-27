// Summary tab, in two columns: the work on the left (what to do next, the items still open),
// the facts on the right (progress, checks, the last notes). Below 860 px the columns stack, work first.
// A check group or note the user unfolds carries a data-key, so the refresh keeps it open (task.js).
import {esc, bar, chip, stepClass} from "../../format.js";
import {ids} from "./parts.js";

// What each step waits for, as the line under the Next panel's head.
const STEP_HINT = {
  decide: "Decisions still open.", consolidate: "The brief no longer matches the task; reread and restamp it.",
  plan: "No roadmap yet.", spike: "A spike blocks a feature.", build: "Next features of the roadmap.",
  review: "Items not concluded and without a pr_note.", pr: "Features without a PR link.",
  finish: "Worktrees left after the PR.",
};
const MAX_ACTIONS = 5;

const MAX_LINE = 140;

// The first sentence of a text, for one-line lists. A line that does not end at a period (a clause cut at ";" or ":",
// or a long text cut at a word break) ends in "…", so the reader sees there is more.
function firstSentence(text) {
  const t = String(text ?? "").trim();
  const m = t.match(new RegExp(`^(.{20,${MAX_LINE}}?)([.;:])(?:\\s|$)`, "s"));
  if (m) return m[2] === "." || m[1].length + 1 === t.length ? m[1] : `${m[1]}…`;
  if (t.length <= MAX_LINE) return t;
  const cut = t.slice(0, MAX_LINE), space = cut.lastIndexOf(" ");
  return `${space > MAX_LINE / 2 ? cut.slice(0, space) : cut}…`;
}

function actions(next, L) {
  if (!next.length) return `<p class="sub">Nothing left to do.</p>`;
  const shown = next.slice(0, MAX_ACTIONS), rest = next.slice(MAX_ACTIONS);
  return `<ol class="acts">${shown.map((a, i) => `<li class="${a.waiting ? "waiting" : ""}"><span class="n">${i + 1}</span>
      <span class="verb">${esc(a.verb)}</span>
      <span class="t">${a.short ? `${L.ref(a.short)} ` : ""}${L.text(a.name)}${a.waiting ? ` <span class="sub">· waiting on someone else</span>` : ""}</span>
      ${chip(a.state)}</li>`).join("")}</ol>
    ${rest.length ? `<p class="more">+ ${rest.length} more: ${rest.map(a => L.ref(a.short || a.id)).join(", ")}</p>` : ""}`;
}

// Who else holds something, and the user's own follow-ups, from status.py's agenda.
function waits(agenda, L) {
  const line = entries => entries.map(e => `${L.ref(e.id)} ${L.text(firstSentence(e.title))}`).join("; ");
  const others = Object.entries(agenda).filter(([who]) => who !== "me");
  const mine = agenda.me || [];
  if (!others.length && !mine.length) return "";
  return `<div class="waits">
    ${others.map(([who, entries]) => `<div>⏳ <span class="who">${esc(who)}</span> holds ${line(entries)}</div>`).join("")}
    ${mine.length ? `<div>📌 <span class="who">Your follow-ups</span>: ${line(mine)}</div>` : ""}</div>`;
}

function nextPanel(d, L) {
  const step = d.status.step;
  const head = step.step === "done" ? `<span class="turn ok">✓</span> Done`
    : step.your_turn ? `<span class="turn">!</span> Your turn` : `<span class="turn off">⏳</span> Waiting on others`;
  return `<section class="panel next step-${esc(step.step)}">
    <div class="head">${head} · <span class="${stepClass(step.step)}">${esc(step.step)}</span></div>
    ${STEP_HINT[step.step] ? `<div class="why">${esc(STEP_HINT[step.step])}</div>` : ""}
    ${actions(d.next || [], L)}
    ${waits(d.status.agenda || {}, L)}</section>`;
}

// Each item not concluded nor dropped, its open requirements and what each needs; the concluded ones on one line.
function openItems(d, L) {
  const items = d.status.items;
  const open = items.filter(i => i.status !== "concluded" && i.status !== "dropped");
  const done = items.filter(i => i.status === "concluded");
  const body = open.map(i => {
    const reqs = d.row.open_requirements.filter(r => r.item === i.id);
    return `<div class="s-item"><div class="ih">${L.ref(i.id)} <span class="it">${L.text(i.text)}</span> ${chip(i.status)}</div>
      ${reqs.length ? `<ul>${reqs.map(r => `<li>${L.ref(r.id)} <span class="miss">needs: ${
        r.missing.map(m => L.text(m.text)).join("; ") || "nothing"}</span></li>`).join("")}</ul>` : ""}</div>`;
  }).join("");
  return `<section class="zone"><h3>Items still open</h3>
    <div class="panel">${body || `<p class="sub">Every item is concluded.</p>`}</div>
    ${done.length ? `<p class="sub concluded">✓ Concluded: ${done.map(i => `${L.ref(i.id)} ${L.text(i.text)}`).join("; ")}</p>` : ""}</section>`;
}

// The items bar and four numbers. Features count against the roadmap's (planned ones too), else the feature.yamls.
// Dropped items and validations are out of play: the totals leave them out.
function progress(d) {
  const s = d.status, row = d.row, items = row.items;
  const roadmap = s.roadmap.flatMap(m => m.features || []);
  const features = roadmap.length ? roadmap : s.features;
  const validations = d.validations.filter(v => v.status !== "dropped");
  const passed = validations.filter(v => v.status === "passed").length;
  const kv = [
    ["Items concluded", `${items.by_status.concluded || 0}/${items.total - (items.by_status.dropped || 0)}`],
    ["Features done", `${features.filter(f => f.status === "done").length}/${features.length}`],
    ["Validations passed", `${passed}/${validations.length}`],
    ["Decisions open", row.decisions.open + row.decisions.proposed],
  ];
  return `<section class="panel"><h3>Progress</h3>${bar(items.by_status)}
    <div class="kv">${kv.map(([k, v]) => `<span>${k}</span><b>${v}</b>`).join("")}</div></section>`;
}

// status.py's failures and warnings grouped by kind: counts in the title, one line per group, the rest unfolds.
function checksCard(d, L) {
  const s = d.status, nf = s.failures.length, nw = s.warnings.length;
  if (!nf && !nw) return `<section class="panel chk chk-ok">✓ Checks clean: status.py found no failures or warnings</section>`;
  const groups = (d.checks || []).map((g, i) => {
    const failure = g.severity === "failure";
    const n = g.ids.length;
    const label = [n ? `${n} id${n > 1 ? "s" : ""}` : "", g.fix ? "fix" : "", "messages"].filter(Boolean).join(" · ");
    return `<div class="wg"><div class="gt"><span class="ic ${failure ? "fail" : "warn"}">${failure ? "✗" : "!"}</span>
        <span>${L.text(g.title)}</span></div>
      <details data-key="summary-check:${i}:${esc(g.kind)}"><summary>${label}</summary>
        <ul>${n ? `<li>${ids(g.ids, L)}</li>` : ""}${g.fix ? `<li><b>Fix:</b> ${L.text(g.fix)}</li>` : ""}${
          g.messages.map(m => `<li>${L.text(m)}</li>`).join("")}</ul></details></div>`;
  }).join("");
  return `<section class="panel chk ${nf ? "chk-bad" : "chk-warn"}"><h3>Checks <span class="cnt">${
    nf ? `<span class="fail">${nf} ✗</span>` : ""} ${nw ? `<span class="warn">${nw} !</span>` : ""}</span></h3>${groups}</section>`;
}

// The last four notes, newest first, each its type and first sentence, the whole note unfolding.
function lately(d, L) {
  const notes = d.journal.slice(-4).reverse();
  const list = notes.map(n => `<li><span class="ty">${esc(n.type || "")}</span>
    <details data-key="summary-note:${esc(n.id)}"><summary>${L.text(firstSentence(n.text))}</summary>
      <div class="full"><span class="when">${L.ref(n.id)} · ${esc(n.date)}</span> ${L.text(n.text)}
        ${n.refs?.length ? `<div class="sub">refs ${ids(n.refs, L)}</div>` : ""}</div></details></li>`).join("");
  return `<section class="panel"><h3>Lately</h3>
    ${notes.length ? `<ul class="notes">${list}</ul>` : `<p class="sub">No journal notes.</p>`}
    <a class="all" href="${L.href("journal")}">All notes in Journal →</a></section>`;
}

export function render(d, L) {
  return `<div class="sum-grid">
    <div class="work">${nextPanel(d, L)}${openItems(d, L)}</div>
    <aside class="side">${progress(d)}${checksCard(d, L)}${lately(d, L)}</aside>
  </div>`;
}
