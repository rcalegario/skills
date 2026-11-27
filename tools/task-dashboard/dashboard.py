#!/usr/bin/env python3
"""dashboard.py - a local, read-only web view of every task in the home.

Usage:
    python tools/task-dashboard/dashboard.py [--home DIR] [--port 8765] [--no-browser]

Serves on 127.0.0.1 only and answers GET only. Routes:
    /                 the page (static/index.html)
    /static/<file>    a file under static/
    /api/tasks        every task of the home with its state, as JSON
    /api/tasks/<repo>/<id>   one task whole, for its page; 404 for an unknown, legacy or broken task
    /api/tasks/<repo>/<id>/docs/<path>   one Markdown file the task lists, as text; 404 for any other path

This file only routes; the reading lives in the modules per context (home, state, detail, graph, docs).
"""
import argparse
import json
import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import home as homemod
import state

STATIC = os.path.join(homemod.TOOL, "static")
HOST = "127.0.0.1"
# Set here, not guessed: the Windows registry may not know .css or .js, and a module script needs its type.
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
MARKDOWN = "text/markdown; charset=utf-8"


class Handler(BaseHTTPRequestHandler):
    home = None  # set by make_server

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == "/":
            return self.send_file(os.path.join(STATIC, "index.html"))
        if path.startswith("/static/"):
            return self.send_file(os.path.join(STATIC, *path[len("/static/"):].split("/")))
        if path == "/api/tasks":
            return self.send_json(state.snapshot(self.home))
        if path.startswith("/api/tasks/"):
            parts = path[len("/api/tasks/"):].split("/")
            if len(parts) > 3 and parts[2] == "docs":
                text = state.task_doc(self.home, parts[0], parts[1], "/".join(parts[3:]))
                return self.send_body(text.encode("utf-8"), MARKDOWN) if text is not None else self.send_error(404)
            found = state.task_detail(self.home, *parts) if len(parts) == 2 else None
            return self.send_json(found) if found else self.send_error(404)
        self.send_error(404)

    def refuse(self):
        # Read the body first: closing with unread data makes Windows reset the connection before the 405 arrives.
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.send_error(405, "read-only: GET only")

    do_POST = do_PUT = do_PATCH = do_DELETE = refuse

    def send_file(self, path):
        real = os.path.realpath(path)
        if os.path.commonpath([real, os.path.realpath(STATIC)]) != os.path.realpath(STATIC) or not os.path.isfile(real):
            return self.send_error(404)
        with open(real, "rb") as fh:
            body = fh.read()
        self.send_body(body, TYPES.get(os.path.splitext(real)[1].lower(), "application/octet-stream"))

    def send_json(self, data):
        self.send_body(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def send_body(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # keep the console quiet; errors still raise
        pass


def make_server(home, port):
    handler = type("BoundHandler", (Handler,), {"home": os.path.abspath(home)})
    return ThreadingHTTPServer((HOST, port), handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", help="the home folder (default: home in skills/task/config.yaml)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = ap.parse_args(argv)
    home = homemod.resolve_home(args.home)
    try:
        srv = make_server(home, args.port)
    except OSError as exc:
        sys.stderr.write("cannot listen on %s:%d: %s\n" % (HOST, args.port, exc))
        return 1
    url = "http://%s:%d/" % (HOST, srv.server_address[1])
    print("task-dashboard: %s (home %s); Ctrl+C stops it" % (url, home), flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
