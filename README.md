# स्तोत्रसङ्ग्रहः (Stotra Sangrahah)

A collection of Sanskrit *stotras* — hymns of praise — typeset in Devanāgarī with LaTeX, compiled into a single book and also made available as smaller, themed booklets and individual PDFs.

This repository is the LaTeX source behind [stotrasamhita.github.io](https://stotrasamhita.github.io/) and the [StotraSamhita](https://github.com/StotraSamhita) project.

## What's here

The texts are organised at three levels:

- **The full book** — `shloka.tex` and its variants (below), which pull together essentially every stotra in the repository into one volume, `स्तोत्रसङ्ग्रहः`.
- **Themed compilations** — `compilations/`, smaller standalone booklets built around a festival, a practice, or a purpose (Navarātri, daily recitation, a children's primer, and so on).
- **Individual stotras** — `stotras/`, the underlying `.tex` source for each hymn, one file per stotra, organised by deity. These are the building blocks that both the full book and the compilations `\input{}`. Pre-built single-stotra PDFs (handy for sharing or printing just one hymn) live alongside in `stotras-pdf/`, `stotras-kindle-pdf/`, and `stotras-kindle-scribe-pdf/`, mirroring the same deity-wise folder structure.

Most stotra texts were originally sourced from [sanskritdocuments.org](http://sanskritdocuments.org/) and [prapatti.com](http://prapatti.com/), then corrected and typeset over several editions.

## The full book: format variants

`shloka.tex` is the master document (it `\input`s `frontmatter.tex`, the prefaces, and `stotras.tex`, which in turn pulls in every stotra under `stotras/`). It is built in several page-size variants, one `.tex`/`.pdf` pair each, since a layout that works on a phone screen doesn't work on a printed page:

| Source | Output | Trim size | Notes |
|---|---|---|---|
| `shloka.tex` | `shloka.pdf` | 148×210 mm (A5-ish) | Default digital edition |
| `shloka-print.tex` | `shloka-print.pdf` | 148×210 mm | Same size, with wider gutter margins for physical binding |
| `shloka-6x9.tex` | `shloka-6x9.pdf` | 6×9 in | US trade paperback trim size |
| `shloka-kindle.tex` | `shloka-kindle.pdf` | 144×192 mm | Sized for Kindle paperback print-on-demand |
| `shloka-kindle-scribe.tex` | `shloka-kindle-scribe.pdf` | 192×254 mm, 2 columns | Larger page for the Kindle Scribe's screen |

Each variant sets a couple of `etoolbox` booleans (`kindle`, `print`) and a page geometry, then defers everything else — headers, fonts, section styling — to the shared `preamble.tex`. The various `shloka-*coverpage*.pdf`/`.svg` files and `ShriRama.jpg` are cover art for the print/Kindle editions.

## Thematic compilations

`compilations/` holds smaller booklets, each built around a specific occasion or need rather than trying to be exhaustive. See [`compilations/README.md`](compilations/README.md) for what each one contains. Most follow the same per-variant pattern as the main book (a base edition plus `-print`, `-kindle`, `-kindle-scribe` siblings where relevant), and each folder is close to self-contained — it carries its own `preamble.tex`, `frontmatter.tex`, and a local copy of `shloka.sty`/`autocols.sty` rather than referencing the root or `latex-styles/` copies, so folders can be built independently and have occasionally drifted slightly from the root versions.

## Shared build assets

- **`latex-styles/`** — the canonical copies of the shared style packages (`shloka.sty`, `shloka-multilang.sty`, `stotrasamhita.sty`, `NerurA5.sty`) and a Grantha/Tamil reference table. See [`latex-styles/README.md`](latex-styles/README.md). Note that the root document and the `compilations/` booklets each keep their own local copy of `shloka.sty`/`autocols.sty` for build convenience, rather than pointing here directly.
- **`fonts/`** — the non-Devanagari and Latin fonts needed for multi-script typesetting (Tamil, Telugu, Kannada, Malayalam, Grantha, IAST). See [`fonts/README.md`](fonts/README.md).
- **`autocols.sty`** (root) — a small adaptive multi-column environment: single column by default, switching to multiple columns only when `\maxColumns` is raised.

## Building

The book is typeset with **XeLaTeX** (see the `% !TeX program = XeLaTeX` line at the top of every root `.tex` file), using `fontspec` for OpenType/Devanagari font handling. You will need:

- A TeX distribution with XeLaTeX (TeX Live or MiKTeX).
- The **Sanskrit 2003** font (the primary Devanagari face used throughout) installed system-wide, plus the scripts referenced by the multi-language styles (Tamil, Telugu, Kannada, Malayalam, Grantha — see `fonts/`).
- Standard LaTeX packages: `fontspec`, `xunicode`, `xltxtra`, `polyglossia`/Devanagari script support, `fancyhdr`, `titlesec`, `multicol`, `hyperref`, `pdfpages`, `wallpaper`.

To build a given edition, run XeLaTeX (ideally via `latexmk`) on the corresponding `.tex` file, e.g.:

```sh
latexmk -xelatex shloka.tex          # default edition -> shloka.pdf
latexmk -xelatex shloka-6x9.tex      # 6x9in print edition
latexmk -xelatex shloka-kindle.tex   # Kindle paperback edition
```

`compilations/rebuildPDFs.bat` shows the same pattern applied to a couple of the thematic booklets (`stotramanjari`, `nityaparayanam`) — a batch script that `cd`s into each folder and reruns `latexmk -xelatex` on every `.tex` target there. It's Windows-specific but the underlying commands translate directly to any platform with `latexmk` installed.

`fix_incorrect_makaara_endings.py` is a small text-cleanup script that scans `.tex` files for `\fourlineindentedshloka` blocks and corrects a line-final अनुस्वार/म् (*makāra*) sandhi mistake — replacing a stray `म्` with `ं` when the following line doesn't start with a vowel. It's a one-off correction tool, not part of the regular build.

## History and acknowledgements

The prefaces to all three editions (`preface.tex`, `preface-1e.tex`, `preface-2e.tex`) open with the same invocation to the guru-paramparā — *sadāśiva-samārambhāṃ śaṅkarācārya-madhyamām / asmad-ācārya-paryantāṃ vande guru-paramparām* — and are signed by the author, Karthik Raman.

The first edition (May 2008) describes the book's origin: it was primarily inspired by two things — the author's *thāthā's* (grandfather's) own handwritten collection of ślokas, made for his grandchildren, and the *mantrapushpam*, a compilation of Vedic mantras and stotras published by the Ramakrishna Mutt. The stated aim was simple: to gather stotras otherwise scattered across many separate books into one portable volume, entirely in Devanāgarī — the author notes having often had access to stotras only in Tamil script, and finding Devanāgarī "more conducive to correct pronunciation" — and simple enough that children could learn from it, singling out *Nāma Rāmāyaṇam* as one every child should be taught. The preface points to M. S. Subbulakshmi's renditions of many of these stotras as a model for both *bhakti* and correct pronunciation, while stressing that one's daily *nityakarma* — especially *sandhyāvandanam* — always takes precedence, quoting *vipro vṛkṣas tasya mūlaṃ ca sandhyā...* ("a brāhmaṇa is a tree, and sandhyā its root — protect the root, or neither branch nor leaf survives"). It closes by dedicating the book to Śrī Kṛṣṇa with the Gītā's own verse on offering all one's acts to him (*yat karoṣi yad aśnāsi...*, Bhagavad Gītā 9.27).

That first-edition preface also thanks: the [Sanskrit Documents website](http://sanskritdocuments.org/), source for almost all the texts in the book; the author's friend **Prasād**, "instrumental (and almost wholly responsible) for the improved formatting," whose XeLaTeX macros made the alignments possible; the **ITranslator** software and the release of **MiKTeX 2.7**, which prompted the move to XeLaTeX; the author's parents, his guru **Shri S. Ananthakrishnan**, and his *māmā*; **Sāketh**, thanked as inspirational; the author's mother, for encouragement and for proofreading (particularly the *Śyāmalā daṇḍakam*); and his wife, for her support throughout.

The second edition (February 2011) added several large stotras — *Saundarya Laharī*, *Saṅkṣepa Rāmāyaṇam*, and *Śiva Sahasranāmam* — splitting the book into two parts, with the longer stotras in the second. It thanks the author's father-in-law, **Shri N. Venugopālan**, for sending the text of some rare stotras; his wife, **Mādhuryā**, for meticulously proofreading *Saundarya Laharī*; and his mother, for suggesting the *Durgā Pañcaratnam* composed by the Mahāperiyavā (the Kāñcī Śaṅkarācārya).

The (revised) third edition preface is shorter, noting the addition of more stotras — *Kāmākṣī Suprabhātam*, *Dakṣiṇāmūrti Aṣṭakam*, *Santāna-gopāla Stotram*, *Dāmodarāṣṭakam*, *Āpaduddhāraṇa Dvādaśa-mukha Hanumān Stotram*, *Ranganātha Gadyam*, and enough *śatanāma* (108-name) stotras that they were moved into a section of their own — and thanks **Sāketh** again, this time by name for proofreading the *Gakārādi Gaṇapati Sahasranāma Stotram* and for encoding many of the *aṣṭottara-śatanāma* stotras.

Typesetting relies heavily on XeLaTeX and the Sanskrit 2003 font, with LaTeX macros originally developed by H. L. Prasād, and early-edition encoding done with Itranslator 2003 and the Mudgala Sanskrit input method.

## Usage

The compiled book is offered for personal use and study. Please see the colophon in `frontmatter.tex` for the project's stated terms ("For Personal Use Only — Not For Commercial Printing/Distribution").

---

*The README.md files on this repo were generated and beautified with Claude.*
