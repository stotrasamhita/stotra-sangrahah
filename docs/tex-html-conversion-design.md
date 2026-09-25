# TeX → HTML conversion design

This document is the reference for turning `stotras/**/*.tex` into structured
content for the future Hugo site. It exists so that whoever writes the
Phase 2 converter doesn't have to re-derive the macro semantics or re-audit
the corpus for anomalies — that work is captured here.

Everything below was verified by direct reads of `shloka.sty`,
`preamble.tex`, `autocols.sty`, and a corpus-wide grep across all
`stotras/**/*.tex` files (268 files at the time of writing).

## 1. Macro inventory

`shloka.sty` (repo root) is the file that actually governs `stotras/`,
loaded via `\usepackage{shloka}` in `preamble.tex`. (`latex-styles/shloka.sty`
is an older, near-duplicate copy; `latex-styles/stotrasamhita.sty` and
`latex-styles/NerurA5.sty` are orphaned — nothing references them.)

### Headings

- **`\sect{title}`** / **`\chapt{title}`** — one arg. Wraps the title in
  danda marks `॥title॥`, fake-bold stretched Devanagari (Sanskrit 2003).
  `\section`/`\chapter` are redefined in `preamble.tex` so that **every
  call resets the verse counter to 0** as a side effect
  (`\resetShloka`). Section numbering itself is suppressed
  (`secnumdepth = -1`) — it's a titling/bookmark mechanism, not a numbered
  outline level. 6 files use `\chapt` instead of `\sect`
  (`stotras/purti/KshamaPrarthana.tex`, `stotras/purti/VandeMataram.tex`,
  `stotras/other/{KalidoshanivaranaStotram,YamabhayanivaranaStotram,
  AvaidhavyaPrarthanaStotram,KartaviryarjunaStotram}.tex`); treat as a
  synonym, not a different construct. `VandeMataram.tex` specifically is a
  patriotic song, not a traditional stotra — route it through the generic
  prose fallback (§2) rather than forcing shloka-shaped IR onto it.

### Verse macros

All auto-increment a shared `shlokacount` counter, rendered as a
**Devanagari numeral** (a hand-rolled recursive digit converter — not
Arabic numerals), and are dispatched via `\@ifstar` to starred/unstarred
variants.

| Macro | Args | Layout | Numbering |
|---|---|---|---|
| `\onelineshloka` | 1 | `\centerline` | ends `॥<num>॥`; **starred variant ends in a single danda `।` instead and drops both the danda-pair and the number** — the one macro where starring changes more than just number-suppression |
| `\twolineshloka` | 2 | both lines padded to the wider one's width, centered as a unit | line 1 ends `।`, line 2 ends `॥<num>॥` (starred: line 2 ends `॥` only, no number) |
| `\threelineshloka` | 3 | same width-matching, 3 lines | **real, common macro — 76 uses across 51 files, not a rarity** |
| `\fourlineindentedshloka` | 4 | odd lines (1,3) width-matched to each other, left-flush; even lines (2,4) width-matched to each other, indented by `\shlokaspaceskip` | line 2 ends `।`, line 4 ends `॥<num>॥` (starred: line 4 ends `॥` only) |
| `\fourlineshloka` | 4 | same odd/even pada indentation as `\fourlineindentedshloka` (confirmed by reading the full macro definition — it applies `\hskip\shlokaspaceskip` to padas 2 and 4 identically) | **no danda marks and no numbering at all** — the only real difference from `\fourlineindentedshloka` is that it's unpunctuated/unnumbered, not that it's unindented. Used exactly twice, both in `stotras/vishnu/RanganathaGadyam.tex` |
| `\annotwolineshloka` | 3 | `\twolineshloka` + a trailing citation fragment via `\rlap{}` | as `\twolineshloka` |
| `\annofourlineindentedshloka` | 5 | `\fourlineindentedshloka` + trailing citation via `\rlap{}` | as `\fourlineindentedshloka` |
| `\THREElineshloka` | 3 | defined in `shloka.sty` | **dead code — never invoked anywhere in `stotras/`** |

**`\sixlineindentedshloka` does not exist anywhere in the repo** (grepped
both `.sty` and `.tex`, repo-wide). No five/six/seven/eight-line variants
exist beyond the four above.

**Starred variants**, in general: byte-identical box/indent/spacing logic
to the unstarred form; the only difference is that `\nextShloka` (the
counter step) is not called, so no number is printed. The closing double
danda is otherwise retained — `\onelineshloka*` is the sole exception,
which drops both the danda-pair and the number (see table above). Starred
forms are used throughout for repeated/generic closing verses (śānti-pāṭha,
phalaśruti boilerplate) that shouldn't get their own number in a stotra's
sequence.

### Sub-headings and speaker attribution

- **`\dnsub{label}`** — one arg. **Not a prose wrapper** (an incorrect
  initial assumption, corrected here). It's a centered, large, bold
  sub-heading *label* — e.g. `\dnsub{ध्यानम्}`, `\dnsub{फलश्रुतिः}`,
  `\dnsub{न्यासः}`, `\dnsub{कवचम्}`, `\dnsub{काण्डः}`-divisions — wrapped in
  danda marks, no numbering. Used 160 times across 51 files. The prose
  that follows a `\dnsub` (e.g. nyāsa mantra text) is **not** wrapped in
  any macro — it's plain paragraph text using literal `\\` for manual line
  breaks.
- **`\uvacha{speaker phrase}`** — one arg, 176 occurrences across 85
  files. Centered, bold Devanagari, normal size (smaller than `\dnsub`),
  **no danda wrapping** — the caller supplies the whole phrase including
  "उवाच"/"उचुः" (e.g. `\uvacha{गर्ग ऋषिरुवाच}`). Always immediately precedes
  the verse block giving that speaker's words; fires multiple times per
  file in dialogue poems as the speaker changes. No numbering. See §4 for
  the plan to make this a filterable taxonomy rather than buried prose.

### Counter control

- **`\resetShloka`** — resets `shlokacount` to 0. Called implicitly by
  every `\sect`/`\chapt`, and explicitly mid-file in 12 files (e.g. to
  restart numbering after a `\dnsub{फलश्रुतिः}` section, or after the
  `\dnsub{चौपाई}` transition in `HanumanChalisa.tex`).
- **`\addtocounter{shlokacount}{N}`** — 43 files, 45 occurrences. Adds `N`
  to the running counter without printing a number. Two real usage
  patterns, both must be supported:
  - **Start-of-file offset**, immediately after `\sect{}`, for a stotra
    that's an excerpt from a larger work — e.g.
    `stotras/vishnu/BrahmapaaraStotram.tex:8` (`{53}` — this is Viṣṇu
    Purāṇa 1.15, starting at verse 54), `stotras/vishnu/
    VishnuVijayaStotram.tex:6` (`{88}`), `stotras/shiva/RudraStotram.tex:15`
    (`{54}`), `stotras/adhyatma-ramayana-stotras/
    AhalyakrtaRamaStotram.tex:10` (`{42}`), `stotras/adhyatma-ramayana-
    stotras/HanumatSambhashanam.tex:7` (`{14}`).
  - **Mid-file skip, sometimes composed with `\resetShloka`** — e.g.
    `stotras/big/ShivaSahasranamaStotram-VishnuKrtam.tex` uses
    `\addtocounter{shlokacount}{1}` twice mid-file (lines 100, 116) to
    skip a number already embedded in the verse text itself, and later
    (lines 696-697) a bare `\resetShloka` immediately followed by
    `\addtocounter{shlokacount}{159}` to restart numbering at a new offset
    partway through the file.

  **Implication for the parser**: the counter model cannot be "step by 1,
  reset to 0" only. It's a single running value mutated by three
  operations recognized anywhere in the block stream — reset-to-0,
  add-N, and step-by-1 (implicit on every non-starred verse macro) —
  applied in document order, so composite sequences (reset immediately
  followed by an offset) resolve correctly.

### Closing conventions

- **Pushpika** (the closing colophon, "thus concludes...") is **not a
  macro**. It's always plain text matching `॥इति...सम्पूर्णम्॥` (or
  `समाप्तम्`), but rendered three inconsistent ways across the corpus: bare
  (152 files), wrapped in bare `{}` (72 files), wrapped in `\centerline{}`
  (2 files: `ShrinivasaGadyam.tex`, `RanganathaGadyam.tex`). No semantic
  difference — the wrapper is accidental inconsistency, not signal.
  **Detect by content regex, not by which wrapper (if any) was used** —
  this makes the 3-way inconsistency irrelevant to the parser. At least
  one file (`RamarakshaStotram.tex`) has its pushpika commented out
  entirely — "no pushpika block" is a legitimate outcome, not a parse
  error.
- **`\closesection`** (triple 🌸 `\EightFlowerPetal` ornament) /
  **`\closesub`** (single 🌸) — optional decorative dividers, used in only
  21/268 files, sometimes wrapped in `\hyperref[...]{\closesection}` as a
  "back to top" link. Purely decorative; no layout math involved.

### Columns

- **`AutoCols` environment** (from `autocols.sty`, a thin conditional
  wrapper around `multicols`, controlled by a `\maxColumns` value that
  differs per book build) — used directly in `stotras/` in 5 files
  (`DakshinamurtiStotram.tex`, `ShivashivaaStuti.tex`,
  `UmamaheshwaraStotram.tex`, `VenkateshaPrapatti.tex`,
  `VishnuBhujangaprayataStotram.tex`).
- **Raw `\begin{multicols}{2}`** — used directly (not via `AutoCols`) in 4
  *different* files (`NamaRamayanam.tex`, `HanumanChalisa.tex`,
  `BhajaGovindam.tex`, `BhajaGovindam-laghu.tex`). Both forms map to the
  same "columns" concept in the parser and CSS.

### Spacing constants (→ CSS custom properties)

```latex
\shlokaspaceskip = 2.4em   % indent applied to even padas in 4-line shloka
                            % (halved to 1.2em in some 2-column builds)
\shlokamidskip   = -1.6pt plus 0.1em   % gap between lines within one verse
\shlokatopskip   = 0.2em plus 0.5em minus 0.2em  % gap before a verse block
```

## 2. Parser strategy

The corpus is a **closed vocabulary of ~15 macros/environments** — not a
general LaTeX subset. A full LaTeX grammar (e.g. a generic parser package)
is overkill and would treat brace-nesting inside verse arguments
(`\hspace{}`, `\rlap{}`, `\mbox{}`) as generically parseable structure when
we just need it treated as "more characters inside this argument."

Proposed pipeline, per file:

1. **Comment stripping**, respecting `\%` (escaped percent). The
   `% --meta--` / `% --end-meta--` block (present in 150/268 files as of
   this writing) is extracted *before* generic comment stripping, since
   it's the one place comments are semantically meaningful — it becomes
   the Hugo front matter (`deity`, `composer`, `chandas`, `type`,
   `source`, `language`, `vakta`, `shrota`, `wiki_title`).
2. **Local-macro pre-scan** — regex-scan for `\newcommand{\foo}...` near
   the top of the file (handles `NamaRamayanam.tex`'s file-local `\jaya`
   refrain macro generically, not as a hardcoded special case) and
   register as inline text-expansion aliases before block parsing.
3. **Brace-balancing scan** — a small stateful scanner that reads a
   command name (`\[A-Za-z]+\*?`), then for each expected argument reads
   a `{`-delimited span while tracking nesting depth (so it does not stop
   at the first `}` inside a nested `\hspace{}`/`\rlap{}`). Argument count
   per command comes from a static arity table (`onelineshloka: 1`,
   `twolineshloka: 2`, `fourlineindentedshloka: 4`,
   `annofourlineindentedshloka: 5`, `dnsub: 1`, `uvacha: 1`, `sect: 1`,
   `chapt: 1`, …). Star detection: a literal `*` immediately after the
   command name, before the first `{`.
4. **Structural tokens**, recognized but not brace-parsed:
   `\begin{center}`/`\end{center}`, `\begin{large}`/`\end{large}`,
   `\begin{multicols}{N}`/`\end{multicols}`,
   `\begin{AutoCols}`/`\end{AutoCols}`, `\resetShloka`,
   `\addtocounter{shlokacount}{N}`, `\closesection`, `\closesub` — these
   become open/close/counter events in the block stream.
5. **Dropped, layout-only tokens**: `\clearpage`, `\newpage`, `\vspace`,
   `\setlength`, `\setmainfont`, `\mbox{}`, `\label`,
   `\hyperref[...]{X}` (unwrapped to just `X` — supersede the 4 ad hoc
   "back to top" anchors with one uniform Hugo template feature instead
   of reconstructing each one). Any `\setlength`/`\setmainfont` found
   **outside** a `\begingroup`/`\endgroup` scope is additionally flagged
   as a lint warning (not a hard failure) for human review before a
   corpus-wide run — this is exactly the class of bug already found and
   fixed in `MahishasuramardiniStotram.tex`.
6. **Generic prose fallback**: any unrecognized content — consecutive
   non-macro lines, or the plain text after a `\dnsub` — is accumulated
   into a `prose` block until the next recognized macro/environment
   boundary, with literal `\\` converted to an explicit line-break marker.
   This one fallback path is what makes `NamaRamayanam.tex`,
   `GitaGovindam.tex`'s Ashtapadi refrains, and ordinary nyāsa prose "just
   work" without per-file special casing.
7. **Pushpika detection**: after block parsing, scan trailing prose/plain
   text for `॥\s*इति.*?(सम्पूर्णम्|समाप्तम्)\s*॥`, regardless of wrapper —
   see §1.
8. **Hard failure mode**: unbalanced braces, or an `\end{...}` with no
   matching `\begin{...}` on the scope stack, is a **loud parse error**
   naming the file and location — not a silent best-effort partial parse.
   This is what `stotras/other/RogaNivaranaShloka.tex` would have hit
   before it was fixed; the class of bug should always fail the build,
   not degrade.

**Counter model**: a single running value, mutated by reset-to-0
(`\sect`/`\chapt`/bare `\resetShloka`), add-N
(`\addtocounter{shlokacount}{N}`), and step-by-1 (implicit on every
non-starred verse macro), applied in document order — see §1's counter
control section for the composite-sequence example this must handle
correctly.

## 3. Intermediate representation

One JSON document per source `.tex` file — the single artifact consumed
by both the Hugo content generator and the (separately planned) Vāgdhenu
TTS shard builder, so the TeX-parsing logic is written once.

```json
{
  "source_file": "stotras/hanuman/HanumanChalisa.tex",
  "slug": "hanuman-chalisa",
  "category": "hanuman",
  "meta": {
    "deity": "Hanuman",
    "composer": "Tulasidas",
    "language": "Avadhi",
    "wiki_title": "Hanuman Chalisa"
  },
  "columns_hint": 2,
  "blocks": [
    { "type": "heading", "macro": "sect", "text": "हनुमान् चालीसा", "resets_counter": true },
    { "type": "columns-open", "n": 2, "source": "multicols" },
    {
      "type": "verse-4-indented",
      "starred": true,
      "verse_number": null,
      "verse_number_deva": null,
      "lines": [
        { "pada": "odd",  "text": "श्रीगुरु चरन सरोज रज" },
        { "pada": "even", "text": "निज मनु मुकुर सुधार" },
        { "pada": "odd",  "text": "बरनऊँ रघुवर विमल यश" },
        { "pada": "even", "text": "जो दायकु फल चार" }
      ],
      "verse_id": "hanuman-chalisa-b0002",
      "plain_text": "श्रीगुरु चरन सरोज रज निज मनु मुकुर सुधार बरनऊँ रघुवर विमल यश जो दायकु फल चार"
    },
    { "type": "subheading", "macro": "dnsub", "text": "चौपाई" },
    { "type": "counter-adjust", "op": "reset" },
    {
      "type": "verse-2",
      "starred": false,
      "verse_number": 1,
      "verse_number_deva": "१",
      "lines": [
        { "pada": null, "text": "जय हनुमान ज्ञान गुण सागर", "ending": "danda" },
        { "pada": null, "text": "जय कपीश तिहुँ लोक उजागर", "ending": "double-danda-numbered" }
      ],
      "verse_id": "hanuman-chalisa-b0004",
      "plain_text": "जय हनुमान ज्ञान गुण सागर जय कपीश तिहुँ लोक उजागर"
    },
    { "type": "columns-close" },
    { "type": "uvacha", "text": "गर्ग ऋषिरुवाच" },
    { "type": "decoration", "style": "closesection" },
    { "type": "pushpika", "text": "॥इति श्रीबुधकौशिकविरचितं श्रीरामरक्षास्तोत्रं सम्पूर्णम्॥" }
  ]
}
```

Notes:

- `type` is a closed enum: `heading | subheading | uvacha | verse-1 |
  verse-2 | verse-3 | verse-4-indented | verse-4-plain |
  verse-annotated-2 | verse-annotated-4 | prose | columns-open |
  columns-close | counter-adjust | decoration | pushpika | attribution`.
  `starred` is a boolean modifier, not a separate type.
- `verse_number`/`verse_number_deva` are computed by the parser's own
  counter model (§2), mirroring `\devanumberrecurse`'s exact digit
  mapping (`DEVA_DIGITS = "०१२३४५६७८९"`) — baked into the data, not
  deferred to a CSS counter (see §5 for why).
- `verse_id` (`{slug}-b{block_index:04d}`) is the stable join key the
  Vāgdhenu TTS shard builder should use to align audio to verse text —
  produced once here, not independently re-derived by the TTS pipeline.
- `plain_text` is the danda/number-stripped, space-joined line
  concatenation — the unit TTS needs per utterance. HTML rendering uses
  `lines[]` directly (preserving pada breaks).
- `category` comes from the immediate parent directory
  (`stotras/<category>/File.tex`), deliberately not from `stotras.tex`'s
  ad hoc TOC groupings (which has at least one bug — a duplicate include
  of `KamakshiMahatmyam.tex` — orthogonal to this per-file conversion).

## 4. TODO: speaker attribution as a filterable tag

`\uvacha{गर्ग ऋषिरुवाच}`-style speaker lines and the wiki-derived
`vakta`/`shrota` metadata fields are conceptually the same thing — "who is
speaking in this passage." Tracked as a GitHub issue rather than designed
here: the idea is to model this as a first-class taxonomy on the Hugo site
(e.g. "every stotra where Krishna is the speaker") instead of leaving
`\uvacha` as decorative prose and `vakta`/`shrota` as separate front-matter
fields with no cross-linking.

## 5. CSS mapping

**LaTeX's box-width-matching trick needs no JS measurement pass — pure
CSS reproduces it exactly.** `\hbox to \@tempdima{\unhbox...}` exists only
to make the narrower of two lines share the same bounding box as the
wider one, so that centering the pair as a unit keeps them left-aligned to
each other. CSS `display: inline-block` already computes shrink-to-fit
width as the max of its children's intrinsic widths and left-aligns block
children within it — the same computation, done by the browser layout
engine.

```css
.verse-block-wrapper { text-align: center; margin-top: 0.4em; } /* \shlokatopskip */
.verse-block { display: inline-block; text-align: left; }        /* shrink-to-fit = max(line widths) */
.verse-block > .line { display: block; }
```

| Macro | CSS mechanism |
|---|---|
| `\onelineshloka` | single `.line`; ends with number span, or (starred) a single danda, no number. |
| `\twolineshloka` / `\threelineshloka` | 2 or 3 stacked `.line`s in one `.verse-block` — width-matching is automatic. |
| `\fourlineindentedshloka` | 4 stacked `.line`s; even lines (pada 2, 4) get `padding-left: var(--shloka-indent)`. Because the wrapper is one shrink-to-fit box over all four lines, the outer width naturally becomes `max(oddLineWidths, indent + evenLineWidths)` — matching (and simplifying) the vbox-of-max-width-hboxes in `shloka.sty`. |
| `\fourlineshloka` | same, minus the trailing numbered danda — no numbering markup. |
| `\annotwolineshloka` / `\annofourlineindentedshloka` | add a `.citation` span with `position: absolute; left: 100%; white-space: nowrap; font-size: smaller;` on a `position: relative` last line — replicates `\rlap{}`'s "doesn't affect box width, spills right" without JS. |
| `\shlokaspaceskip` | CSS custom property `--shloka-indent: 2.4em;` at `:root`; a narrow-viewport media query sets `1.2em`, mirroring the 2-column build's halving. |
| `\dnsub` | `.subheading { text-align: center; font-weight: 700; font-size: 1.25em; }` with `::before`/`::after` content `"॥ "` / `" ॥"`. |
| `\uvacha` | `.uvacha { text-align: center; font-weight: 700; }` — no danda wrap, normal size. |
| `\closesection` / `\closesub` | centered text content, 3 or 1 flower glyphs — no layout math. |
| `AutoCols` / raw `multicols` | `.verse-columns { column-count: 2; column-gap: 30pt; column-rule: 1pt solid; }` (matches `\columnsep`/`\columnseprule`) when column count > 1; otherwise normal block flow. |

**Devanagari verse numbers**: do not rely on CSS `counter()`/
`@counter-style`. The parser already computes both the integer and the
Devanagari string (§2, §3) — bake `verse_number_deva` directly into the
rendered text. Reasons: the TTS pipeline needs the integer as data, not
CSS-generated decoration; numbering must restart mid-document in ways
(`\resetShloka`/`\addtocounter` firing anywhere, independent of DOM
nesting) that don't map cleanly onto CSS's nested `counter-reset` scoping;
and it sidesteps inconsistent browser support for exotic counter-style
numeral systems.

## 6. Anomaly handling policy

A corpus-wide audit found that ~93% of files (≈247/268) use only the
macros in §1, cleanly. 13 categories of exceptions were found; five were
real bugs (fixed by the repo owner directly, see below), the rest are
intentional one-offs the parser handles generically rather than through
per-file special cases.

| # | Pattern | Decision |
|---|---|---|
| 1 | Corrupted/unclosed file (`stotras/other/RogaNivaranaShloka.tex`: two stotras concatenated, unmatched `\end{center}`, unscoped global font changes, unclosed trailing `\begin{center}`) | **Fixed in TeX** (repo owner, commit `f4dac73`). This class of bug should always be a hard parser failure (§2 step 8), never a silent partial parse. |
| 2 | Catcode hack for line-breaking a long compound word (`stotras/dhyanam/KanchiSwastiVachanam.tex`) | Out of scope — single-file, working, idiosyncratic. Parser strips the `\catcode` block as inert for this one file; rely on CSS `overflow-wrap: break-word` in the browser instead. One-time manual visual check, no generic rule needed. |
| 3 | File-local `\jaya` macro + plain `\hfill`-aligned text (`stotras/rama/NamaRamayanam.tex`) | Handled generically — local-macro pre-scan (§2 step 2) + prose fallback (§2 step 6), no file-specific code. |
| 4 | Unscoped `\setlength{\shlokaspaceskip}` leaking into subsequent files (`stotras/shakti/MahishasuramardiniStotram.tex`) | **Fixed in TeX** (repo owner). Also now a standing lint rule (§2 step 5) for any future recurrence. |
| 5 | Manual `\hspace{}` kerning hacks in verse text (`stotras/adhyatma-ramayana-stotras/DevaStuti.tex`) | Out of scope — `\hspace{}` is already dropped generically; one spot-check of the rendered page is sufficient. |
| 6 | Ashtapadi refrains as plain `\\`/`\smallskip`/`\bigskip` text (`stotras/krishna/GitaGovindam.tex`) | Handled generically — same prose fallback as #3. `\smallskip`/`\bigskip` in prose map to spacer utility classes. |
| 7 | `\textbf{}` used instead of `\dnsub` for a heading (`stotras/guru/KanchiKamakotiGuruParamparaStava.tex`) | **Fixed in TeX** (repo owner). |
| 8 | Stray mid-body `\clearpage` (`RogaNivaranaShloka.tex`, `stotras/big/SankshepaRamayanam.tex`) | Handled generically — `\clearpage`/`\newpage` are on the dropped-token list (§2 step 5). |
| 9 | Right-aligned ritual-offering attribution lines, `\nobreak\hfill{}---text` (`stotras/shiva/Karttikasomavararghyam.tex`, 8×) | One small, generic parser rule (an `attribution` block type, §3) — contained enough to be worth handling rather than deferring to manual conversion. |
| 10 | Dead commented-out `\closesub` (`ArdhanarishwaraStotram.tex`, `SubrahmanyaPancharatnam.tex`) | **Fixed in TeX** (repo owner). |
| 11 | `\chapt{}` instead of `\sect{}` (6 files) | Handled generically — synonym in the macro dispatch table (§1, §2). `VandeMataram.tex` routed through the prose fallback as a non-stotra `song`-type page. |
| 12 | Vestigial inert `\begingroup` with commented-out payload (`stotras/vishnu/BrahmapaaraStotram.tex`) | **Fixed in TeX** (repo owner) — the live `\addtocounter{shlokacount}{53}` line in the same file was correctly preserved. |
| 13 | Misc one-offs: pushpika wrapper variance, `\label`/`\hyperref` back-links, `minipage`/`large`/`center` envs, `\mbox{}`, `\vspace`, skips | Handled generically across the board — see §2 steps 5, 7 for the specific rules (content-based pushpika detection, dropped-token list, unwrapped `\hyperref`). No per-file code. |

## 7. Explicitly out of scope

This document is a design reference. It does not include a converter
implementation — that is a follow-on phase, to be planned separately once
this design is settled. The 118 stotra files still lacking a
`% --meta--` metadata header (see the MediaWiki backfill work) are also
untouched here.
