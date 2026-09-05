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
    # mahabharatam's own shloka.sty (not stotra-sangrahah's): a 3-couplet
    # extension of fourlineindentedshloka's odd/even indentation pattern, no
    # starred form (\ifstar isn't used in its definition -- always numbered).
    "sixlineindentedshloka": 6,
}

NO_STAR_SUPPORT = {"annotwolineshloka", "annofourlineindentedshloka", "fourlineshloka", "sixlineindentedshloka"}
NEVER_NUMBERED = {"fourlineshloka"}
INDENTED_MACROS = {"fourlineindentedshloka", "fourlineshloka", "annofourlineindentedshloka", "sixlineindentedshloka"}

TYPE_NAME = {
    "onelineshloka": "verse-1",
    "twolineshloka": "verse-2",
    "threelineshloka": "verse-3",
    "fourlineindentedshloka": "verse-4-indented",
    "fourlineshloka": "verse-4-plain",
    "annotwolineshloka": "verse-annotated-2",
    "annofourlineindentedshloka": "verse-annotated-4",
    "sixlineindentedshloka": "verse-6-indented",
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
    "sixlineindentedshloka": (
        ["none", "danda", "none", "danda", "none", "double-danda-numbered"],
        None,
    ),
}

STRUCTURAL_BEGIN_END = {"center", "large", "Large", "minipage", "flushleft", "flushright", "enumerate", "itemize"}
COLUMN_ENVIRONMENTS = {"multicols", "AutoCols"}
TABLE_ENVIRONMENTS = {"tabular", "supertabular", "longtable"}

DROPPED_ZERO_ARG = {
    "clearpage", "newpage", "smallskip", "medskip", "bigskip", "nobreak",
    "hfill", "raggedright", "selectfont", "adjustShlokaSpaceSkip",
    "nopagebreak", "normalsize", "noindent", "centering",
    # font-size/family switches: no visible effect on the page (CSS already
    # sets one consistent font throughout .stotra-article).
    "bfseries", "sffamily", "scriptsize", "small", "large", "footnotesize", "LARGE",
    # FontAwesome clock icon (puja-vidhanam's practical-timing notes,
    # e.g. "\faClockO{} {\sffamily This must be offered thrice every day...}") --
    # decorative, dropped rather than reproduced as an emoji/icon.
    "faClockO",
    # \footnotemark[\value{footnote}] -- print-only citation marker, no
    # pagination on a web page for it to point at.
    "footnotemark",
    # hyperref PDF-bookmark anchor; vertical-skip spacing tweak: neither has
    # a visible effect here.
    "phantomsection", "shlokavskip",
    # print-only pagination/column-layout hints, no web equivalent.
    "pagebreak", "linebreak", "vfill", "columnbreak",
    # plain-TeX preamble markers around raw \def-based macro definitions
    # (e.g. surya-namaskara.tex's \makeatletter\def\vhrulefill#1{...}
    # \makeatother) -- \def itself is handled by its own dispatch below,
    # which skips these entirely, so the markers have nothing left to do.
    "makeatletter", "makeatother",
    # rudra-prashnah.tex: bare "\sn"/"\ar" mid-mantra, with no braced
    # argument and no \newcommand definition anywhere in this corpus --
    # stray backslashes in the source (typo), not real macros; dropped
    # rather than leaked as literal text.
    "sn", "ar",
}
DROPPED_ONE_ARG = {
    "label", "vspace", "setmainfont", "mbox", "hspace",
    # print-only citation/pagination hints, no web equivalent to reproduce.
    "footnotetext", "footnote", "needspace",
    # standalone \value{counter} (outside \footnotemark[\value{footnote}],
    # already handled above): no other counter in this corpus is read this
    # way, so it's just dropped rather than resolved.
    "value",
    # image inclusion: this converter has no image pipeline, so both the
    # search-path declaration and each \includegraphics{} (with its usual
    # \includegraphics[width=...]{path} optional sizing) are dropped
    # wholesale, path and all.
    "graphicspath", "includegraphics",
}
DROPPED_TWO_ARG = {"setlength", "addtolength"}  # lint-checked for begingroup/brace scoping
DROPPED_TWO_ARG_NO_LINT = {"fontsize", "markboth"}  # markboth: print page-header bookmarking, no visible effect
UNWRAP_ONE_ARG = {
    "textbf", "textsf", "textit", "emph", "centerline", "textsuperscript",
    # styling/box wrappers with no web equivalent worth reproducing --
    # content kept, wrapper dropped.
    "underline", "fbox",
    # \rlap{text} (purvanga/prana-pratishtha.tex's verse citation, e.g.
    # "...स्वस्ति॥\rlap{ऋक्~१०.५९.६॥}"): a zero-width print overlay trick,
    # rendered here as ordinary trailing text instead.
    "rlap",
}

# \X for X not a letter: known literal-producing escapes (\% is already
# unescaped during comment stripping, so it never reaches here). A trailing
# "\" immediately before a newline (go-puja.tex has exactly one, a stray
# corpus artifact with no other sensible reading) is absorbed like "\-".
ESCAPED_SYMBOLS = {"&": "&", "_": "_", "#": "#", " ": " ", "-": "", "\n": ""}

# --- puja-vidhanam-specific shared boilerplate ------------------------------
# puja-vidhanam/preamble.tex and purana-dhyana-shloka.tex define ~30 macros
# every individual puja file relies on but never defines itself (loaded only
# by the book-assembly .tex files, which this converter doesn't read). Their
# definitions are transcribed here directly from those two files rather than
# generically loading \newcommand/\renewcommand from preamble.tex's raw text:
# some of preamld.tex's redefinitions (e.g. \resetSankalpa's own body is a
# *nested* block of further \renewcommand calls, only meant to take effect
# when \resetSankalpa is actually invoked) would corrupt a naive whole-file
# textual-substitution pass, so a hand-verified transcription is safer here
# than a generic loader.
#
# PUJA_TEXT_MACRO_DEFAULTS seeds plain-text placeholders (sankalpa date/time/
# purpose fields etc.) with preamble.tex's own defaults; any file's own
# \renewcommand overrides its entry from that point in the document onward
# (see the \renewcommand dispatch below). \blank's rendering ("(   )") and
# \see's footnote-to-a-print-page-number (dropped -- meaningless online) are
# baked into these where preamble.tex's own default reads as \blank / \blank\see{...}.
PUJA_BLANK = "(   )"
PUJA_TEXT_MACRO_DEFAULTS = {
    "devaName": "देव", "devAya": "", "devaH": "",
    "achamanam": "आचमनम्।", "achamya": "(आचम्य)", "pranayama": "प्राणान् आयम्य।",
    "samvatsara": PUJA_BLANK, "ayane": PUJA_BLANK, "rtu": PUJA_BLANK, "masa": PUJA_BLANK,
    "paksha": "(शुक्ल / कृष्ण)", "tithau": PUJA_BLANK,
    "vasara": "(इन्दु / भौम / सौम्य / गुरु / भृगु / स्थिर / भानु)",
    "nakshatra": PUJA_BLANK, "yoga": PUJA_BLANK, "karana": PUJA_BLANK,
    "regularSankalpa": (
        "अस्माकं सहकुटुम्बानां क्षेमस्थैर्य-धैर्य-वीर्य-विजय-आयुरारोग्य-ऐश्वर्याभिवृद्ध्यर्थं "
        "धर्मार्थकाममोक्षचतुर्विधफलपुरुषार्थसिद्ध्यर्थं पुत्रपौत्राभिवृद्ध्यर्थम् इष्टकाम्यार्थसिद्ध्यर्थं "
        "मम इहजन्मनि पूर्वजन्मनि जन्मान्तरे च सम्पादितानां ज्ञानाज्ञानकृतमहापातकचतुष्टय-व्यतिरिक्तानां "
        "रहस्यकृतानां प्रकाशकृतानां सर्वेषां पापानां सद्य अपनोदनद्वारा सकल-पापक्षयार्थं"
    ),
    "additionalSankalpa": "", "kaale": "", "prakaarena": "", "prityartham": "", "pujaam": "",
    # \OM/\OMshri are \ifbool{veda}{...}{...} in preamble.tex; since \ifbool
    # always takes the false branch here (no veda flag context to resolve),
    # these are pre-resolved to that branch's value directly.
    "OM": "", "OMshri": "श्री-",
}

# 0-arg macros whose body contains real structural macros (verses, \dnsub,
# etc.) -- spliced into the scanner stream at the invocation point (like
# \hyperref/\textbf unwrapping) so everything inside gets re-parsed normally,
# rather than flattened to inert text.
SPLICE_MACROS = {
    "shuklambaradharam": r"\twolineshloka*{शुक्लाम्बरधरं विष्णुं शशिवर्णं चतुर्भुजम्}{प्रसन्नवदनं ध्यायेत् सर्वविघ्नोपशान्तये}",
    "hiranyagarbha": r"\twolineshloka*{हिरण्यगर्भगर्भस्थं हेमबीजं विभावसोः}{अनन्तपुण्यफलदम् अतः शान्तिं प्रयच्छ मे}",
    "vighneshvaraYathasthanam": (
        r"श्रीविघ्नेश्वराय नमः यथास्थानं प्रतिष्ठापयामि। शोभनार्थे क्षेमाय पुनरागमनाय च।\\"
        r"(गणपति-प्रसादं शिरसा गृहीत्वा)"
    ),
    "aavaahitobhava": (
        r"आवाहितो भव। स्थापितो भव। सन्निहितो भव। सन्निरुद्धो भव। अवकुण्ठितो भव। "
        r"प्रीतो भव। सुप्रसन्नो भव। सुमुखो भव। वरदो भव। प्रसीद प्रसीद॥ "
        r"\twolineshloka*{स्वामिन् सर्वजगन्नाथ यावत्पूजावसानकम्}{तावत् त्वं प्रीतिभावेन बिम्बेऽस्मिन् सन्निधिं कुरु} "
        r"\centerline{॥इति प्राणप्रतिष्ठा॥}"
    ),
    "nArAyaNam": r"\twolineshloka*{नारायणं नमस्कृत्य नरं चैव नरोत्तमम्}{देवीं सरस्वतीं व्यासं ततो जयमुदीरयेत्}",
    "sankalpa": (
        r"\dnsub{सङ्कल्पः} "
        r"ममोपात्त-समस्त-दुरित-क्षयद्वारा श्री-परमेश्वर-प्रीत्यर्थं शुभे शोभने मुहूर्ते अद्य ब्रह्मणः "
        r"द्वितीयपरार्धे श्वेतवराहकल्पे वैवस्वतमन्वन्तरे अष्टाविंशतितमे कलियुगे प्रथमे पादे "
        r"जम्बूद्वीपे भारतवर्षे भरतखण्डे मेरोः दक्षिणे पार्श्वे शकाब्दे अस्मिन् वर्तमाने व्यावहारिकाणां "
        r"प्रभवादीनां षष्ट्याः संवत्सराणां मध्ये "
        r"\textbf{\samvatsara} नाम संवत्सरे \textbf{\ayane{}} \textbf{\rtu}-ऋतौ \textbf{\masa}-मासे "
        r"\textbf{\paksha}पक्षे \textbf{\tithau} शुभतिथौ \textbf{\vasara}-वासरयुक्तायां "
        r"\textbf{\nakshatra}-नक्षत्र-\textbf{\yoga}-योग-\textbf{\karana}-करण-युक्तायां "
        r"च एवं गुण-विशेषण-विशिष्टायाम् अस्याम्\\"
        r"\textbf{\tithau{}} शुभतिथौ "
        r"\regularSankalpa{} \additionalSankalpa{} \prityartham{} \kaale{} \prakaarena{} "
        r"यथाशक्ति-ध्यान-आवाहनादि-षोडशोपचारैः \pujaam{} करिष्ये।\\"
        r"तदङ्गं कलशपूजां च करिष्ये।"
    ),
    # Invoking \resetSankalpa re-applies preamble.tex's own defaults for the
    # sankalpa placeholders (as opposed to whatever a file redefined them to
    # earlier) -- spliced as the literal \renewcommand sequence so the
    # generic \renewcommand dispatch below applies each one, in order, from
    # this point in the document onward.
    "resetSankalpa": "\n".join(
        r"\renewcommand{\%s}{%s}" % (k, v) for k, v in {
            "samvatsara": PUJA_BLANK, "ayane": "(उत्तरायणे/दक्षिणायने)", "rtu": PUJA_BLANK, "masa": PUJA_BLANK,
            "paksha": "(शुक्ल / कृष्ण)", "tithau": PUJA_BLANK,
            "vasara": "(इन्दु / भौम / सौम्य / गुरु / भृगु / स्थिर / भानु)",
            "nakshatra": PUJA_BLANK, "yoga": PUJA_BLANK, "karana": PUJA_BLANK,
            "additionalSankalpa": "", "kaale": "", "prakaarena": "", "prityartham": "", "pujaam": "",
        }.items()
    ) + "\n" + r"\renewcommand{\regularSankalpa}{%s}" % PUJA_TEXT_MACRO_DEFAULTS["regularSankalpa"],
    # purana-dhyana-shloka.tex's own 0-arg macros, invoked at the top of
    # several kathas (e.g. shivaratri-vrata-katha-linga-puranam.tex,
    # ekadashi-mahatmyam-padma-puranam.tex) that \input{} it for these
    # definitions but are parsed here independently of that file (each
    # \input{} target is preprocessed/expanded on its own, so a katha file
    # can't pick up a *different* file's \newcommand this way) -- so, as
    # with the preamble.tex macros above, transcribed directly instead.
    "ganapatyadiDhyanam": r"""
\dnsub{श्री-महागणपति-प्रार्थना}
\twolineshloka*
{शुक्लाम्बरधरं विष्णुं शशिवर्णं चतुर्भुजम्}
{प्रसन्नवदनं ध्यायेत् सर्वविघ्नोपशान्तये}
\twolineshloka*
{वागीशाद्याः सुमनसः सर्वार्थानामुपक्रमे}
{यं नत्वा कृतकृत्याः स्युस्तं नमामि गजाननम्}
\dnsub{श्री-गुरु-प्रार्थना}
\twolineshloka*
{गुरुर्ब्रह्मा गुरुर्विष्णुर्गुरुर्देवो महेश्वरः}
{गुरुः साक्षात् परं ब्रह्म तस्मै श्री-गुरवे नमः}
\twolineshloka*
{सदाशिवसमारम्भां शङ्कराचार्यमध्यमाम्}
{अस्मदाचार्यपर्यन्तां वन्दे गुरुपरम्पराम्}
\dnsub{श्री-सरस्वती-प्रार्थना}
\fourlineindentedshloka*
{दोर्भिर्युक्ता चतुर्भिः स्फटिकमणिनिभैरक्षमालां दधाना}
{हस्तेनैकेन पद्मं सितमपि च शुकं पुस्तकं चापरेण}
{भासा कुन्देन्दुशङ्खस्फटिकमणिनिभा भासमानाऽसमाना}
{सा मे वाग्देवतेयं निवसतु वदने सर्वदा सुप्रसन्ना}
\dnsub{श्री-व्यास-नमस्क्रिया}
\resetShloka
\twolineshloka
{व्यासं वसिष्ठनप्तारं शक्तेः पौत्रमकल्मषम्}
{पराशरात्मजं वन्दे शुकतातं तपोनिधिम्}
\fourlineindentedshloka
{अभ्रश्यामः पिङ्गजटाबद्धकलापः}
{प्रांशुर्दण्डी कृष्णमृगत्वक्परिधानः}
{साक्षाल्लोकान् पावयमानः कविमुख्यः}
{पाराशर्यः पर्वसु रूपं विवृणोतु}
\twolineshloka
{जयति पराशरसूनुः सत्यवतीहृदयनन्दनो व्यासः}
{यस्यास्यकमलगलितं वाङ्मयममृतं जगत् पिबति}
\resetShloka
""",
    "genMangalaShloka": r"""
\dnsub{मङ्गलश्लोकाः}
\fourlineindentedshloka*
{स्वस्ति प्रजाभ्यः परिपालयन्तां}
{न्यायेन मार्गेण महीं महीशाः}
{गोब्राह्मणेभ्यः शुभमस्तु नित्यं}
{लोकाः समस्ताः सुखिनो भवन्तु}
\twolineshloka*
{काले वर्षतु पर्जन्यः पृथिवी सस्यशालिनी}
{देशोऽयं क्षोभरहितो ब्राह्मणाः सन्तु निर्भयाः}
\twolineshloka*
{अपुत्राः पुत्रिणः सन्तु पुत्रिणः सन्तु पौत्रिणः}
{अधनाः सधनाः सन्तु जीवन्तु शरदां शतम्}
\twolineshloka*
{यदक्षरपदभ्रष्टं मात्राहीनं तु यद् भवेत्}
{तत् सर्वं क्षम्यतां देव नारायण नमोऽस्तुते}
\twolineshloka*
{विसर्गबिन्दुमात्राश्च पदपादाक्षराणि च}
{न्यूनानि चातिरिक्तानि क्षमस्व पुरुषोत्तम}
\twolineshloka*
{यज्ञेशाच्युत गोविन्द माधवानन्त केशव}
{कृष्ण विष्णो हृषीकेश वासुदेव नमोऽस्तुते}
\fourlineindentedshloka*
{कायेन वाचा मनसेन्द्रियैर्वा}
{बुद्‌ध्याऽऽत्मना वा प्रकृतेः स्वभावात्}
{करोमि यद्यत् सकलं परस्मै}
{नारायणायेति समर्पयामि}
""",
    "lingaPuranam": r"""
\dnsub{लिङ्गपुराणम् — मङ्गलश्लोकः}
\twolineshloka*
{नमो रुद्राय हरये ब्रह्मणे परमात्मने}
{प्रधानपुरुषेशाय सर्गस्थित्यन्तकारिणे}
\nArAyaNam
""",
    "padmaPuranam": r"""
\dnsub{पाद्ममहापुराणम् — मङ्गलश्लोकः}
\fourlineindentedshloka*
{स्वच्छं चन्द्रावदातं करिकर-मकर-क्षोभ-सञ्जात-फेनं}
{ब्रह्मोद्भूतिप्रसक्तैर्व्रतनियमपरैः सेवितं विप्रमुख्यैः}
{ओङ्कारालङ्कृतेन त्रिभुवनगुरुणा ब्रह्मणा दृष्टिपूतं}
{सम्भोगाभोगरम्यं जलमशुभहरं पौष्करं नः पुनातु}
\nArAyaNam
""",
}

# \kshama{name} (1-arg): an "apology for deficiencies in this worship" verse
# personalizing the closing line with the deity's name.
KSHAMA_TEMPLATE = (
    r"\dnsub{अपराध-क्षमापनम्} "
    r"\twolineshloka*{यस्य स्मृत्या च नामोक्त्या तपः-पूजा-क्रियादिषु}{न्यूनं सम्पूर्णतां याति सद्यो वन्दे %s} "
    r"\fourlineindentedshloka*{कायेन वाचा मनसेन्द्रियैर्वा}{बुद्‌ध्याऽऽत्मना वा प्रकृतेः स्वभावात्}"
    r"{करोमि यद्यत् सकलं परस्मै}{नारायणायेति समर्पयामि} "
    r"\centerline{सर्वं तत्सद्ब्रह्मार्पणमस्तु।}"
)

# Macro names dispatched specially elsewhere in parse_blocks() -- \renewcommand
# never registers a text-macro override for these, however it's used in the
# corpus, so a stray/unexpected redefinition can't shadow real behavior.
PROTECTED_MACRO_NAMES = (
    {"sect", "chapt", "chapter", "part", "dnsub", "uvacha", "devanumber", "resetShloka",
     "addtocounter", "refstepcounter", "stepcounter", "ifbool", "input", "let", "renewcommand",
     "begingroup", "endgroup", "closesection", "closesub", "blank", "see", "kshama",
     "setcounter", "newcounter", "arabic", "def", "parbox", "multicolumn"}
    | set(ARITY) | set(SPLICE_MACROS)
)

# The reliable signal for a closing colophon is the leading "इति" ("thus"),
# not the specific closing word (सम्पूर्णम्/समाप्तम्/स्तोत्रम्/स्तवः/... all occur).
# Note: \b is unreliable right after Devanagari dependent vowel signs (they're
# Unicode combining marks, category Mn -- not \w characters to Python's re
# module), so this requires an explicit whitespace separator instead of \b.
PUSHPIKA_RE = re.compile(r"॥\s*इति\s.*॥")
ATTRIBUTION_RE = re.compile(r"^[{}\s]*-{2,3}(.+)$")
NEWCOMMAND_RE = re.compile(r"\\newcommand\{\\([A-Za-z]+)\}")
# \footnotemark(\[...\])? -- a print-only citation marker occasionally
# embedded mid-verse (e.g. nrisimha-jayanti-puja.tex's
# "...परमेश्वर\footnotemark", go-puja.tex's "...गृह्ण\footnotemark[\value{footnote}] धेनुके"):
# since a verse line's text is a raw captured argument (never re-scanned by
# the main dispatch loop the way \footnotemark is handled there), it needs
# the same drop here too.
INLINE_STRIP_RE = re.compile(r"\\hspace\{[^{}]*\}|\\mbox\{\}|\\nobreak\b|\\footnotemark(\[[^\]]*\])?")
# Text-styling wrappers occasionally used inside a heading/title argument
# (e.g. gita.tex's "\textsf{---}" chapter-name separator); read_braced_arg()
# returns that argument's raw substring unexpanded, so these need unwrapping
# here rather than relying on the main scanner's UNWRAP_ONE_ARG dispatch,
# which only ever sees body text, never a captured argument string.
INLINE_UNWRAP_RE = re.compile(r"\\(?:textbf|textsf|textit|emph|centerline|textsuperscript)\{([^{}]*)\}")
# SkandaShashthiKavacham.tex's \sect{\fontspec{Arial Unicode MS}{content}} --
# this file's own convention for switching to a Tamil-capable font around a
# span of text, used here (unlike the main dispatch's \fontspec, which only
# ever sees the font-name argument, e.g. \fontspec[Script=Devanagari]{Siddhanta}
# with no second argument) inside a captured \sect{} title.
INLINE_FONTSPEC_RE = re.compile(r"\\fontspec\{[^{}]*\}\{([^{}]*)\}")
# \blank similarly appears mid-verse (nrisimha-jayanti-puja.tex's sankalpa
# line) as well as inside \renewcommand bodies that themselves get spliced
# (where it's handled by the main dispatch instead) -- this covers the
# raw-argument case.
INLINE_BLANK_RE = re.compile(r"\\blank\b")


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

    def read_braced_or_command_arg(self):
        """Like read_braced_arg(), but also accepts a single bare control
        sequence (e.g. \\setlength\\columnsep{0pt} -- \\columnsep needs no
        braces since it's already one token). Only used where the argument's
        content is discarded, so a bare command's name doesn't need to be
        returned meaningfully."""
        self.skip_ws()
        if self.peek() == "\\":
            self.read_command()
            return None
        return self.read_braced_arg()

    def splice(self, s):
        """Re-inject text at the current position so it gets scanned normally
        on the next loop iteration -- used to unwrap \\hyperref[...]{X} and
        \\textbf{X} etc. into X, so a macro call inside X (e.g.
        \\hyperref[...]{\\closesection}) is still dispatched properly rather
        than dumped as literal backslash-text."""
        self.text = self.text[: self.pos] + s + self.text[self.pos :]
        self.n = len(self.text)


def clean_line_text(s, text_macros=None):
    if text_macros:
        # A 0-arg text-macro placeholder (e.g. \devaName, renewcommand'd
        # per-file from preamble.tex's default -- see
        # PUJA_TEXT_MACRO_DEFAULTS) can appear *inside* a verse macro's
        # braced argument (e.g. purvanga/kalasha-puja.tex's "आयान्तु
        # \devaName{}पूजार्थं..." inside a \twolineshloka{} line). That text
        # is captured as a raw substring by read_braced_arg() and never
        # re-enters the main dispatch loop where text_macros lookups
        # normally happen, so it's substituted here instead.
        for name, value in text_macros.items():
            # lambda replacement: a renewcommand'd value is arbitrary text
            # and must never be interpreted for backreferences (e.g. a
            # literal "\1") the way a raw replacement string would be.
            s = re.sub(r"\\" + re.escape(name) + r"\b(\{\})?", lambda m, v=value: v, s)
    s = INLINE_STRIP_RE.sub("", s)
    s = INLINE_FONTSPEC_RE.sub(r"\1", s)
    while True:
        s2 = INLINE_UNWRAP_RE.sub(r"\1", s)
        if s2 == s:
            break
        s = s2
    s = INLINE_BLANK_RE.sub(PUJA_BLANK, s)
    s = s.replace("~", " ")  # TeX non-breaking space
    return re.sub(r"\s+", " ", s).strip()


def expand_macro_invocations(text, path, name, n, body):
    """Replaces each \\name{a1}...{aN} invocation with `body`, substituting
    #1..#N with that invocation's own raw argument text -- unlike a 0-arg
    macro's blind whole-document substitution, each invocation can supply
    different arguments (e.g. mahabharatam's virāṭaparva.tex:
    \\onelineindentedshloka{A}{B} ten times over, each with its own A/B)."""
    invoke_re = re.compile(r"\\" + re.escape(name) + r"\b")
    while True:
        m = invoke_re.search(text)
        if not m:
            return text
        scanner = TexScanner(text, path)
        scanner.pos = m.end()
        args = [scanner.read_braced_arg() for _ in range(n)]
        expanded = body
        for i, a in enumerate(args, start=1):
            expanded = expanded.replace(f"#{i}", a)
        text = text[: m.start()] + expanded + text[scanner.pos :]


def expand_local_macros(text, path):
    """Pre-scan for \\newcommand{\\foo}{body} (optionally \\newcommand{\\foo}[N]{body})
    near the top of the file and splice `body` in for every later \\foo --
    handles file-local macros like NamaRamayanam.tex's \\jaya (0-arg) and
    mahabharatam's virāṭaparva.tex's \\onelineindentedshloka (2-arg)
    generically, not as hardcoded cases. The xparse-style optional-default
    form (\\newcommand{\\foo}[N][default]{body}, vedamantra-book's
    \\anuvakamend) is out of scope -- skipped rather than mis-expanded."""
    while True:
        m = NEWCOMMAND_RE.search(text)
        if not m:
            return text
        name = m.group(1)
        scanner = TexScanner(text, path)
        scanner.pos = m.end()
        n = 0
        if scanner.peek() == "[":
            n_arg = scanner.read_bracket_arg()
            try:
                n = int(n_arg)
            except ValueError:
                raise ParseError(path, scanner.line_at(scanner.pos), f"\\newcommand{{\\{name}}}[{n_arg}] -- non-integer arg count")
        skip = n > 0 and scanner.peek() == "["  # xparse-style [N][default] -- out of scope
        if skip:
            scanner.read_bracket_arg()
        body = scanner.read_braced_arg()
        text = text[: m.start()] + text[scanner.pos :]
        if skip:
            continue
        if n == 0:
            text = re.sub(r"\\" + re.escape(name) + r"\b", lambda _match: body, text)
        else:
            text = expand_macro_invocations(text, path, name, n, body)


def resolve_input(rel_path, warn):
    """Reads and preprocesses a \\input{path} target for splicing inline, if
    it's a same-repo reference this corpus's own conventions make safely
    resolvable: always relative to the repo root (matching how e.g.
    pujas.tex itself -- at the repo root -- writes \\input{pujas/foo}, and
    shivaratri-puja.tex -- itself inside pujas/ -- writes the same
    pujas/-prefixed form, not a path relative to its own directory), never
    a "../" cross-repo reference (puja-vidhanam pulling in namavali-manjari/
    stotra-sangrahah files this way is real, but resolving another repo's
    files is out of scope here -- this converter processes one repo's files
    per run). Returns None (leaving the \\input silently dropped, as before)
    if the path is cross-repo, doesn't exist, or can't be read as UTF-8."""
    if rel_path.startswith("../") or rel_path.startswith("/"):
        return None
    candidate = Path(rel_path if rel_path.endswith(".tex") else rel_path + ".tex")
    if not candidate.is_file():
        return None
    try:
        text = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        warn(f"\\input{{{rel_path}}}: {candidate} is not valid UTF-8, left unresolved")
        return None
    body, _ = strip_comments_and_extract_meta(text)
    return expand_local_macros(body, str(candidate))


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


def emit_verse_block(name, starred, args, counter, text_macros=None):
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

    pada_tags = (["odd", "even"] * len(verse_args))[: len(verse_args)] if name in INDENTED_MACROS else [None] * len(verse_args)

    lines = [
        {"pada": pada, "text": clean_line_text(text, text_macros), "ending": ending}
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
        block["citation"] = clean_line_text(citation, text_macros)
    return block


NAMED_COUNTER_REF_RE = re.compile(r"^\\(?:arabic|value)\{(\w+)\}$")


def resolve_scalar_arg(arg, counter, named_counters):
    """Resolves a \\devanumber{...}/\\addtocounter{...}{...} argument that may
    be a literal integer, or a \\arabic{name}/\\value{name} reference to a
    counter's current value (shlokacount, tracked by `counter`, or any other
    name registered via \\newcounter and stepped by \\refstepcounter/
    \\stepcounter). Raises ValueError for anything else, same as a bare
    int(arg) would."""
    arg = arg.strip()
    m = NAMED_COUNTER_REF_RE.match(arg)
    if m:
        name = m.group(1)
        return counter.value if name == "shlokacount" else named_counters.get(name, 0)
    return int(arg)


def parse_blocks(text, path, warn):
    scanner = TexScanner(text, path)
    counter = CounterModel()
    blocks = []
    prose_buf = []
    scope_stack = []
    begingroup_depth = 0
    brace_depth = 0
    # \let\X\Y aliasing (e.g. \let\chapt\sect, \let\sect\dnsub for one local
    # macro to borrow another's behavior): resolved by name right after every
    # \read_command(), so every dispatch branch below sees the effective name
    # transparently. Scoped to \begingroup/\endgroup, matching how this
    # corpus actually uses it (each \let sits inside its own begingroup so it
    # reverts afterward) -- a bare {...} group is not tracked as a scope here
    # since no \let in the corpus needed that.
    aliases = {}
    alias_stack = []
    # Plain-text macro substitution (\renewcommand{\X}{body} and the
    # puja-vidhanam placeholder defaults) -- see PUJA_TEXT_MACRO_DEFAULTS.
    # Position-aware: a file's own \renewcommand overrides its entry from
    # that point in the document onward, matching real LaTeX semantics
    # (unlike expand_local_macros()'s whole-document textual substitution).
    text_macros = dict(PUJA_TEXT_MACRO_DEFAULTS)
    # \newcounter{name}/\refstepcounter{name}/\stepcounter{name}/\arabic{name}:
    # a running value per counter *other* than shlokacount (which the
    # CounterModel above already owns) -- e.g. MahaNyasah.tex's \newcounter{dik}
    # counts through the 9 directions of its ritual diagram, read back via
    # \devanumber{\arabic{dik}}.
    named_counters = {}
    # \begin{tabular}/\{supertabular}/\{longtable}: a stack of
    # {"rows": [...], "current_row": [...], "cell_buf": [...]} accumulators
    # (a stack, not a single value, in case of nested tables). While one is
    # active, plain-text output (chars, ~, escaped symbols) is redirected
    # here instead of prose_buf, and bare "&"/"\\" become cell/row
    # separators instead of literal text/a forced line break. Macros
    # invoked *inside* a cell (e.g. \textbf{}) still append to prose_buf,
    # not the cell buffer -- none of this corpus's actual tables use them,
    # so this is intentionally not handled generically.
    table_stack = []

    def emit_text(s):
        if table_stack:
            table_stack[-1]["cell_buf"].append(s)
        else:
            prose_buf.append(s)

    def flush():
        flush_prose(prose_buf, blocks)

    while not scanner.eof():
        c = scanner.peek()

        if table_stack and c == "&":
            tbl = table_stack[-1]
            tbl["current_row"].append(clean_line_text("".join(tbl["cell_buf"]), text_macros))
            tbl["cell_buf"] = []
            scanner.pos += 1
            continue

        if c == "\\":
            nxt = scanner.text[scanner.pos + 1] if scanner.pos + 1 < scanner.n else ""
            if nxt == "\\":
                scanner.pos += 2
                scanner.read_bracket_arg()
                if table_stack:
                    tbl = table_stack[-1]
                    tbl["current_row"].append(clean_line_text("".join(tbl["cell_buf"]), text_macros))
                    tbl["cell_buf"] = []
                    tbl["rows"].append(tbl["current_row"])
                    tbl["current_row"] = []
                else:
                    prose_buf.append("\n")
                continue
            if nxt in ESCAPED_SYMBOLS:
                emit_text(ESCAPED_SYMBOLS[nxt])
                scanner.pos += 2
                continue

            name, starred = scanner.read_command()
            name = aliases.get(name, name)

            if name == "let":
                x_name, _ = scanner.read_command()
                y_name, _ = scanner.read_command()
                aliases[x_name] = aliases.get(y_name, y_name)
                continue

            if name == "def":
                # Raw plain-TeX \def<cs><param-text>{<body>} (e.g.
                # surya-namaskara.tex's \def\vhrulefill#1{\leavevmode\leaders
                # \hrule\@height#1\hfill \kern\z@}) defines a pure print-
                # layout helper (rule-drawing) with no verse text and uses
                # raw control sequences like \@height that this parser's
                # command reader can't tokenize (CMD_RE is [A-Za-z]+ only).
                # Skip the whole definition -- name, parameter text, body --
                # rather than expanding or re-parsing it.
                save_pos = scanner.pos
                try:
                    scanner.read_command()
                except ParseError:
                    # \def<symbol>... (e.g. KanchiSwastiVachanam.tex's
                    # \catcode`==\active \def={\discretionary{-}{}{-}}, an
                    # active-character line-break hint -- not a nameable
                    # control sequence this parser's CMD_RE can consume) --
                    # skipping isn't safe here, so fall back to \def's
                    # pre-existing behavior (an ordinary unrecognized macro,
                    # left as literal text) and let the rest of the line,
                    # "=" symbols included, print through unaffected.
                    scanner.pos = save_pos
                    warn(r"\def<symbol>{...} target is not a nameable command; treating \def as literal text")
                    emit_text("\\def")
                    continue
                scanner.skip_ws()
                while scanner.pos < scanner.n and scanner.peek() != "{":
                    scanner.pos += 1
                scanner.read_braced_arg()
                continue

            if name == "renewcommand":
                # \renewcommand{\X}{body}: registers/overrides \X from here
                # on (see text_macros above). The raw body is stored (not
                # clean_line_text'd) because some bodies contain real
                # structural content -- e.g. go-puja.tex's
                # \renewcommand{\additionalSankalpa}{\begin{itemize}...} --
                # which needs the normal dispatch loop to see \begin/\item
                # etc. properly when \additionalSankalpa is later invoked
                # (see the splice in the text_macros fallback below), not a
                # flattened, unprocessed string.
                # A parameterized form (\renewcommand{\X}[N]{...}, seen once
                # in this corpus for \sect itself, in a file already excluded
                # for an unrelated parse error) is out of scope -- skip it
                # rather than mis-register a templated body as literal text.
                target_arg = scanner.read_braced_arg().strip()
                target_name = target_arg.lstrip("\\")
                if scanner.peek() == "[":
                    scanner.read_bracket_arg()
                    scanner.read_braced_arg()
                    continue
                body = scanner.read_braced_arg()
                if target_name not in PROTECTED_MACRO_NAMES:
                    text_macros[target_name] = body
                continue

            if name == "ldots":
                emit_text("…")
                continue

            if name == "circ":
                emit_text("॰")  # yajur-upakarma.tex's \sep word-separator dot (Devanagari abbreviation sign)
                continue

            if name == "lbrack":
                emit_text("[")
                continue

            if name == "rbrack":
                emit_text("]")
                continue

            if name == "item":
                scanner.read_bracket_arg()  # optional custom label, e.g. \item[a.] -- unused in this corpus
                emit_text("\n")  # starts each item on its own line, like a forced line break
                continue

            if name == "blank":
                emit_text(PUJA_BLANK)
                continue

            if name == "see":
                scanner.read_braced_arg()  # footnote-to-a-print-page-number; meaningless online, dropped
                continue

            if name == "kshama":
                # Two shipped files (sarasvati-puja.tex, savitri-vratam.tex)
                # invoke this bare, with no {name} argument at all -- a
                # pre-existing bug in that source (real LaTeX would silently
                # swallow the next token, usually \closesub, as #1 instead),
                # not something to reproduce here. Tolerate it: an empty name
                # is a reasonable fallback, and leaves the next token alone.
                scanner.skip_ws()
                deva_name = scanner.read_braced_arg() if scanner.peek() == "{" else ""
                scanner.splice(KSHAMA_TEMPLATE % clean_line_text(deva_name, text_macros))
                continue

            if name in SPLICE_MACROS:
                scanner.splice(SPLICE_MACROS[name])
                continue

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
                    elif envname in TABLE_ENVIRONMENTS:
                        scanner.read_braced_arg()  # column spec, e.g. {ll} -- not needed for HTML output
                        flush()
                        table_stack.append({"rows": [], "current_row": [], "cell_buf": []})
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
                    elif envname in TABLE_ENVIRONMENTS:
                        tbl = table_stack.pop()
                        if tbl["cell_buf"] or tbl["current_row"]:
                            tbl["current_row"].append(clean_line_text("".join(tbl["cell_buf"]), text_macros))
                            tbl["rows"].append(tbl["current_row"])
                        flush()
                        blocks.append({"type": "table", "rows": tbl["rows"]})
                continue

            if name in ("sect", "chapt", "chapter", "part", "section"):
                # \chapter/\part/\section (mahabharatam, adhyatmaramayanam,
                # puja-vidhanam) are plain heading macros here too, same as
                # \sect/\chapt -- some source repos \renewcommand them with
                # extra bookkeeping
                # (their own running shloka-count counters, feeding a
                # book-compile-only colophon), but that has no visible effect
                # beyond what \sect/\chapt already do: start a new heading
                # and reset the per-section verse count.
                (title,) = (scanner.read_braced_arg(),)
                flush()
                counter.reset()
                blocks.append({"type": "heading", "macro": name, "text": clean_line_text(title, text_macros), "resets_counter": True})
                continue

            # adhyatmaramayanam-specific: \iti{kanda}{sarga}/\itibala{kanda}{sarga}
            # /\itikanda{text} are file-local (preamble.tex) colophon macros
            # that close a sarga/kanda with a fixed template. Their real
            # bodies also print a running total-shloka-count aside (book-
            # compile bookkeeping via \newcounter/\value, not part of the
            # verse text itself), which is intentionally not reproduced here
            # -- would need a general LaTeX counter/\value engine for
            # marginal value. The colophon text itself matches preamble.tex's
            # own template verbatim.
            if name in ("iti", "itibala"):
                kanda = clean_line_text(scanner.read_braced_arg(), text_macros)
                sarga = clean_line_text(scanner.read_braced_arg(), text_macros)
                flush()
                colophon = f"॥इति श्रीमदध्यात्मरामायणे उमामहेश्वरसंवादे {kanda} {sarga} सर्गः॥"
                blocks.append({"type": "pushpika", "text": colophon})
                blocks.append({"type": "decoration", "style": "closesub"})
                continue

            if name == "itikanda":
                colophon = clean_line_text(scanner.read_braced_arg(), text_macros)
                flush()
                blocks.append({"type": "pushpika", "text": colophon})
                blocks.append({"type": "decoration", "style": "closesection"})
                continue

            if name == "dnsub":
                (label,) = (scanner.read_braced_arg(),)
                flush()
                blocks.append({"type": "subheading", "macro": "dnsub", "text": clean_line_text(label, text_macros)})
                continue

            if name == "uvacha":
                (speaker,) = (scanner.read_braced_arg(),)
                flush()
                blocks.append({"type": "uvacha", "text": clean_line_text(speaker, text_macros)})
                continue

            if name == "ifbool":
                # \ifbool{name}{true-branch}{false-branch} (etoolbox). Each
                # boolean's resolution is a corpus-editorial choice, not a
                # real \ifbool{} evaluation (this converter has no flag
                # state):
                #   "katha" -> true-branch: puja-vidhanam wraps its katha
                #     \input{}s this way, and those should render as
                #     sub-sections of the puja that references them.
                #   "individual" -> true-branch: same shape as "katha" --
                #     gates a per-mahatmya \input{} + itemize listing (e.g.
                #     ekadashi-purusha-sukta-vidhana-puja.tex's Padma-Puranam
                #     and Vrata-Raja Ekadashi mahatmya kathas), with an empty
                #     false-branch in every occurrence in this corpus.
                #   "veda" -> false-branch: the "regular" (non-Vedic) edition,
                #     matching \OM/\OMshri's own pre-resolution elsewhere.
                #   anything else -> dropped entirely (unknown semantics).
                # Both branches are raw, unparsed text at this point; splice()
                # re-injects the chosen one for the main loop to parse
                # normally (so a spliced \input{} still resolves).
                bool_name = scanner.read_braced_arg().strip()
                true_branch = scanner.read_braced_arg()
                false_branch = scanner.read_braced_arg()
                if bool_name in ("katha", "individual"):
                    scanner.splice(true_branch)
                elif bool_name == "veda":
                    scanner.splice(false_branch)
                continue

            if name == "input":
                rel_path = scanner.read_braced_arg().strip()
                resolved = resolve_input(rel_path, warn)
                if resolved is not None:
                    scanner.splice(resolved)
                continue

            if name in ARITY:
                nargs = ARITY[name]
                if starred and name in NO_STAR_SUPPORT:
                    warn(f"\\{name}* used but macro has no starred form; treating as unstarred")
                    starred = False

                def read_verse_arg():
                    # A verse macro's ending punctuation is synthesized by
                    # this parser (ENDING_TABLE), never sourced from the raw
                    # text, so a stray editorial danda/double-danda between/
                    # before its braced args (e.g. varamahalakshmi-vrata-
                    # katha.tex's misplaced "।") is a source typo, not real
                    # argument content -- skip it rather than hard-failing.
                    # Only this narrow punctuation set is skipped: if the
                    # next char instead starts a new command (e.g.
                    # ekadashi-mahatmyam-padma-puranam.tex's several
                    # \twolineshloka{single line} calls that are simply
                    # missing their 2nd line before the next \twolineshloka
                    # begins), that's a missing argument, not stray
                    # punctuation -- treat it as empty and leave the
                    # following command untouched for its own dispatch.
                    scanner.skip_ws()
                    while scanner.peek() in ("।", "॥"):
                        warn(f"stray {scanner.peek()!r} before \\{name} argument, skipping")
                        scanner.pos += 1
                        scanner.skip_ws()
                    if scanner.peek() != "{":
                        warn(f"\\{name} missing an expected argument (found {scanner.peek()!r}); treating as empty")
                        return ""
                    return scanner.read_braced_arg()

                args = [read_verse_arg() for _ in range(nargs)]
                flush()
                blocks.append(emit_verse_block(name, starred, args, counter, text_macros))
                continue

            if name == "devanumber":
                arg = scanner.read_braced_arg().strip()
                try:
                    n = resolve_scalar_arg(arg, counter, named_counters)
                except ValueError:
                    raise ParseError(path, scanner.line_at(scanner.pos), f"\\devanumber{{{arg}}} -- non-integer argument")
                emit_text(to_deva(n))
                continue

            if name == "newcounter":
                ctr_name = scanner.read_braced_arg().strip()
                named_counters.setdefault(ctr_name, 0)
                continue

            if name == "arabic":
                # Bare \arabic{name} outside \devanumber{} -- print the
                # counter's current value as a plain (non-Devanagari) number.
                ctr_name = scanner.read_braced_arg().strip()
                value = counter.value if ctr_name == "shlokacount" else named_counters.get(ctr_name, 0)
                emit_text(str(value))
                continue

            if name == "resetShloka":
                flush()
                counter.reset()
                blocks.append({"type": "counter-adjust", "op": "reset"})
                continue

            if name in ("refstepcounter", "stepcounter"):
                # adhyatmaramayanam manually bumps shlokacount this way in a
                # few spots (e.g. BalaKanda.tex); any other counter name is a
                # LaTeX-internal bookkeeping detail with no effect on the
                # verse text or numbering we render, so it's just dropped.
                ctr_name = scanner.read_braced_arg().strip()
                flush()
                if ctr_name == "shlokacount":
                    counter.step()
                    blocks.append({"type": "counter-adjust", "op": "add", "n": 1})
                else:
                    named_counters[ctr_name] = named_counters.get(ctr_name, 0) + 1
                continue

            if name == "addtocounter":
                arg1 = scanner.read_braced_arg().strip()
                arg2 = scanner.read_braced_arg().strip()
                try:
                    n = resolve_scalar_arg(arg2, counter, named_counters)
                except ValueError:
                    raise ParseError(path, scanner.line_at(scanner.pos), f"\\addtocounter{{{arg1}}}{{{arg2}}} -- non-integer amount")
                flush()
                if arg1 == "shlokacount":
                    counter.add(n)
                    blocks.append({"type": "counter-adjust", "op": "add", "n": n})
                else:
                    named_counters[arg1] = named_counters.get(arg1, 0) + n
                continue

            if name == "setcounter":
                # \setcounter{name}{value} -- sets rather than adds. Seen
                # for LaTeX-internal counters (page, secnumdepth) with no
                # web equivalent, and for a real content dependency in
                # MahaNyasah.tex: \setcounter{shlokacount}{\value{ssk}}
                # re-syncs the running verse count to a separately-tracked
                # "ssk" counter before rendering an aligned couplet with
                # \twolineshloka (so it numbers using ssk's sequence).
                ctr_name = scanner.read_braced_arg().strip()
                arg2 = scanner.read_braced_arg().strip()
                try:
                    n = resolve_scalar_arg(arg2, counter, named_counters)
                except ValueError:
                    raise ParseError(path, scanner.line_at(scanner.pos), f"\\setcounter{{{ctr_name}}}{{{arg2}}} -- non-integer value")
                flush()
                if ctr_name == "shlokacount":
                    counter.value = n
                    blocks.append({"type": "counter-adjust", "op": "set", "n": n})
                else:
                    named_counters[ctr_name] = n
                continue

            if name == "parbox":
                # \parbox[pos]{width}{content} -- print box-layout wrapper;
                # position and width are dropped, content is spliced back
                # for normal re-parsing (e.g. shankara-prashasti.tex's
                # \fbox{\parbox[]{0.8\linewidth}{...}} attribution note).
                scanner.read_bracket_arg()
                scanner.read_braced_arg()
                content = scanner.read_braced_arg()
                scanner.splice(content)
                continue

            if name == "multicolumn":
                # \multicolumn{n}{fmt}{content} inside a tabular row (e.g.
                # purvanga/prana-pratishtha.tex's karanyasa table) -- the
                # column-span count and alignment aren't modeled by this
                # converter's plain row/cell table type, so only the cell
                # content is kept.
                scanner.read_braced_arg()
                scanner.read_braced_arg()
                content = scanner.read_braced_arg()
                scanner.splice(content)
                continue

            if name in ("closesection", "closesub"):
                flush()
                blocks.append({"type": "decoration", "style": name})
                continue

            if name == "begingroup":
                begingroup_depth += 1
                alias_stack.append(dict(aliases))
                continue
            if name == "endgroup":
                begingroup_depth = max(0, begingroup_depth - 1)
                if alias_stack:
                    aliases = alias_stack.pop()
                continue

            if name in DROPPED_ZERO_ARG:
                scanner.read_bracket_arg()  # e.g. \nopagebreak[4]
                continue

            if name in DROPPED_ONE_ARG:
                scanner.read_bracket_arg()  # e.g. \setmainfont[Script=Devanagari]{Siddhanta}
                scanner.read_braced_arg()
                continue

            if name in DROPPED_TWO_ARG:
                scanner.read_braced_or_command_arg()  # e.g. \setlength\columnsep{0pt} -- \columnsep needs no braces
                scanner.read_braced_arg()
                if begingroup_depth == 0 and brace_depth == 0:
                    warn(f"\\{name} outside \\begingroup/\\endgroup (or brace-group) scope")
                continue

            if name in DROPPED_TWO_ARG_NO_LINT:
                scanner.read_braced_or_command_arg()
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

            if name in text_macros:
                scanner.splice(text_macros[name])
                continue

            warn(f"unrecognized macro \\{name}{'*' if starred else ''}, kept as literal text")
            emit_text("\\" + name + ("*" if starred else ""))
            continue

        elif c == "~":
            emit_text(" ")  # TeX non-breaking space
            scanner.pos += 1
            continue
        elif c == "$":
            # Math-mode toggle: this corpus never has real math, just a
            # single decorative symbol wrapped in $...$ (yajur-upakarma.tex's
            # \sep word-separator, \circ) -- transparent, like {}, rather
            # than building out real math-mode support for one symbol.
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
            emit_text(c)
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
