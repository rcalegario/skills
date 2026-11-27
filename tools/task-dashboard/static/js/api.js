// Reads /api/tasks, one task's /api/tasks/<repo>/<id> and its docs. The server only answers GET; nothing here writes.

async function get(url, as = "json") {
  const resp = await fetch(url, {cache: "no-store"});
  if (!resp.ok) {
    const err = new Error(resp.status === 404 ? "not found" : `HTTP ${resp.status}`);
    err.status = resp.status;
    throw err;
  }
  return resp[as]();
}

export const fetchTasks = () => get("/api/tasks");

// task is "<repo>/<id>", as the page's hash holds it.
function taskUrl(task) {
  const [repo, ...id] = task.split("/");
  return `/api/tasks/${encodeURIComponent(repo)}/${encodeURIComponent(id.join("/"))}`;
}

export const fetchTask = task => get(taskUrl(task));

// One Markdown file the task lists, as text; path is relative to the task folder, with "/".
export const fetchDoc = (task, path) =>
  get(`${taskUrl(task)}/docs/${path.split("/").map(encodeURIComponent).join("/")}`, "text");
