#!/usr/bin/env python3
"""Flask front-end for local phylogenetic tools (gs2, panjep, sj).

Run with a Python that has flask and ete3 installed, e.g.:

    /Users/qm/opt/anaconda3/bin/python app.py

Environment variables:
    BIND_HOST  interface to bind (default 127.0.0.1)
    BIND_PORT  port to listen on (default 8080)
"""

from __future__ import annotations

import datetime
import logging
import os
import random
import re
import shlex
import subprocess
import tempfile

from flask import Flask, abort, render_template, request, send_from_directory, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from tools import TOOLS, BoolField
from viz import ascii_tree, render_tree_svg

logger = logging.getLogger("webserver")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
_RE_RUN_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9]{6}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# Respect X-Forwarded-* headers from the nginx reverse proxy so url_for()
# generates correct absolute URLs and request.remote_addr reflects the client.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


@app.context_processor
def inject_tools():
    return {"tools": list(TOOLS.values())}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/tool/<slug>", methods=["GET", "POST"])
def tool_view(slug):
    tool = TOOLS.get(slug)
    if tool is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "tool.html",
            tool=tool,
            values=tool.default_values(),
            input_text="",
            result=None,
            error=None,
        )

    input_text = request.form.get("input", "")
    raw_values = {}
    for f in tool.fields:
        if isinstance(f, BoolField):
            raw_values[f.name] = bool(request.form.get(f.name))
        else:
            raw_values[f.name] = request.form.get(f.name, "")

    try:
        parsed = {f.name: f.parse(raw_values.get(f.name)) for f in tool.fields}
    except ValueError as ve:
        return render_template(
            "tool.html",
            tool=tool,
            values=raw_values,
            input_text=input_text,
            result=None,
            error=str(ve),
        )

    if not input_text.strip():
        return render_template(
            "tool.html",
            tool=tool,
            values=raw_values,
            input_text=input_text,
            result=None,
            error="Input is empty.",
        )

    cmd = tool.build_command(parsed)
    result = _execute(tool, cmd, input_text)
    result["command"] = (
        " ".join(shlex.quote(a) for a in cmd) + " <input-file>"
    )

    if result["returncode"] == 0 and result["stdout"].strip():
        svg, viz_err = render_tree_svg(result["stdout"])
        result["svg"] = svg
        result["viz_error"] = viz_err
        result["ascii"] = ascii_tree(result["stdout"])
        run_id, tree_files = _save_newick_trees(result["stdout"])
        result["run_id"] = run_id
        result["tree_files"] = tree_files
    else:
        result["svg"] = None
        result["viz_error"] = None
        result["ascii"] = None
        result["run_id"] = None
        result["tree_files"] = []

    return render_template(
        "tool.html",
        tool=tool,
        values=raw_values,
        input_text=input_text,
        result=result,
        error=None,
    )


def _generate_run_id() -> str:
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    rand = random.randint(0, 999999)
    return f"{timestamp}-{rand:06d}"


def _save_newick_trees(stdout: str) -> tuple[str, list[dict]]:
    """Persist Newick trees from ``stdout`` under ./results/<run_id>/.

    Splits on ``;`` so each tree in the output is written to its own file.
    Returns the run id and a list of {name, url} dicts for the saved files.
    """
    run_id = _generate_run_id()
    run_dir = os.path.join(RESULTS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    trees = [t.strip() for t in stdout.split(";") if t.strip()]
    files: list[dict] = []
    for i, tree in enumerate(trees, 1):
        fname = "tree.nwk" if len(trees) == 1 else f"tree_{i}.nwk"
        path = os.path.join(run_dir, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(tree + ";\n")
        files.append({
            "name": fname,
            "url": url_for("result_file", run_id=run_id, filename=fname),
        })
    return run_id, files


@app.route("/results/<run_id>/<path:filename>")
def result_file(run_id: str, filename: str):
    if not _RE_RUN_ID.match(run_id):
        abort(404)
    directory = os.path.join(RESULTS_DIR, run_id)
    if not os.path.isdir(directory):
        abort(404)
    return send_from_directory(directory, filename, as_attachment=False)


def _execute(tool, cmd, input_text: str) -> dict:
    """Run the tool binary with ``input_text`` written to a temporary file.

    The temp file is created inside ``tool.cwd`` so that relative paths and
    side-files (e.g. MMseqs2 scratch dirs) resolve as the binary expects.
    """
    with tempfile.NamedTemporaryFile(
        "w", suffix=".in", delete=False, dir=tool.cwd, encoding="utf-8"
    ) as fh:
        fh.write(input_text)
        input_path = fh.name

    try:
        full_cmd = list(cmd) + [input_path]
        logger.info("Running: %s", " ".join(shlex.quote(a) for a in full_cmd))
        try:
            proc = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=tool.timeout,
                cwd=tool.cwd,
            )
        except subprocess.TimeoutExpired:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Timed out after {tool.timeout}s",
            }
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    finally:
        try:
            os.unlink(input_path)
        except OSError:
            pass


def _check_binaries():
    for tool in TOOLS.values():
        if not (os.path.isfile(tool.binary) and os.access(tool.binary, os.X_OK)):
            logger.warning(
                "binary missing or not executable for %s: %s", tool.slug, tool.binary
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _check_binaries()
    host = os.environ.get("BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("BIND_PORT", "8080"))
    app.run(host=host, port=port, debug=False, threaded=True)
