#!/usr/bin/env python3
"""Append cells to a Jupyter notebook from outside Jupyter.

Companion to the analyzing-logs skill. The bundled posit-mcp-repl REPL
captures stdout from agent code at the tool-call level; this script lets
the agent also persist that code + output (and any matplotlib plot PNGs)
into a runnable .ipynb the user can open and re-execute in JupyterLab.
Stdlib only. Requires Python 3.7+.

Subcommands:
  init [PATH]                Create an empty runnable notebook. If PATH is
                             omitted, an `inspect-analysis-<timestamp>.ipynb`
                             name is generated in the current directory.
                             Prints the path on stdout.
  append PATH --code-file F  Append a code cell whose source is read from F.
                             Optional --output-file attaches captured stdout
                             as a stream output. Optional --image-file
                             attaches a PNG as a display_data output so the
                             plot renders inline when the notebook is opened.

Writes are atomic: the script writes to a temp file in the same directory
and `os.replace()`s it into place, so a crash or disk-full mid-write can't
leave a partial / zero-byte notebook.
"""

import sys

if sys.version_info < (3, 7):
    sys.exit("append_to_notebook.py requires Python 3.7+")

import argparse
import base64
import datetime as _dt
import json
import os
import pathlib
import uuid


EMPTY_NB = {
    "cells": [],
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


def _atomic_write_json(path: pathlib.Path, obj) -> None:
    """Serialize `obj` to `path` atomically.

    Writes to `<path>.tmp` in the same directory, then `os.replace()`s into
    place. Avoids leaving a zero-byte or partial file if the process is
    interrupted mid-write, and means JupyterLab readers never see a half-
    written file.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, path)


def cmd_init(args: argparse.Namespace) -> int:
    if args.path is None:
        stamp = _dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        path = pathlib.Path(f"inspect-analysis-{stamp}.ipynb")
    else:
        path = pathlib.Path(args.path)
    if path.exists():
        sys.stderr.write(f"refusing to overwrite existing notebook: {path}\n")
        return 2
    _atomic_write_json(path, EMPTY_NB)
    print(path)
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    path = pathlib.Path(args.path)
    if not path.exists():
        sys.stderr.write(f"notebook does not exist: {path}. Run `init` first.\n")
        return 2
    # Validate the notebook FIRST (before consuming the code / output files),
    # so a corrupted .ipynb fails fast with a clear error instead of after
    # we've already read everything else.
    try:
        nb = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.stderr.write(f"notebook {path} is not valid JSON: {e}\n")
        return 3
    if not isinstance(nb, dict) or "cells" not in nb:
        sys.stderr.write(f"notebook {path} is not a valid nbformat document (missing 'cells')\n")
        return 3
    code = pathlib.Path(args.code_file).read_text()
    cell: dict = {
        "cell_type": "code",
        "id": uuid.uuid4().hex[:8],
        "execution_count": None,
        "metadata": {},
        "source": code,
        "outputs": [],
    }
    if args.output_file:
        output = pathlib.Path(args.output_file).read_text()
        if output:
            cell["outputs"].append({
                "output_type": "stream",
                "name": "stdout",
                "text": output,
            })
    if args.image_file:
        img_bytes = pathlib.Path(args.image_file).read_bytes()
        img_b64 = base64.b64encode(img_bytes).decode("ascii")
        cell["outputs"].append({
            "output_type": "display_data",
            "data": {"image/png": img_b64},
            "metadata": {},
        })
    nb["cells"].append(cell)
    _atomic_write_json(path, nb)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="create an empty runnable notebook")
    p_init.add_argument("path", nargs="?", help="optional path; auto-generates a timestamped name if omitted")
    p_init.set_defaults(func=cmd_init)

    p_app = sub.add_parser("append", help="append a code cell with optional captured stdout and/or PNG image")
    p_app.add_argument("path", help="path to the notebook")
    p_app.add_argument("--code-file", required=True, help="file containing the cell source")
    p_app.add_argument("--output-file", help="file containing captured stdout (optional)")
    p_app.add_argument("--image-file", help="path to a PNG to embed as a display_data output (optional)")
    p_app.set_defaults(func=cmd_append)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
