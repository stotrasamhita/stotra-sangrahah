# fonts

Font files bundled for the multi-script typesetting used by `latex-styles/shloka-multilang.sty`, `stotrasamhita.sty`, and `NerurA5.sty`. The primary Devanāgarī text throughout the books is set in **Sanskrit 2003**, which most `.tex` files reference by name via `fontspec` and expect to find installed system-wide; the fonts collected here are the rest of the scripts needed when a stotra (or its transliteration) is rendered in more than one script.

| File | Script / use |
|---|---|
| `sanskrit2003-5-spac-diaresis.ttf` | A bundled copy of the Sanskrit 2003 Devanāgarī font, for builds where it isn't already installed system-wide. |
| `NotoSerifGrantha-Regular-20191216-shri.ttf` | Grantha script (South Indian script historically used for Sanskrit). |
| `NotoSerifTamil-Regular.ttf`, `NotoSerifTamil-Bold.ttf` | Tamil script. |
| `NotoSerifMalayalam-Regular.ttf`, `NotoSerifMalayalam-Bold.ttf` | Malayalam script. |
| `Mandali.ttf` | Telugu script. |
| `Nudi Unicode 01 Regular.ttf`, `Nudi Unicode 01 Bold.ttf` | Kannada script. |
| `GenBasR.ttf`, `GenBasI.ttf` | Gentium Basic (Regular/Italic) — a Latin font used for IAST transliteration of Sanskrit into the Roman alphabet. |

To build any document that uses these (via the `dng`/`grantha`/`tamil`/`telugu`/`kannada`/`malayalam`/`iast` options of `shloka-multilang.sty`, or the per-script font commands in `stotrasamhita.sty`/`NerurA5.sty`), make sure this folder's fonts — plus Sanskrit 2003 itself — are installed and discoverable by XeLaTeX (e.g. via your OS font directory, or a local `TEXMFHOME`/font-path configuration pointing at this folder).
