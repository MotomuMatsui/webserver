"""Tool registry and form-field abstractions.

Adding a new tool is a matter of defining a ToolSpec with a list of Field
instances and registering it in TOOLS at the bottom of this file.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_RE_INT = re.compile(r"^-?\d+$")
_RE_FLOAT = re.compile(r"^-?\d+(\.\d+)?$")


# ---------------------------------------------------------------------------
# Field abstractions
# ---------------------------------------------------------------------------


@dataclass
class Field:
    name: str
    label: str
    flag: Optional[str] = None
    help: str = ""
    default: Any = None

    def parse(self, raw: Any) -> Any:
        return raw

    def to_args(self, value: Any) -> List[str]:
        if value in (None, ""):
            return []
        return [self.flag, str(value)] if self.flag else [str(value)]

    def render(self, current: Any) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


@dataclass
class IntField(Field):
    min: Optional[int] = None
    max: Optional[int] = None
    skip_if: Optional[int] = None  # when value equals this, do not emit the flag

    def parse(self, raw):
        s = (raw or "").strip() if isinstance(raw, str) else raw
        if s in (None, ""):
            return None
        if not isinstance(s, str) or not _RE_INT.match(s):
            raise ValueError(f"{self.label}: integer required")
        v = int(s)
        if self.min is not None and v < self.min:
            raise ValueError(f"{self.label}: must be >= {self.min}")
        if self.max is not None and v > self.max:
            raise ValueError(f"{self.label}: must be <= {self.max}")
        return v

    def to_args(self, value):
        if value is None:
            return []
        if self.skip_if is not None and value == self.skip_if:
            return []
        return [self.flag, str(value)] if self.flag else [str(value)]

    def render(self, current):
        v = "" if current is None else str(current)
        attrs = []
        if self.min is not None:
            attrs.append(f'min="{self.min}"')
        if self.max is not None:
            attrs.append(f'max="{self.max}"')
        return (
            f'<input type="number" name="{html.escape(self.name)}" '
            f'value="{html.escape(v)}" {" ".join(attrs)}>'
        )


@dataclass
class FloatField(Field):
    min: Optional[float] = None
    max: Optional[float] = None

    def parse(self, raw):
        s = (raw or "").strip() if isinstance(raw, str) else raw
        if s in (None, ""):
            return None
        if not isinstance(s, str) or not _RE_FLOAT.match(s):
            raise ValueError(f"{self.label}: number required")
        v = float(s)
        if self.min is not None and v < self.min:
            raise ValueError(f"{self.label}: must be >= {self.min}")
        if self.max is not None and v > self.max:
            raise ValueError(f"{self.label}: must be <= {self.max}")
        return v

    def render(self, current):
        v = "" if current is None else str(current)
        return (
            f'<input type="text" name="{html.escape(self.name)}" '
            f'value="{html.escape(v)}">'
        )


@dataclass
class SelectField(Field):
    choices: List[str] = dc_field(default_factory=list)

    def parse(self, raw):
        if raw in (None, ""):
            return None
        if raw not in self.choices:
            raise ValueError(f"{self.label}: must be one of {self.choices}")
        return raw

    def render(self, current):
        opts = []
        for c in self.choices:
            sel = " selected" if current == c else ""
            opts.append(
                f'<option value="{html.escape(c)}"{sel}>{html.escape(c)}</option>'
            )
        return f'<select name="{html.escape(self.name)}">{"".join(opts)}</select>'


@dataclass
class BoolField(Field):
    def parse(self, raw):
        return bool(raw)

    def to_args(self, value):
        return [self.flag] if value and self.flag else []

    def render(self, current):
        checked = " checked" if current else ""
        return (
            f'<input type="checkbox" name="{html.escape(self.name)}" '
            f'value="1"{checked}>'
        )


# ---------------------------------------------------------------------------
# Tool spec
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    slug: str
    name: str
    short_name: str
    description: str
    binary: str
    cwd: str
    fields: List[Field] = dc_field(default_factory=list)
    extra_args: List[str] = dc_field(default_factory=list)
    input_help: str = ""
    timeout: int = 300

    def build_command(self, parsed: dict) -> List[str]:
        args: List[str] = [self.binary]
        for f in self.fields:
            args += f.to_args(parsed.get(f.name))
        args += list(self.extra_args)
        return args

    def default_values(self) -> dict:
        return {f.name: f.default for f in self.fields}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GS = ToolSpec(
    slug="GS",
    name="GS::Graph Splitting Method v2.5",
    short_name="GS",
    description=(
        "Graph Splitting tree inference from FASTA sequences, distance matrices, "
        "or similarity matrices."
    ),
    binary=os.path.join(BASE_DIR, "gs", "gs2"),
    cwd=os.path.join(BASE_DIR, "gs"),
    input_help=(
        "Paste a FASTA file (protein or nucleotide; type is auto-detected), "
        "PHYLIP distance matrix (enable -d), or similarity matrix (enable -w)."
    ),
    fields=[
        IntField("e", "EP replicates (-e)", flag="-e",
                 help="Replicates for the EP method.",
                 default=0, min=0, max=1000, skip_if=0),
        SelectField("b", "Bootstrap method (-b)", flag="-b",
                    help="tbe or fbs.",
                    default="tbe", choices=["tbe", "fbs"]),
        IntField("r", "Random seed (-r)", flag="-r",
                 help="Optional; default is a random number.",
                 default=None, min=1),
        IntField("t", "Threads (-t)", flag="-t",
                 help="Threads for the homology search (MMseqs2 / blastn).",
                 default=1, min=1),
        FloatField("m", "MMseqs sensitivity (-m)", flag="-m",
                   help="1.0 – 7.5. Protein input only (ignored for nucleotide / blastn).",
                   default=7.5, min=1.0, max=7.5),
        BoolField("d", "Distance matrix input (-d)", flag="-d"),
        BoolField("w", "Similarity matrix input (-w)", flag="-w"),
        BoolField("l", "Newick with actual names (-l)", flag="-l",
                  default=True),
    ],
    extra_args=["-s"],
)

PANJEP = ToolSpec(
    slug="PANJEP",
    name="PANJEP::PA-based NJ with EP v1.0",
    short_name="PANJEP",
    description=(
        "(P)airwise (A)lignment-based (N)eighbor-(J)oining tree inference with (E)edge (P)urterbaton branch support."
    ),
    binary=os.path.join(BASE_DIR, "panjep", "panjep"),
    cwd=os.path.join(BASE_DIR, "panjep"),
    input_help=(
        "PHYLIP distance matrix OR FASTA sequence file (protein/nucleotide); "
        "format and sequence type are auto-detected."
    ),
    fields=[
        IntField("t", "OpenMP threads (-t)", flag="-t",
                 help="Leave blank to use all cores.",
                 default=None, min=1, max=4),
        FloatField("s", "Search sensitivity (-s)", flag="-s",
                   help=("1.0 – 7.5; FASTA input only. "
                         "Protein → MMseqs2 -s; "
                         "nucleotide → blastn -task "
                         "(<3 megablast, 3–5 dc-megablast, "
                         "5–7 blastn, ≥7 blastn-short)."),
                   default=7.5, min=1.0, max=7.5),
        SelectField("d", "Evolutionary-distance method (-d)", flag="-d",
                    help=("FASTA only. auto = ScoreDist for protein, "
                          "Poisson(nc=4) for nucleotide. "
                          "scoredist/poisson/pdist work for any input; "
                          "jc69/k2p/f81/f84/tn93/logdet/ry/rysym are DNA-specific "
                          "(k2p/f84/tn93/logdet/ry/rysym are DNA-only)."),
                    default="auto",
                    choices=["auto", "scoredist", "poisson", "pdist",
                             "jc69", "k2p", "f81", "f84", "tn93",
                             "logdet", "ry", "rysym"]),
        IntField("e", "EP iterations (-e)", flag="-e",
                 help="FASTA only; set 0 to disable.",
                 default=100, min=0, max=1000),
        BoolField("v", "Print timing / statistics (-v)", flag="-v"),
    ],
)

SJ = ToolSpec(
    slug="SJ",
    name="SJ::Splitting and Joining Method v0.1",
    short_name="SJ",
    description=(
        "Hybrid GS + PANJEP tree inference: each clade is resolved by spectral "
        "clustering (GS) or neighbor-joining (PANJEP) according to its "
        "similarity-matrix transitivity."
    ),
    binary=os.path.join(BASE_DIR, "sj", "sj"),
    cwd=os.path.join(BASE_DIR, "sj"),
    input_help=(
        "Paste a FASTA file (protein or nucleotide; alphabet is auto-detected "
        "from residue composition)."
    ),
    fields=[
        FloatField("T", "Transitivity threshold (-T)", flag="-T",
                   help=("Clades with transitivity > T are resolved by NJ "
                         "(panjep); otherwise by GS spectral clustering. "
                         "Range (0, 1]."),
                   default=0.68, min=0.0, max=1.0),
        IntField("t", "Threads (-t)", flag="-t",
                 help="Threads for both the homology search and OpenMP.",
                 default=1, min=1),
        FloatField("m", "Search sensitivity (-m)", flag="-m",
                   help=("1.0 – 7.5. "
                         "Protein → MMseqs2 -s; "
                         "nucleotide → blastn -task "
                         "(<3 megablast, <5 dc-megablast, "
                         "<7 blastn, ≥7 blastn-short)."),
                   default=7.5, min=1.0, max=7.5),
        BoolField("l", "Newick with actual names (-l)", flag="-l",
                  default=True),
        BoolField("s", "Silent mode (-s)", flag="-s",
                  default=True),
    ],
)

TOOLS = {t.slug: t for t in (GS, PANJEP, SJ)}
