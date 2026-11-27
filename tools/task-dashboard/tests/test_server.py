"""dashboard.py: a GET-only server on 127.0.0.1."""
import json
import threading
import urllib.error
import urllib.request

import pytest

import dashboard
from conftest import write


@pytest.fixture
def server(home):
    srv = dashboard.make_server(str(home), 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def call(url, method="GET"):
    req = urllib.request.Request(url, method=method, data=b"x" if method in ("POST", "PUT", "PATCH") else None)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers.get("Content-Type"), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type"), exc.read()


def test_page_and_task_list(server):
    status, ctype, body = call(server + "/")
    assert status == 200 and ctype.startswith("text/html")
    status, ctype, body = call(server + "/api/tasks")
    assert status == 200 and ctype.startswith("application/json")
    data = json.loads(body)
    assert [t["id"] for t in data["tasks"]] == ["2026-11-10-1000-old", "2026-11-12-0900-alpha"]
    assert data["generated"]


def test_page_modules_have_their_types(server):
    for path, ctype in (("/static/style.css", "text/css"), ("/static/js/main.js", "text/javascript"),
                        ("/static/js/views/tasks.js", "text/javascript")):
        status, got, _ = call(server + path)
        assert status == 200 and got.startswith(ctype), path


def test_writes_are_refused(server, home):
    before = sorted(p.name for p in (home / "tasks" / "skills").iterdir())
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        for path in ("/", "/api/tasks"):
            assert call(server + path, method)[0] == 405
    assert sorted(p.name for p in (home / "tasks" / "skills").iterdir()) == before


def test_unknown_and_escaping_paths_are_404(server):
    for path in ("/nope", "/api/other", "/static/../dashboard.py", "/static/%2e%2e/dashboard.py",
                 "/static/missing.css", "/tasks/skills/2026-11-12-0900-alpha/acs.yaml"):
        assert call(server + path)[0] == 404, path


def test_task_route_gives_one_task(server):
    status, ctype, body = call(server + "/api/tasks/skills/2026-11-12-0900-alpha")
    assert status == 200 and ctype.startswith("application/json")
    assert json.loads(body)["row"]["id"] == "2026-11-12-0900-alpha"


def test_task_route_refuses_unknown_legacy_and_escaping(server):
    for path in ("/api/tasks/skills/nope", "/api/tasks/iac/2026-11-10-1000-old", "/api/tasks/skills",
                 "/api/tasks/skills/2026-11-12-0900-alpha/acs.yaml", "/api/tasks/skills/..",
                 "/api/tasks/../tasks/skills", "/api/tasks/skills/%2e%2e%2f..%2fiac"):
        assert call(server + path)[0] == 404, path


def test_binds_localhost_only(home):
    srv = dashboard.make_server(str(home), 0)
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()



def test_docs_route_serves_a_listed_doc(server, home):
    write(home, "tasks/skills/2026-11-12-0900-alpha/brief.md", "---\ndate: 2026-11-12\n---\n# Brief é\n")
    status, ctype, body = call(server + "/api/tasks/skills/2026-11-12-0900-alpha/docs/brief.md")
    assert status == 200 and ctype == "text/markdown; charset=utf-8"
    assert body.decode("utf-8") == "# Brief é\n"
    write(home, "tasks/skills/2026-11-12-0900-alpha/context/now.md", "# Now\n")
    assert call(server + "/api/tasks/skills/2026-11-12-0900-alpha/docs/context/now.md")[0] == 200


def test_docs_route_refuses_unlisted_paths(server, home):
    alpha = "tasks/skills/2026-11-12-0900-alpha/"
    write(home, alpha + "repos/skills/README.md", "# worktree\n")
    write(home, alpha + "notes.txt", "x\n")
    base = server + "/api/tasks/skills/2026-11-12-0900-alpha/docs/"
    for rel in ("acs.yaml", "notes.txt", "repos/skills/README.md", "missing.md", "../brief.md",
                "%2e%2e/%2e%2e/2026-11-10-1000-old/README.md", "context/../README.md", ""):
        assert call(base + rel)[0] == 404, rel
    for path in ("/api/tasks/iac/2026-11-10-1000-old/docs/README.md", "/api/tasks/skills/nope/docs/README.md",
                 "/api/tasks/skills/2026-11-12-0900-alpha/other/README.md"):
        assert call(server + path)[0] == 404, path
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert call(base + "README.md", method)[0] == 405
