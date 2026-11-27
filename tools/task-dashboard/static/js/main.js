// Boot: the hash picks the page (all tasks, or one task's page), the data is loaded and drawn,
// and refreshed every 30 s.
//   #                                     every task in one list, filtered by step
//   #task=<repo>/<id>&tab=<tab>&focus=<id>  one task's page, on a tab, with an entry shown
import {fetchTasks, fetchTask} from "./api.js";
import {startRefresh} from "./refresh.js";
import {esc, clock} from "./format.js";
import * as tasksView from "./views/tasks.js";
import * as taskView from "./views/task.js";

// The data on screen and which page it belongs to ("" for all tasks, else "<repo>/<id>").
const state = {page: null, data: null, error: null, at: null};
let firstDraw = true;  // a reload shows the entry its hash names
let refresh = null;    // set by startRefresh below

function route() {
  const params = new URLSearchParams(location.hash.slice(1));
  return {task: params.get("task") || "", tab: params.get("tab"), focus: params.get("focus")};
}

function draw({focus = false} = {}) {
  const r = route(), view = document.getElementById("view"), meta = document.getElementById("meta");
  const failed = state.error ? ` · <span class="error">error: ${esc(state.error)}${state.data ? " (old data kept)" : ""}</span>` : "";
  if (state.page !== r.task || !state.data) {
    view.innerHTML = state.error
      ? `<p class="empty">${r.task ? `No task ${esc(r.task)}. ` : ""}<a href="#">← All tasks</a></p>`
      : `<p class="empty">loading…</p>`;
    meta.innerHTML = state.error ? `<span class="error">error: ${esc(state.error)}</span>` : "loading…";
    return;
  }
  if (r.task) {
    taskView.render(state.data, view, r, {focus});
    meta.innerHTML = `last refresh ${esc(clock(state.at))}${failed}`;
  } else {
    const shown = tasksView.render(state.data, view), total = state.data.tasks.length;
    meta.innerHTML = `${shown === total ? total : `${shown} of ${total}`} tasks · last refresh ${esc(clock(state.at))}${failed}`;
  }
}

// Fetches the page the hash names and redraws it in place; on a failure the last good data stays on screen.
// When the hash moved to another page during the fetch, that page is fetched next.
async function load() {
  for (;;) {
    const page = route().task;
    let data = null, error = null;
    try {
      data = await (page ? fetchTask(page) : fetchTasks());
    } catch (exc) {
      error = exc.message || String(exc);
    }
    if (route().task !== page) continue;
    if (state.page !== page) Object.assign(state, {page, data: null});
    if (data) Object.assign(state, {data, at: new Date()});
    state.error = error;
    break;
  }
  if (firstDraw && state.data) {
    firstDraw = false;
    return draw({focus: true});
  }
  const y = window.scrollY;
  draw();
  window.scrollTo(0, y);
}

window.addEventListener("hashchange", () => {
  if (route().task !== state.page) {
    Object.assign(state, {page: route().task, data: null, error: null});
    draw();
    window.scrollTo(0, 0);
    refresh();
    return;
  }
  window.scrollTo(0, 0);
  draw({focus: true});
});
tasksView.onChange(() => draw());
state.page = route().task;
refresh = startRefresh(document.getElementById("refresh-slot"), load);
