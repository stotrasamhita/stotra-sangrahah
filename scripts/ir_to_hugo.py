#!/usr/bin/env python3
"""Convert tex_to_ir.py's JSON IR into Hugo content files.

Reads _build/ir/<category>/<slug>.json (see docs/tex-html-conversion-design.md
and tex_to_ir.py) and writes _build/hugo-content/<category>/<slug>.md: a
Hugo content file with JSON front matter (title, taxonomies, plain params --
real metadata only) followed by the verse content rendered directly as raw
HTML (Hugo's goldmark `unsafe = true` passes this through untouched).

Rendering lives here, in Python, rather than in a Hugo/Go template, for two
reasons found by actually building and inspecting the site, not assumed up
front: (1) it's the same testable/debuggable pattern already used for
tex_to_ir.py, and (2) hugo-book's own sidebar-menu partial only links a page
if its rendered `.Content` is non-empty -- an earlier version of this script
put the verse data in front matter and left the Markdown body empty, relying
on a custom template to render `.Params.blocks`; that produced a site where
every stotra page built fine on its own but was invisible in the nav tree
(bare, unlinked list items), because hugo-book's `.Content` never saw any of
it. Emitting real HTML as the body sidesteps that entirely and needs no
template overrides in the site repo at all.

Transform rules (see docs/tex-html-conversion-design.md and the Phase 3
plan for rationale):
  1. Drop every counter-adjust block (parse-time-only, already reflected in
     later verse_number values).
  2. The first heading block becomes the page title and is removed from the
     rendered body; any later heading blocks are kept and rendered in-body.
  3. Drop verse-4-plain blocks whose lines are all empty text (fixes the
     known BhajaGovindam.tex \\fourlineshloka{}{}{}{} data-quality issue,
     generically -- not file-specific).
  4. Group columns-open/columns-close spans into one nested
     {"type": "columns", "n": ..., "source": ..., "blocks": [...]} block,
     rendered as a single wrapping <div style="column-count:N">.

Usage:
    python scripts/ir_to_hugo.py [input...] [--out DIR]
"""
import argparse
import html as html_lib
import json
import sys
from pathlib import Path

TAXONOMY_META_KEYS = ("deity", "composer", "chandas")

ENDING_GLYPH = {"danda": "।", "double-danda": "॥"}


def esc(s):
    return html_lib.escape(str(s), quote=False)


# ---------------------------------------------------------------------------
# IR block transforms (pure data, no HTML)
# ---------------------------------------------------------------------------

def drop_counter_adjust(blocks):
    return [b for b in blocks if b["type"] != "counter-adjust"]


# Files with no single natural title heading -- either a "compilation" file
# bundling several independently-\sect-ed verses with no umbrella heading of
# its own (nitya-shloka: 11 \sect calls, none of which is "the" title), or a
# title embedded in plain prose rather than a \sect call at all
# (kanchi-kamakshi-churnika's title literally appears as plain danda-wrapped
# text: "॥श्री-कामाक्षी चूर्णिका॥"). There's no reliable way to derive these
# automatically, so they're curated by hand here -- extend this as more such
# files turn up in future corpus rollouts.
TITLE_OVERRIDES = {
    "nitya-shloka": "नित्यश्लोकाः",
    "dhyanam": "ध्यानम्",
    "kanchi-kamakshi-churnika": "श्री-कामाक्षी चूर्णिका",
    # gita repo: mahatmyam.tex has no heading of its own (starts directly
    # with a \dnsub subheading).
    "mahatmyam": "गीता-माहात्म्यम्",
    # mahabharatam/parvas: each file's first heading is the real \part{...}
    # parva name, but every file also has many per-adhyaya \chapter{...}
    # headings after it, so the "exactly one heading" rule below doesn't
    # fire -- curate these explicitly instead of falling back to the
    # slugified filename (which would show ugly things like "01 Ādiparva").
    "01-ādiparva": "आदिपर्व",
    "02-sabhāparva": "सभापर्व",
    "03-araṇyaparva": "अरण्यपर्व",
    "04-virāṭaparva-orig": "विराटपर्व",
    "05-udyogaparva": "उद्यॊगपर्व",
    "06-bhīṣmaparva": "भीष्मपर्व",
    "07-droṇaparva": "द्रॊणपर्व",
    "08-karṇaparva": "कर्णपर्व",
    "09-śalyaparva": "शल्यपर्व",
    "10-sauptikaparva": "सौप्तिकपर्व",
    "11-strīparva": "स्त्रीपर्व",
    "12-śāntiparva": "शान्तिपर्व",
    "13-anuśāsanaparva": "अनुशासनपर्व",
    "14-āśvamedhikaparva": "आश्वमॆधिकपर्व",
    "15-mausalaparva": "मौसलपर्व",
    "16-āśramavāsikaparva": "आश्रमवासिकपर्व",
    "17-mahāprasthānikaparva": "महाप्रस्थानिकपर्व",
    "18-svargārohaṇaparva": "स्वर्गारॊहणपर्व",
}


def extract_title(blocks, meta, slug):
    """Reads the title -- never removes a heading block from blocks[], so
    every \\sect in the source stays visible on the page, including
    whichever one supplied the title. Priority: curated override -> the
    single heading if there's exactly one (the common, reliable case) ->
    wiki_title -> humanized slug."""
    if slug in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[slug], blocks
    headings = [b for b in blocks if b["type"] == "heading"]
    if len(headings) == 1:
        return headings[0]["text"], blocks
    if meta.get("wiki_title"):
        return meta["wiki_title"], blocks
    return slug.replace("-", " ").title(), blocks


def is_blank_verse(block):
    if block["type"] != "verse-4-plain":
        return False
    return all(not line["text"].strip() for line in block["lines"])


def drop_blank_verses(blocks):
    return [b for b in blocks if not is_blank_verse(b)]


def group_columns(blocks):
    out = []
    i = 0
    n = len(blocks)
    while i < n:
        b = blocks[i]
        if b["type"] == "columns-open":
            inner = []
            i += 1
            while i < n and blocks[i]["type"] != "columns-close":
                inner.append(blocks[i])
                i += 1
            if i >= n:
                raise ValueError("columns-open with no matching columns-close")
            out.append({"type": "columns", "n": b.get("n"), "source": b.get("source"), "blocks": inner})
            i += 1  # skip the columns-close
            continue
        if b["type"] == "columns-close":
            raise ValueError("columns-close with no matching columns-open")
        out.append(b)
        i += 1
    return out


def transform_blocks(ir):
    """Returns (title, blocks) -- blocks ready to render, title extracted."""
    blocks = list(ir["blocks"])
    meta = ir["meta"]
    blocks = drop_counter_adjust(blocks)
    title, blocks = extract_title(blocks, meta, ir["slug"])
    blocks = drop_blank_verses(blocks)
    blocks = group_columns(blocks)
    return title, blocks


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_line(line, verse_number_deva, is_last, citation):
    text = esc(line["text"])
    ending = line["ending"]
    if ending == "double-danda-numbered":
        punct = f"॥{esc(verse_number_deva)}॥" if verse_number_deva else "॥॥"
    else:
        punct = ENDING_GLYPH.get(ending, "")
    pada_cls = " pada-even" if line.get("pada") == "even" else ""
    style = ' style="position:relative;"' if is_last else ""
    cite = f'<span class="citation">{esc(citation)}</span>' if (is_last and citation) else ""
    return f'<div class="line{pada_cls}"{style}>{text}{punct}{cite}</div>'


# Verse types whose padas share ONE justification target width in shloka.sty
# (a single \@tempdima across all lines) -- CSS can reproduce true
# justification for these directly. The 4-line indented types use two
# independent target widths (odd/even padas) and are left as plain
# indentation; see stotras.css.
JUSTIFIABLE_VERSE_TYPES = {"verse-1", "verse-2", "verse-3", "verse-annotated-2"}


def render_verse(block):
    lines = block["lines"]
    citation = block.get("citation")
    n = len(lines)
    rendered = "".join(
        render_line(line, block.get("verse_number_deva"), i == n - 1, citation) for i, line in enumerate(lines)
    )
    vid = esc(block.get("verse_id", ""))
    cls = "verse-block"
    if block["type"] in JUSTIFIABLE_VERSE_TYPES:
        cls += " verse-justify"
    return f'<div class="verse-block-wrapper" id="{vid}"><div class="{cls}">{rendered}</div></div>'


def render_block(block):
    t = block["type"]
    if t == "heading":
        return f'<h2 class="stotra-heading">{esc(block["text"])}</h2>'
    if t == "subheading":
        return f'<h3 class="subheading">{esc(block["text"])}</h3>'
    if t == "uvacha":
        return f'<p class="uvacha">{esc(block["text"])}</p>'
    if t == "prose":
        inner = "<br>".join(esc(l) for l in block["lines"])
        return f'<p class="prose">{inner}</p>'
    if t == "pushpika":
        return f'<p class="pushpika">{esc(block["text"])}</p>'
    if t == "attribution":
        return f'<p class="attribution">{esc(block["text"])}</p>'
    if t == "decoration":
        glyph = "❀ ❀ ❀" if block["style"] == "closesection" else "❀"
        return f'<div class="decoration">{glyph}</div>'
    if t == "columns":
        ncols = block.get("n") or 2
        inner = "".join(render_block(b) for b in block["blocks"])
        return f'<div class="verse-columns" style="column-count:{ncols};">{inner}</div>'
    if t.startswith("verse-"):
        return render_verse(block)
    return ""  # counter-adjust and anything else: nothing (shouldn't occur post-transform)


# Default matches stotra-sangrahah, the first corpus this bridge supported;
# other source repos pass their own via --pdf-repo/--pdf-variants/--strip-prefix
# (their PDF directory names and content-source layout both differ -- e.g.
# namavali-manjari's namavalis-pdf/<category>/<file>.pdf, with no leading
# content-root prefix to strip since its .tex files sit at the repo root).
DEFAULT_PDF_VARIANTS = (
    ("A5 / print", "stotras-pdf"),
    ("Kindle", "stotras-kindle-pdf"),
    ("Kindle Scribe", "stotras-kindle-scribe-pdf"),
)
DEFAULT_PDF_REPO = "stotrasamhita/stotra-sangrahah"
DEFAULT_STRIP_PREFIX = "stotras/"


def render_pdf_links(source_file, pdf_repo=DEFAULT_PDF_REPO, pdf_variants=DEFAULT_PDF_VARIANTS, strip_prefix=DEFAULT_STRIP_PREFIX):
    """source_file is e.g. "stotras/hanuman/HanumanChalisa.tex" -- each PDF
    variant mirrors that same category/filename under its own top-level
    directory in the source repo, just with a .pdf extension."""
    if not pdf_variants:
        return ""
    pdf_base_url = f"https://raw.githubusercontent.com/{pdf_repo}/master"
    rel = source_file[len(strip_prefix):] if strip_prefix and source_file.startswith(strip_prefix) else source_file
    rel_pdf = rel.rsplit(".", 1)[0] + ".pdf"
    links = "".join(
        f'<a href="{pdf_base_url}/{dirname}/{esc(rel_pdf)}">{esc(label)}</a>' for label, dirname in pdf_variants
    )
    return f'<div class="pdf-links"><span class="pdf-links-label">PDF:</span>{links}</div>'


def render_body(blocks, stotra_type=None, source_file=None, pdf_repo=DEFAULT_PDF_REPO,
                 pdf_variants=DEFAULT_PDF_VARIANTS, strip_prefix=DEFAULT_STRIP_PREFIX):
    # hugo-book's default page template wraps .Content in <article
    # class="markdown book-article"> -- it has no class of its own we can
    # hook a stotra-specific selector to, so the verse content is wrapped in
    # its own .stotra-article div here. This is also what the script-switcher
    # (hugo/assets/js/script-switcher.js in the site repo) targets, and
    # deliberately does NOT include the PDF links below: those are plain
    # English labels ("A5 / print", "Kindle"), not Devanagari verse text, and
    # transliterating them would be wrong.
    article_parts = []
    if stotra_type:
        article_parts.append(f'<p class="stotra-meta">{esc(stotra_type)}</p>')
    article_parts.extend(render_block(b) for b in blocks)
    parts = [f'<div class="stotra-article">' + "\n".join(p for p in article_parts if p) + "</div>"]
    if source_file:
        parts.append(render_pdf_links(source_file, pdf_repo, pdf_variants, strip_prefix))
    # Single-newline-joined, no blank lines: keeps this one contiguous
    # CommonMark HTML block so goldmark passes it through verbatim, with no
    # markdown reinterpretation of Devanagari text (asterisks, underscores,
    # leading "-"/"#" etc. inside verse lines are not markdown here).
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Front matter (metadata only -- no blocks)
# ---------------------------------------------------------------------------

def build_front_matter(ir, title):
    meta = dict(ir["meta"])
    verse_count = sum(1 for b in ir["blocks"] if b["type"].startswith("verse-")) - sum(
        1 for b in ir["blocks"] if is_blank_verse(b)
    )

    front_matter = {
        "title": title,
        "slug": ir["slug"],
        "source_file": ir["source_file"],
        "verse_count": verse_count,
    }

    for key in TAXONOMY_META_KEYS:
        if key in meta:
            # "Shiva, Shakti" -> ["Shiva", "Shakti"]; always a list, even for one value.
            front_matter[key] = [v.strip() for v in meta.pop(key).split(",") if v.strip()]

    # meta's own "type" (e.g. "Ashtakam", "Shatanama Stotram" -- the stotra's
    # genre) would collide with Hugo's reserved "type" front-matter key.
    if "type" in meta:
        front_matter["stotra_type"] = meta.pop("type")

    front_matter.update(meta)  # remaining meta keys (language, source, vakta, shrota, wiki_title) as plain params

    if ir.get("columns_hint") is not None:
        front_matter["columns_hint"] = ir["columns_hint"]

    return front_matter


def assign_weights(front_matters):
    """front_matters: list of (category, front_matter dict), mutated in place
    with a weight assigned alphabetically-by-slug within each category."""
    by_category = {}
    for category, fm in front_matters:
        by_category.setdefault(category, []).append(fm)
    for fms in by_category.values():
        for i, fm in enumerate(sorted(fms, key=lambda f: f["slug"])):
            fm["weight"] = (i + 1) * 10


def write_md(out_path, front_matter, body_html):
    """Hugo natively supports JSON front matter: a file whose first
    character is '{' is parsed as a self-contained JSON object (brace-depth
    matched), with everything after the closing '}' treated as the page
    body. Used here instead of YAML/TOML to avoid a PyYAML dependency (this
    repo's other scripts are stdlib-only) and YAML's escaping pitfalls with
    Devanagari text."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = json.dumps(front_matter, ensure_ascii=False, indent=1)
    out_path.write_text(f"{fm_text}\n\n{body_html}\n", encoding="utf-8")


def iter_input_files(inputs):
    paths = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            paths.extend(sorted(p.rglob("*.json")))
        elif p.is_file():
            paths.append(p)
        else:
            raise FileNotFoundError(str(p))
    return paths


def parse_pdf_variants(spec):
    """Parses "Label=dirname,Label2=dirname2" into the PDF_VARIANTS tuple
    shape; an empty string means no PDF links at all (e.g. a repo with only
    one combined book PDF, not per-file PDFs)."""
    if not spec:
        return ()
    pairs = []
    for item in spec.split(","):
        label, _, dirname = item.partition("=")
        if not dirname:
            raise ValueError(f"--pdf-variants entry {item!r} is not Label=dirname")
        pairs.append((label.strip(), dirname.strip()))
    return tuple(pairs)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert IR JSON to Hugo content (JSON front matter + raw HTML body).")
    ap.add_argument("input", nargs="*", default=["_build/ir"], help="IR JSON files or directories (default: _build/ir)")
    ap.add_argument("--out", default="_build/hugo-content", help="Output directory root (default: _build/hugo-content)")
    ap.add_argument("--pdf-repo", default=DEFAULT_PDF_REPO, help="owner/repo raw.githubusercontent.com PDFs are served from")
    ap.add_argument("--pdf-variants", default=None,
                    help='"Label=dirname,Label2=dirname2" (default: stotra-sangrahah\'s 3 variants); pass "" for none')
    ap.add_argument("--strip-prefix", default=DEFAULT_STRIP_PREFIX,
                    help="leading path segment to drop from source_file before appending .pdf (default: 'stotras/')")
    args = ap.parse_args(argv)

    pdf_variants = DEFAULT_PDF_VARIANTS if args.pdf_variants is None else parse_pdf_variants(args.pdf_variants)

    paths = iter_input_files(args.input)
    if not paths:
        print("No IR JSON files found.", file=sys.stderr)
        return 1

    out_root = Path(args.out)
    entries = []  # (category, front_matter, body_html, out_path)
    for path in paths:
        ir = json.loads(path.read_text(encoding="utf-8"))
        title, blocks = transform_blocks(ir)
        fm = build_front_matter(ir, title)
        body = render_body(blocks, fm.get("stotra_type"), ir["source_file"], args.pdf_repo, pdf_variants, args.strip_prefix)
        out_path = out_root / ir["category"] / f"{ir['slug']}.md"
        entries.append((ir["category"], fm, body, out_path))

    assign_weights([(cat, fm) for cat, fm, _, _ in entries])

    for _, fm, body, out_path in entries:
        write_md(out_path, fm, body)

    print(f"OK: wrote {len(entries)} Hugo content file(s) to {out_root}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
