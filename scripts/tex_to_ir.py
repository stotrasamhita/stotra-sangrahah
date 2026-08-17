#!/usr/bin/env python3
"""Convert stotras/**/*.tex files into structured JSON IR.

Implements the parser design in docs/tex-html-conversion-design.md: a
brace-balancing scanner over a closed ~15-macro vocabulary, a running
verse-number counter mutated by reset/add/step operations in document
order, and a generic prose fallback for anything outside that vocabulary.

Usage:
    python scripts/tex_to_ir.py [input...] [--out DIR] [--check] [-v]
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

DEVA_DIGITS = "०१२३४५६७८९"

ARITY = {
    "sect": 1,
    "chapt": 1,
    "onelineshloka": 1,
    "twolineshloka": 2,
    "threelineshloka": 3,
    "fourlineindentedshloka": 4,
    "fourlineshloka": 4,
    "annotwolineshloka": 3,
    "annofourlineindentedshloka": 5,
    "dnsub": 1,
    "uvacha": 1,
}

NO_STAR_SUPPORT = {"annotwolineshloka", "annofourlineindentedshloka", "fourlineshloka"}
NEVER_NUMBERED = {"fourlineshloka"}
FOUR_LINE_MACROS = {"fourlineindentedshloka", "fourlineshloka", "annofourlineindentedshloka"}

TYPE_NAME = {
    "onelineshloka": "verse-1",
    "twolineshloka": "verse-2",
    "threelineshloka": "verse-3",
    "fourlineindentedshloka": "verse-4-indented",
    "fourlineshloka": "verse-4-plain",
    "annotwolineshloka": "verse-annotated-2",
    "annofourlineindentedshloka": "verse-annotated-4",
}

# (unstarred endings, starred endings-or-None) per line, in argument order.
ENDING_TABLE = {
    "onelineshloka": (["double-danda-numbered"], ["danda"]),
    "twolineshloka": (["danda", "double-danda-numbered"], ["danda", "double-danda"]),
    "threelineshloka": (
        ["danda", "danda", "double-danda-numbered"],
        ["danda", "danda", "double-danda"],
    ),
    "fourlineindentedshloka": (
        ["none", "danda", "none", "double-danda-numbered"],
        ["none", "danda", "none", "double-danda"],
    ),
    "fourlineshloka": (["none", "none", "none", "none"], None),
    "annotwolineshloka": (["danda", "double-danda-numbered"], None),
    "annofourlineindentedshloka": (
        ["none", "danda", "none", "double-danda-numbered"],
        None,
    ),
}

STRUCTURAL_BEGIN_END = {"center", "large", "Large", "minipage", "flushleft"}
COLUMN_ENVIRONMENTS = {"multicols", "AutoCols"}

DROPPED_ZERO_ARG = {
    "clearpage", "newpage", "smallskip", "medskip", "bigskip", "nobreak",
    "hfill", "raggedright", "selectfont", "adjustShlokaSpaceSkip",
    "nopagebreak", "normalsize", "noindent", "centering",
}
DROPPED_ONE_ARG = {"label", "vspace", "setmainfont", "mbox", "hspace"}
DROPPED_TWO_ARG = {"setlength"}  # lint-checked for begingroup/brace scoping
DROPPED_TWO_ARG_NO_LINT = {"fontsize"}
UNWRAP_ONE_ARG = {"textbf", "textsf", "textit", "emph", "centerline", "textsuperscript"}

# \X for X not a letter: known literal-producing escapes (\% is already
# unescaped during comment stripping, so it never reaches here).
ESCAPED_SYMBOLS = {"&": "&", "_": "_", "#": "#", " ": " ", "-": ""}

# The reliable signal for a closing colophon is the leading "इति" ("thus"),
# not the specific closing word (सम्पूर्णम्/समाप्तम्/स्तोत्रम्/स्तवः/... all occur).
# Note: \b is unreliable right after Devanagari dependent vowel signs (they're
# Unicode combining marks, category Mn -- not \w characters to Python's re
# module), so this requires an explicit whitespace separator instead of \b.
PUSHPIKA_RE = re.compile(r"॥\s*इति\s.*॥")
ATTRIBUTION_RE = re.compile(r"^[{}\s]*-{2,3}(.+)$")
NEWCOMMAND_RE = re.compile(r"\\newcommand\{\\([A-Za-z]+)\}")
INLINE_STRIP_RE = re.compile(r"\\hspace\{[^{}]*\}|\\mbox\{\}|\\nobreak\b")


class ParseError(Exception):
    def __init__(self, path, line_no, msg):
        super().__init__(f"{path}:{line_no}: {msg}")
        self.path = path
        self.line_no = line_no


def to_deva(n):
    """Map a non-negative int to its Devanagari numeral string, mirroring
    shloka.sty's \\devanumberrecurse digit-by-digit conversion."""
    if n == 0:
        return DEVA_DIGITS[0]
    out = []
    while n > 0:
        out.append(DEVA_DIGITS[n % 10])
        n //= 10
    return "".join(reversed(out))


class CounterModel:
    """The shlokacount counter: one running value mutated by reset/add/step,
    applied in document order. verse_number/verse_number_deva are read off
    this at the moment each verse block is emitted -- no separate resolve
    pass, so composite sequences (e.g. reset immediately followed by an
    add-N) just work as two sequential mutations."""

    def __init__(self):
        self.value = 0

    def reset(self):
        self.value = 0

    def add(self, n):
        self.value += n

    def step(self):
        self.value += 1
        return self.value


def strip_comments_and_extract_meta(text):
    """Strip TeX comments (unescaped %...), unescape \\% -> %, and pull out
    the % --meta-- / % --end-meta-- block (if present) into a dict."""
    meta_lines = []
    body_lines = []
    in_meta = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "% --meta--":
            in_meta = True
            continue
        if stripped == "% --end-meta--":
            in_meta = False
            continue
        if in_meta:
            meta_lines.append(line)
            continue
        out = []
        i, n = 0, len(line)
        while i < n:
            c = line[i]
            if c == "\\" and i + 1 < n:
                nxt = line[i + 1]
                out.append("%" if nxt == "%" else line[i : i + 2])
                i += 2
                continue
            if c == "%":
                break
            out.append(c)
            i += 1
        body_lines.append("".join(out))

    meta = {}
    for ml in meta_lines:
        s = ml.strip()
        if s.startswith("%"):
            s = s[1:].strip()
        if ":" in s:
            k, v = s.split(":", 1)
            meta[k.strip()] = v.strip()
    return "\n".join(body_lines), meta


class TexScanner:
    """Brace-balancing scanner. read_braced_arg() tracks nesting depth
    character-by-character so nested \\hspace{}/\\rlap{} inside a verse-line
    argument is captured verbatim as part of that argument, never re-parsed
    as its own command."""

    CMD_RE = re.compile(r"\\([A-Za-z]+)(\*)?")

    def __init__(self, text, path):
        self.text = text
        self.path = path
        self.pos = 0
        self.n = len(text)

    def line_at(self, pos):
        return self.text.count("\n", 0, pos) + 1

    def eof(self):
        return self.pos >= self.n

    def peek(self):
        return self.text[self.pos] if self.pos < self.n else ""

    def read_command(self):
        m = self.CMD_RE.match(self.text, self.pos)
        if not m:
            raise ParseError(
                self.path,
                self.line_at(self.pos),
                f"unrecognized escape sequence near {self.text[self.pos:self.pos+10]!r}",
            )
        self.pos = m.end()
        return m.group(1), bool(m.group(2))

    def skip_ws(self):
        while self.pos < self.n and self.text[self.pos] in " \t\n":
            self.pos += 1

    def read_braced_arg(self):
        self.skip_ws()
        if self.peek() != "{":
            raise ParseError(
                self.path,
                self.line_at(self.pos),
                f"expected '{{' argument, found {self.peek()!r}",
            )
        start = self.pos
        depth = 0
        i = self.pos
        while i < self.n:
            c = self.text[i]
            if c == "\\" and i + 1 < self.n:
                i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    inner = self.text[start + 1 : i]
                    self.pos = i + 1
                    return inner
            i += 1
        raise ParseError(
            self.path,
            self.line_at(start),
            "unbalanced braces: argument opened here never closed before EOF",
        )

    def read_bracket_arg(self):
        self.skip_ws()
        if self.peek() != "[":
            return None
        start = self.pos
        end = self.text.find("]", start)
        if end == -1:
            raise ParseError(self.path, self.line_at(start), "unclosed '[' argument before EOF")
        self.pos = end + 1
        return self.text[start + 1 : end]

    def splice(self, s):
        """Re-inject text at the current position so it gets scanned normally
        on the next loop iteration -- used to unwrap \\hyperref[...]{X} and
        \\textbf{X} etc. into X, so a macro call inside X (e.g.
        \\hyperref[...]{\\closesection}) is still dispatched properly rather
        than dumped as literal backslash-text."""
        self.text = self.text[: self.pos] + s + self.text[self.pos :]
        self.n = len(self.text)


def clean_line_text(s):
    s = INLINE_STRIP_RE.sub("", s)
    s = s.replace("~", " ")  # TeX non-breaking space
    return re.sub(r"\s+", " ", s).strip()


def expand_local_macros(text, path):
    """Pre-scan for \\newcommand{\\foo}{body} near the top of the file and
    splice `body` in for every later bare \\foo -- handles file-local macros
    like NamaRamayanam.tex's \\jaya generically, not as a hardcoded case."""
    while True:
        m = NEWCOMMAND_RE.search(text)
        if not m:
            return text
        name = m.group(1)
        scanner = TexScanner(text, path)
        scanner.pos = m.end()
        body = scanner.read_braced_arg()
        text = text[: m.start()] + text[scanner.pos :]
        text = re.sub(r"\\" + re.escape(name) + r"\b", lambda _match: body, text)


def _prose_block(lines):
    return {"type": "prose", "lines": list(lines), "text": " ".join(lines)}


def flush_prose(buf, blocks):
    text = "".join(buf)
    buf.clear()
    lines = [clean_line_text(l) for l in text.split("\n")]
    lines = [l for l in lines if l]
    if not lines:
        return
    prose_lines = []
    for line in lines:
        am = ATTRIBUTION_RE.match(line)
        if am:
            if prose_lines:
                blocks.append(_prose_block(prose_lines))
                prose_lines = []
            blocks.append({"type": "attribution", "text": am.group(1).strip()})
            continue
        pm = PUSHPIKA_RE.search(line)
        if pm:
            if prose_lines:
                blocks.append(_prose_block(prose_lines))
                prose_lines = []
            blocks.append({"type": "pushpika", "text": pm.group(0)})
            continue
        prose_lines.append(line)
    if prose_lines:
        blocks.append(_prose_block(prose_lines))


def emit_verse_block(name, starred, args, counter):
    citation = None
    verse_args = args
    if name == "annotwolineshloka":
        verse_args, citation = args[:2], args[2]
    elif name == "annofourlineindentedshloka":
        verse_args, citation = args[:4], args[4]

    endings_unstarred, endings_starred = ENDING_TABLE[name]
    endings = endings_starred if (starred and endings_starred is not None) else endings_unstarred

    numbered = name not in NEVER_NUMBERED and not starred
    if numbered:
        vnum = counter.step()
        vnum_deva = to_deva(vnum)
    else:
        vnum, vnum_deva = None, None

    pada_tags = ["odd", "even", "odd", "even"] if name in FOUR_LINE_MACROS else [None] * len(verse_args)

    lines = [
        {"pada": pada, "text": clean_line_text(text), "ending": ending}
        for text, pada, ending in zip(verse_args, pada_tags, endings)
    ]

    block = {
        "type": TYPE_NAME[name],
        "starred": starred,
        "verse_number": vnum,
        "verse_number_deva": vnum_deva,
        "lines": lines,
    }
    if citation is not None:
        block["citation"] = clean_line_text(citation)
    return block


def parse_blocks(text, path, warn):
    scanner = TexScanner(text, path)
    counter = CounterModel()
    blocks = []
    prose_buf = []
    scope_stack = []
    begingroup_depth = 0
    brace_depth = 0

    def flush():
        flush_prose(prose_buf, blocks)

    while not scanner.eof():
        c = scanner.peek()

        if c == "\\":
            nxt = scanner.text[scanner.pos + 1] if scanner.pos + 1 < scanner.n else ""
            if nxt == "\\":
                scanner.pos += 2
                scanner.read_bracket_arg()
                prose_buf.append("\n")
                continue
            if nxt in ESCAPED_SYMBOLS:
                prose_buf.append(ESCAPED_SYMBOLS[nxt])
                scanner.pos += 2
                continue

            name, starred = scanner.read_command()

            if name in ("begin", "end"):
                envname = scanner.read_braced_arg().strip()
                if name == "begin":
                    if envname in STRUCTURAL_BEGIN_END:
                        if envname == "minipage":
                            scanner.read_bracket_arg()
                            scanner.read_braced_arg()  # width, e.g. \begin{minipage}{\linewidth}
                        scope_stack.append(envname)
                    elif envname == "multicols":
                        n_arg = scanner.read_braced_arg().strip()
                        try:
                            ncols = int(n_arg)
                        except ValueError:
                            warn(f"non-numeric \\begin{{multicols}}{{{n_arg}}}, recording n=null")
                            ncols = None
                        flush()
                        blocks.append({"type": "columns-open", "n": ncols, "source": "multicols"})
                        scope_stack.append(envname)
                    elif envname == "AutoCols":
                        scanner.read_bracket_arg()
                        flush()
                        blocks.append({"type": "columns-open", "n": None, "source": "AutoCols"})
                        scope_stack.append(envname)
                    else:
                        warn(f"unrecognized \\begin{{{envname}}}, treated as transparent")
                        scope_stack.append(envname)
                else:
                    if not scope_stack:
                        raise ParseError(path, scanner.line_at(scanner.pos), f"\\end{{{envname}}} with no matching \\begin")
                    top = scope_stack.pop()
                    if top != envname:
                        raise ParseError(
                            path,
                            scanner.line_at(scanner.pos),
                            f"\\end{{{envname}}} does not match innermost \\begin{{{top}}}",
                        )
                    if envname in COLUMN_ENVIRONMENTS:
                        flush()
                        blocks.append({"type": "columns-close"})
                continue

            if name in ("sect", "chapt"):
                (title,) = (scanner.read_braced_arg(),)
                flush()
                counter.reset()
                blocks.append({"type": "heading", "macro": name, "text": title.strip(), "resets_counter": True})
                continue

            if name == "dnsub":
                (label,) = (scanner.read_braced_arg(),)
                flush()
                blocks.append({"type": "subheading", "macro": "dnsub", "text": label.strip()})
                continue

            if name == "uvacha":
                (speaker,) = (scanner.read_braced_arg(),)
                flush()
                blocks.append({"type": "uvacha", "text": speaker.strip()})
                continue

            if name in ARITY:
                nargs = ARITY[name]
                if starred and name in NO_STAR_SUPPORT:
                    warn(f"\\{name}* used but macro has no starred form; treating as unstarred")
                    starred = False
                args = [scanner.read_braced_arg() for _ in range(nargs)]
                flush()
                blocks.append(emit_verse_block(name, starred, args, counter))
                continue

            if name == "resetShloka":
                flush()
                counter.reset()
                blocks.append({"type": "counter-adjust", "op": "reset"})
                continue

            if name == "addtocounter":
                arg1 = scanner.read_braced_arg().strip()
                arg2 = scanner.read_braced_arg().strip()
                if arg1 != "shlokacount":
                    raise ParseError(
                        path,
                        scanner.line_at(scanner.pos),
                        f"\\addtocounter{{{arg1}}} -- unexpected counter, only 'shlokacount' is supported",
                    )
                try:
                    n = int(arg2)
                except ValueError:
                    raise ParseError(path, scanner.line_at(scanner.pos), f"\\addtocounter{{shlokacount}}{{{arg2}}} -- non-integer amount")
                flush()
                counter.add(n)
                blocks.append({"type": "counter-adjust", "op": "add", "n": n})
                continue

            if name in ("closesection", "closesub"):
                flush()
                blocks.append({"type": "decoration", "style": name})
                continue

            if name == "begingroup":
                begingroup_depth += 1
                continue
            if name == "endgroup":
                begingroup_depth = max(0, begingroup_depth - 1)
                continue

            if name in DROPPED_ZERO_ARG:
                scanner.read_bracket_arg()  # e.g. \nopagebreak[4]
                continue

            if name in DROPPED_ONE_ARG:
                scanner.read_bracket_arg()  # e.g. \setmainfont[Script=Devanagari]{Siddhanta}
                scanner.read_braced_arg()
                continue

            if name in DROPPED_TWO_ARG:
                scanner.read_braced_arg()
                scanner.read_braced_arg()
                if begingroup_depth == 0 and brace_depth == 0:
                    warn(f"\\{name} outside \\begingroup/\\endgroup (or brace-group) scope")
                continue

            if name in DROPPED_TWO_ARG_NO_LINT:
                scanner.read_braced_arg()
                scanner.read_braced_arg()
                continue

            if name == "fontspec":
                scanner.read_bracket_arg()
                scanner.read_braced_arg()
                continue

            if name in UNWRAP_ONE_ARG:
                inner = scanner.read_braced_arg()
                scanner.splice(inner)
                continue

            if name == "hyperref":
                scanner.read_bracket_arg()
                inner = scanner.read_braced_arg()
                scanner.splice(inner)
                continue

            warn(f"unrecognized macro \\{name}{'*' if starred else ''}, kept as literal text")
            prose_buf.append("\\" + name + ("*" if starred else ""))
            continue

        elif c == "~":
            prose_buf.append(" ")  # TeX non-breaking space
            scanner.pos += 1
            continue
        elif c == "{":
            brace_depth += 1
            scanner.pos += 1
            continue
        elif c == "}":
            if brace_depth == 0:
                raise ParseError(path, scanner.line_at(scanner.pos), "unmatched '}' with no open group")
            brace_depth -= 1
            scanner.pos += 1
            continue
        else:
            prose_buf.append(c)
            scanner.pos += 1
            continue

    flush()
    if scope_stack:
        raise ParseError(path, scanner.line_at(scanner.n), f"unclosed environment(s) at EOF: {scope_stack}")
    if brace_depth != 0:
        raise ParseError(path, scanner.line_at(scanner.n), f"unbalanced braces at EOF (depth={brace_depth})")
    return blocks


def slugify(name):
    s = re.sub(r"(?<!^)(?=[A-Z])", "-", name)
    return s.lower()


def build_ir(path, blocks, meta):
    slug = slugify(path.stem)
    category = path.parent.name
    for i, b in enumerate(blocks):
        if b["type"].startswith("verse-"):
            b["verse_id"] = f"{slug}-b{i:04d}"
            b["plain_text"] = " ".join(l["text"] for l in b["lines"])
    columns_hint = next((b.get("n") for b in blocks if b["type"] == "columns-open"), None)
    return {
        "source_file": str(path),
        "slug": slug,
        "category": category,
        "meta": meta,
        "columns_hint": columns_hint,
        "blocks": blocks,
    }


def process_file(path):
    warnings = []

    def warn(msg):
        warnings.append(msg)
        logging.warning(f"{path}: {msg}")

    text = path.read_text(encoding="utf-8")
    body, meta = strip_comments_and_extract_meta(text)
    body = expand_local_macros(body, str(path))
    blocks = parse_blocks(body, str(path), warn)
    return build_ir(path, blocks, meta), warnings


def iter_input_files(inputs):
    paths = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            paths.extend(sorted(p.rglob("*.tex")))
        elif p.is_file():
            paths.append(p)
        else:
            raise FileNotFoundError(str(p))
    return paths


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert stotra .tex files to structured JSON IR.")
    ap.add_argument("input", nargs="*", default=["stotras"], help="Files or directories to convert (default: stotras/)")
    ap.add_argument("--out", default="_build/ir", help="Output directory root (default: _build/ir)")
    ap.add_argument(
        "--check", "--dry-run", dest="check", action="store_true",
        help="Parse only, write nothing; exit non-zero if any file fails to parse",
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="Show lint warnings")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR, format="%(levelname)s: %(message)s")

    paths = iter_input_files(args.input)
    if not paths:
        print("No .tex files found.", file=sys.stderr)
        return 1

    out_root = Path(args.out)
    n_errors = 0
    n_warnings = 0
    for path in paths:
        try:
            ir, warnings = process_file(path)
        except ParseError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            n_errors += 1
            continue
        n_warnings += len(warnings)
        if not args.check:
            out_path = out_root / ir["category"] / f"{ir['slug']}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(ir, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if n_errors:
        print(f"FAILED: {n_errors} of {len(paths)} file(s) had a hard parse error.", file=sys.stderr)
        return 1

    suffix = "" if args.check else f", wrote JSON to {out_root}/"
    print(f"OK: parsed {len(paths)} file(s) ({n_warnings} lint warning(s)){suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
