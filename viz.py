"""Tree visualization helpers built on top of the ETE Toolkit (ete3)."""

from __future__ import annotations

import os
import tempfile
from typing import Optional, Tuple

# A few Newick parsing formats to try. Different tools emit support/branch
# length combinations that only parse under specific ETE format codes.
# 1: flexible (internal node names)
# 0: branch support + branch length
# 5: internal and leaf names + branch lengths
# 100: free-form
_NEWICK_FORMATS = (1, 0, 5, 100, 3, 2)


def _parse_newick(newick: str):
    from ete3 import Tree  # imported lazily so app still boots without ete3

    last_err: Optional[Exception] = None
    cleaned = newick.strip()
    if not cleaned:
        return None, ValueError("empty Newick string")
    for fmt in _NEWICK_FORMATS:
        try:
            return Tree(cleaned, format=fmt), None
        except Exception as e:  # noqa: BLE001
            last_err = e
    return None, last_err


def render_tree_svg(newick: str) -> Tuple[Optional[str], Optional[str]]:
    """Render a Newick string to an SVG document.

    Returns ``(svg_text, None)`` on success or ``(None, error_message)`` on
    failure. The SVG is returned as a string ready to be inlined into HTML.
    """
    try:
        from ete3 import TreeStyle, NodeStyle
    except ImportError as e:  # pragma: no cover
        return None, f"ete3 not available: {e}"

    tree, err = _parse_newick(newick)
    if tree is None:
        return None, f"Could not parse Newick: {err}"

    ts = TreeStyle()
    ts.show_leaf_name = True
    ts.show_branch_length = False
    ts.show_branch_support = True
    ts.scale = 60
    ts.branch_vertical_margin = 6

    base_style = NodeStyle()
    base_style["size"] = 4
    base_style["fgcolor"] = "#2a6496"
    base_style["hz_line_width"] = 1
    base_style["vt_line_width"] = 1
    for node in tree.traverse():
        node.set_style(base_style)

    fd, tmppath = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    try:
        tree.render(tmppath, tree_style=ts)
        with open(tmppath, "r", encoding="utf-8") as f:
            svg = f.read()
        return svg, None
    except Exception as e:  # noqa: BLE001
        return None, f"Render failed: {e}"
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass


def ascii_tree(newick: str) -> Optional[str]:
    """Return an ASCII-art rendering of the tree, or None if parsing fails."""
    tree, _ = _parse_newick(newick)
    if tree is None:
        return None
    return str(tree)
