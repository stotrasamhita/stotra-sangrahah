# latex-styles

Shared LaTeX packages and reference material used across the stotra books. (Note: the root document and each `compilations/` booklet keep their own local copies of `shloka.sty`/`autocols.sty` alongside their `.tex` sources rather than pulling from here directly — this folder holds the canonical/shared versions, useful as a reference or a starting point for new booklets.)

- **`shloka.sty`** — the core stotra-typesetting package. Defines the verse-layout macros (`\twolineshloka`, `\onelineshloka`, `\fourlineindentedshloka`, and related annotated/starred variants) used to lay out shlokas with correctly aligned verse-end daṇḍas (।/॥) and automatic Devanāgarī verse numbering (`\nextShloka`, rendered via `\devanumber`/`\devadigit`). It also sets Devanāgarī fonts for the table of contents (`अनुक्रमणिका`) and part/chapter names, and loads `fontspec`, `pdfpages`, `xunicode`, `xltxtra`, `titlesec`, and `multicol` as its base dependencies.
- **`shloka-multilang.sty`** — a multi-script extension of the same idea: it declares package options (`dng`, `grantha`, `tamil`, `tamilgrantha`, `telugu`, `kannada`, `malayalam`, `hindi`, `iast`) to toggle rendering a stotra in Devanāgarī, Grantha, Tamil, Telugu, Kannada, Malayalam, Hindi, or IAST transliteration, plus table-column helpers (`L`/`C`/`R`) for laying out parallel-script tables.
- **`stotrasamhita.sty`** — a page/document style (17pt base size, custom margins, a purple-on-cream colour scheme, and per-script font commands for Devanagari/Tamil/Telugu/Kannada/Grantha/Malayalam) used for StotraSamhita-branded documents.
- **`NerurA5.sty`** — the same style adapted for A5-format documents associated with Nerur Shankara Matham; nearly identical to `stotrasamhita.sty` but with its own colour palette and page geometry.
- **`granthamizh-table-only.pdf`** — a reference table of the Grantha/Tamil script mapping, not a style file; useful when checking or extending the multi-script font handling above.

---

*The README.md files on this repo were generated and beautified with Claude.*
