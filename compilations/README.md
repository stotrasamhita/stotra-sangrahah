# Compilations

Themed booklets, each built around a specific occasion, practice, or purpose rather than trying to cover everything — a lighter alternative to the full `स्तोत्रसङ्ग्रहः` book for a particular need. Every folder is a near-self-contained LaTeX project: it carries its own `preamble.tex`, `frontmatter.tex`, and local copies of `shloka.sty`/`autocols.sty`, and `\input{}`s stotra sources from `../../stotras/` (the shared per-stotra source tree) as well as, in some cases, its own local `stotras/` subfolder of texts unique to that booklet.

| Folder | What it is |
|---|---|
| [`adhyatma-ramayana-stotras/`](adhyatma-ramayana-stotras/) | Stotras drawn from the *Adhyātma Rāmāyaṇa*, the spiritual/philosophical retelling of the Rāmāyaṇa. |
| [`bala-patha/`](bala-patha/) | *Bāla pāṭha* — a children's primer: simple stotras and a *jyautiṣa* (basic astrology/almanac) primer meant to be easy for young learners to pick up. |
| [`devi-stotrANi/`](devi-stotrANi/) | *Devī stotrāṇi* — hymns to the Divine Mother (Devī). |
| [`krittika-somavara-parayanam/`](krittika-somavara-parayanam/) | *Kṛttikā Somavāra pārāyaṇam* — Shiva stotras for recitation on Mondays that fall in the Kṛttikā (Kārtika) lunar month, a traditional Shiva-worship observance. |
| [`mantrastotrakadambam/`](mantrastotrakadambam/) | *Mantra-stotra-kadambam* — a "bouquet" combining Vedic mantras, stotras, and selections from the Bhagavad Gītā in one booklet. |
| [`navarAtra-stotrANi/`](navarAtra-stotrANi/) | *Navarātra stotrāṇi* — stotras for Navarātri, the nine-nights festival of the Goddess, together with the *Amṛtasiddhi* text. |
| [`nityaparayanam/`](nityaparayanam/) | *Nitya pārāyaṇam* — a daily-recitation set: a shloka edition, a Vedic-mantra edition, and a compact *Mantrapuṣpam*. |
| [`satsantAnaprApti/`](satsantAnaprApti/) | *Sat-santāna-prāpti* — stotras traditionally recited for the wellbeing of children and progeny (e.g. *Garbharakṣāmbikā Stotram*, *Subrahmaṇya Bhujangam*, *Saundarya Laharī*). |
| [`stotramanjari/`](stotramanjari/) | *Stotra-mañjarī* — a "cluster of blossoms": mainly *aṣṭottara-śatanāma* (108-name) stotras for various deities and grahas (planets), split across several parts, plus a handful of longer individual stotras. |

## Format variants

Like the root book, several of these booklets are built in more than one page-size variant from the same content — a base `<name>.tex`/`.pdf`, plus `<name>-print.tex`, `<name>-kindle.tex`, and/or `<name>-kindle-scribe.tex` siblings where a print or e-reader edition has been prepared. Not every booklet has every variant; check each folder's file listing.

## Building

`rebuildPDFs.bat` at this level is a Windows batch script that rebuilds a subset of these booklets (currently `stotramanjari`'s several parts and `nityaparayanam`'s editions) by `cd`-ing into each folder and running `latexmk -xelatex <target>` there, logging to `rebuild.log`. It's a convenience script covering the booklets that are rebuilt most often, not an exhaustive build-everything target — to build any individual booklet (including ones not listed in the script), `cd` into its folder and run `latexmk -xelatex <name>.tex` (or the XeLaTeX toolchain described in the root README) directly.

`shloka-book-v3.pdf` at this level is a previously compiled snapshot of the full book, kept here from an earlier stage of the project; the current full-book builds live at the repository root (`shloka*.pdf`).

---

*The README.md files on this repo were generated and beautified with Claude.*
