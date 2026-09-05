import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from tex_to_ir import (  # noqa: E402
    CounterModel,
    ParseError,
    TexScanner,
    clean_line_text,
    expand_local_macros,
    parse_blocks,
    strip_comments_and_extract_meta,
    to_deva,
)


class TestCleanLineText(unittest.TestCase):
    def test_unwraps_textsf_inside_a_title(self):
        # read_braced_arg() returns a heading's argument unexpanded, so a
        # nested \textsf{...} (gita.tex's chapter-name separator) needs
        # unwrapping here rather than relying on the main scanner dispatch,
        # which never sees a captured argument string.
        self.assertEqual(clean_line_text(r"प्रथमोऽध्यायः\textsf{---}अर्जुनविषादयोगः"), "प्रथमोऽध्यायः---अर्जुनविषादयोगः")

    def test_unwraps_fontspec_content_inside_a_title(self):
        # SkandaShashthiKavacham.tex: \sect{\fontspec{Arial Unicode MS}{...}}
        # -- the font-name argument is dropped, the Tamil content kept.
        self.assertEqual(clean_line_text(r"\fontspec{Arial Unicode MS}{கவசம்}"), "கவசம்")


class TestBraceBalancing(unittest.TestCase):
    def test_nested_braces_captured_verbatim(self):
        s = TexScanner(r"{रामं\hspace{1.3ex}जनकात्मजायुतं}", "t")
        inner = s.read_braced_arg()
        self.assertEqual(inner, r"रामं\hspace{1.3ex}जनकात्मजायुतं")

    def test_unterminated_argument_raises(self):
        s = TexScanner("{unterminated", "t")
        with self.assertRaises(ParseError):
            s.read_braced_arg()

    def test_bare_braces_are_transparent(self):
        blocks = parse_blocks("{plain text}", "t", lambda msg: None)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "prose")
        self.assertNotIn("{", blocks[0]["text"])
        self.assertNotIn("}", blocks[0]["text"])
        self.assertIn("plain text", blocks[0]["text"])


class TestStarredNumbering(unittest.TestCase):
    def test_oneline_unstarred(self):
        blocks = parse_blocks(r"\onelineshloka{A}", "t", lambda msg: None)
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertEqual(b["type"], "verse-1")
        self.assertEqual(b["verse_number"], 1)
        self.assertEqual(b["lines"][0]["ending"], "double-danda-numbered")

    def test_oneline_starred_drops_pair_and_number(self):
        blocks = parse_blocks(r"\onelineshloka*{A}", "t", lambda msg: None)
        b = blocks[0]
        self.assertIsNone(b["verse_number"])
        self.assertEqual(len(b["lines"]), 1)
        self.assertEqual(b["lines"][0]["ending"], "danda")

    def test_twoline_starred_keeps_double_danda_no_number(self):
        blocks = parse_blocks(r"\twolineshloka*{A}{B}", "t", lambda msg: None)
        b = blocks[0]
        self.assertIsNone(b["verse_number"])
        self.assertEqual(b["lines"][1]["ending"], "double-danda")

    def test_sixlineindentedshloka(self):
        # mahabharatam's own shloka.sty (not stotra-sangrahah's): a
        # 3-couplet extension of fourlineindentedshloka's odd/even
        # indentation pattern, no starred form.
        blocks = parse_blocks(r"\sixlineindentedshloka{A}{B}{C}{D}{E}{F}", "t", lambda msg: None)
        b = blocks[0]
        self.assertEqual(b["type"], "verse-6-indented")
        self.assertEqual(b["verse_number"], 1)
        self.assertEqual(
            [(l["pada"], l["text"], l["ending"]) for l in b["lines"]],
            [
                ("odd", "A", "none"), ("even", "B", "danda"),
                ("odd", "C", "none"), ("even", "D", "danda"),
                ("odd", "E", "none"), ("even", "F", "double-danda-numbered"),
            ],
        )


class TestCounterModel(unittest.TestCase):
    def test_reset_then_add_composite(self):
        # ShivaSahasranamaStotram-VishnuKrtam.tex: \resetShloka immediately
        # followed by \addtocounter{shlokacount}{159}, then the next verse
        # steps to 160.
        c = CounterModel()
        c.reset()
        c.add(159)
        self.assertEqual(c.step(), 160)

    def test_start_of_file_offset(self):
        # BrahmapaaraStotram.tex: \addtocounter{shlokacount}{53} then first
        # verse steps to 54.
        c = CounterModel()
        c.add(53)
        self.assertEqual(c.step(), 54)

    def test_to_deva(self):
        self.assertEqual(to_deva(0), "०")
        self.assertEqual(to_deva(9), "९")
        self.assertEqual(to_deva(10), "१०")
        self.assertEqual(to_deva(160), "१६०")

    def test_composite_via_full_parse(self):
        tex = r"""
\sect{test}
\uvacha{X}
{एवं नाम्नां सहस्रेण तुष्टाव वृषभध्वजम्॥१५९॥}
\resetShloka
\addtocounter{shlokacount}{159}
\twolineshloka
{A}
{B}
"""
        blocks = parse_blocks(tex, "t", lambda msg: None)
        verse_blocks = [b for b in blocks if b["type"] == "verse-2"]
        self.assertEqual(len(verse_blocks), 1)
        self.assertEqual(verse_blocks[0]["verse_number"], 160)


class TestMetaParsing(unittest.TestCase):
    def test_multivalue_field_kept_as_one_string(self):
        text = (
            "% !TeX program = XeLaTeX\n"
            "% --meta--\n"
            "% deity: Shiva, Shakti\n"
            "% --end-meta--\n"
            "\\sect{title}\n"
        )
        _, meta = strip_comments_and_extract_meta(text)
        self.assertEqual(meta["deity"], "Shiva, Shakti")


class TestLocalMacroExpansion(unittest.TestCase):
    def test_jaya_style_macro_expands_into_blocks(self):
        text = r"""\newcommand{\jaya}{\twolineshloka*{A}{B}}
\sect{t}
\jaya
"""
        body, _ = strip_comments_and_extract_meta(text)
        body = expand_local_macros(body, "t")
        self.assertNotIn(r"\jaya", body)
        blocks = parse_blocks(body, "t", lambda msg: None)
        types = [b["type"] for b in blocks]
        self.assertIn("verse-2", types)

    def test_parameterized_macro_each_invocation_gets_its_own_args(self):
        # mahabharatam's virāṭaparva.tex: \onelineindentedshloka{#1}{#2}
        # renders #1 as a plain line then #2 as a numbered onelineshloka --
        # each of its several invocations must substitute its own arguments,
        # not the first invocation's args reused everywhere (unlike the
        # 0-arg case, this can't be a single blind whole-document \bfoo ->
        # body substitution).
        text = (
            r"\newcommand{\onelineindentedshloka}[2]{{#1}\\\onelineshloka{#2}}"
            + "\n\\sect{t}\n"
            + r"\onelineindentedshloka{A1}{A2}" + "\n"
            + r"\onelineindentedshloka{B1}{B2}" + "\n"
        )
        body, _ = strip_comments_and_extract_meta(text)
        body = expand_local_macros(body, "t")
        self.assertNotIn("onelineindentedshloka", body)
        blocks = parse_blocks(body, "t", lambda msg: None)
        prose_texts = [b["text"] for b in blocks if b["type"] == "prose"]
        verse_texts = [b["lines"][0]["text"] for b in blocks if b["type"] == "verse-1"]
        self.assertEqual(prose_texts, ["A1", "B1"])
        self.assertEqual(verse_texts, ["A2", "B2"])

    def test_xparse_optional_default_form_skipped_not_misexpanded(self):
        # vedamantra-book's \newcommand{\anuvakamend}[1][]{...} -- out of
        # scope (no corpus file needing it has this form with a *second*
        # bracket); left unexpanded rather than corrupted.
        text = r"\newcommand{\foo}[1][]{ignored #1}" + "\n" + r"\sect{t}" + "\n" + r"\foo{X}" + "\n"
        body, _ = strip_comments_and_extract_meta(text)
        body = expand_local_macros(body, "t")
        self.assertIn(r"\foo", body)


class TestLetAliasing(unittest.TestCase):
    def test_new_alias_name_behaves_as_its_target(self):
        # \let\head\chapt: \head should act like a heading.
        text = r"""\let\head\chapt
\head{title}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        self.assertEqual(blocks[0]["type"], "heading")
        self.assertEqual(blocks[0]["text"], "title")

    def test_let_is_noop_between_already_synonymous_macros(self):
        text = r"""\let\chapt\sect
\chapt{title}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        self.assertEqual(blocks[0]["type"], "heading")

    def test_let_reverts_after_endgroup(self):
        # \let\sect\dnsub inside its own \begingroup/\endgroup should not
        # leak out: \sect used afterward is still a real heading.
        text = r"""\begingroup
\let\sect\dnsub
\sect{inner}
\endgroup
\sect{outer}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        types_and_text = [(b["type"], b["text"]) for b in blocks]
        self.assertIn(("subheading", "inner"), types_and_text)
        self.assertIn(("heading", "outer"), types_and_text)


class TestBareCommandArg(unittest.TestCase):
    def test_setlength_accepts_bare_control_sequence_first_arg(self):
        # \setlength\columnsep{0pt} -- \columnsep needs no braces since it's
        # already one token; this must not raise.
        text = r"""\setlength\columnsep{0pt}
\sect{t}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        self.assertEqual(blocks[0]["type"], "heading")


class TestChapterPartAliasing(unittest.TestCase):
    def test_chapter_and_part_are_headings(self):
        text = r"""\part{आदिपर्व}
\chapter{अध्यायः १}
verse text
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        self.assertEqual([b["type"] for b in blocks[:2]], ["heading", "heading"])
        self.assertEqual(blocks[0]["text"], "आदिपर्व")
        self.assertEqual(blocks[1]["text"], "अध्यायः १")


class TestAdhyatmaRamayanamColophons(unittest.TestCase):
    def test_itibala_renders_fixed_colophon_and_closes_subsection(self):
        blocks = parse_blocks(r"\itibala{बालकाण्डे}{प्रथमः}", "t", lambda msg: None)
        self.assertEqual(blocks[0]["type"], "pushpika")
        self.assertIn("बालकाण्डे", blocks[0]["text"])
        self.assertIn("प्रथमः", blocks[0]["text"])
        self.assertEqual(blocks[1], {"type": "decoration", "style": "closesub"})

    def test_itikanda_renders_text_and_closes_section(self):
        blocks = parse_blocks(r"\itikanda{इति बालकाण्डः समाप्तः॥}", "t", lambda msg: None)
        self.assertEqual(blocks[0], {"type": "pushpika", "text": "इति बालकाण्डः समाप्तः॥"})
        self.assertEqual(blocks[1], {"type": "decoration", "style": "closesection"})


class TestRefstepcounter(unittest.TestCase):
    def test_shlokacount_manual_bump_affects_next_verse_number(self):
        text = r"""\sect{t}
\refstepcounter{shlokacount}
\onelineshloka{a}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        verse = next(b for b in blocks if b["type"] == "verse-1")
        self.assertEqual(verse["verse_number"], 2)

    def test_other_counter_names_are_silently_dropped(self):
        blocks = parse_blocks(r"\sect{t}\refstepcounter{sargacount}", "t", lambda msg: None)
        self.assertEqual([b["type"] for b in blocks], ["heading"])


class TestIfboolAndInput(unittest.TestCase):
    def test_ifbool_katha_true_branch_unresolvable_input_still_drops_silently(self):
        # katha=true now, but the referenced file doesn't exist here --
        # \input itself still silently drops in that case.
        text = r"""\sect{t}
before \ifbool{katha}{\input{kathas/some-katha.tex}}{} after
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["text"], "before after")

    def test_ifbool_unknown_bool_name_dropped_entirely(self):
        text = r"""\sect{t}
before \ifbool{somethingelse}{X}{Y} after
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["text"], "before after")

    def test_ifbool_veda_uses_false_branch(self):
        text = r"\ifbool{veda}{\sect{vedic}}{\sect{regular}}"
        blocks = parse_blocks(text, "t", lambda msg: None)
        self.assertEqual([b["text"] for b in blocks if b["type"] == "heading"], ["regular"])

    def test_bare_input_unresolvable_dropped(self):
        text = r"""\sect{t}
before \input{purvanga/ghanta-puja.tex} after
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["text"], "before after")

    def test_cross_repo_input_left_unresolved(self):
        text = r"before \input{../namavali-manjari/100/Ganga_108.tex} after"
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["text"], "before after")

    def test_same_repo_input_resolves_and_splices_real_content(self):
        # A same-repo, relative-to-repo-root \input{} (this corpus's own
        # convention, e.g. pujas.tex's \input{pujas/foo} and
        # shivaratri-puja.tex's own \input{pujas/shivaratri-yama-1-puja})
        # should read the target and splice it in for real parsing --
        # a nested \sect must show up as a real heading, not literal text.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pujas").mkdir()
            (Path(tmp) / "pujas" / "child.tex").write_text(r"\dnsub{नेस्टेड-अनुभागः}" + "\n", encoding="utf-8")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                text = r"\sect{parent}" + "\n" + r"\input{pujas/child}" + "\n"
                blocks = parse_blocks(text, "t", lambda msg: None)
            finally:
                os.chdir(cwd)
        self.assertEqual(
            [(b["type"], b["text"]) for b in blocks],
            [("heading", "parent"), ("subheading", "नेस्टेड-अनुभागः")],
        )

    def test_ifbool_katha_splices_resolvable_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "kathas").mkdir()
            (Path(tmp) / "kathas" / "some-katha.tex").write_text(r"\dnsub{कथा}" + "\n", encoding="utf-8")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                text = r"\sect{t}" + "\n" + r"\ifbool{katha}{\input{kathas/some-katha}}{}" + "\n"
                blocks = parse_blocks(text, "t", lambda msg: None)
            finally:
                os.chdir(cwd)
        self.assertEqual([b["type"] for b in blocks], ["heading", "subheading"])
        self.assertEqual(blocks[1]["text"], "कथा")


class TestStandaloneDevanumber(unittest.TestCase):
    def test_inline_devanumber_becomes_deva_numeral_in_prose(self):
        text = r"""\sect{t}
गजाननाय~नमः\\
ज्ञानदीपाय~नमः\hfill\devanumber{10}\\
सुखनिधये~नमः\\
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][1], "ज्ञानदीपाय नमः१०")

    def test_devanumber_non_integer_raises(self):
        with self.assertRaises(ParseError):
            parse_blocks(r"\sect{t}\devanumber{x}", "t", lambda msg: None)


class TestRenewcommandTextMacros(unittest.TestCase):
    def test_local_renewcommand_overrides_default(self):
        text = r"""\sect{t}
\renewcommand{\devAya}{तुलसी-विष्णुभ्यां नमः,}
\devAya{} आसनं समर्पयामि।
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "तुलसी-विष्णुभ्यां नमः, आसनं समर्पयामि।")

    def test_position_aware_across_two_redefinitions(self):
        # A file that dedicates part of itself to one deity, then another,
        # must not have the second \renewcommand retroactively change text
        # already emitted before it.
        text = r"""\sect{t}
\renewcommand{\devAya}{A,}
\devAya{} first.
\renewcommand{\devAya}{B,}
\devAya{} second.
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "A, first.")
        self.assertEqual(prose["lines"][1], "B, second.")

    def test_unset_placeholder_defaults_to_preamble_value(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"\ayane{} test", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertIn("( )", prose["lines"][0])

    def test_protected_macro_name_not_overridable(self):
        text = r"""\renewcommand{\dnsub}{ignored}
\sect{t}
\dnsub{real subheading}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        self.assertEqual([b["type"] for b in blocks], ["heading", "subheading"])
        self.assertEqual(blocks[1]["text"], "real subheading")


class TestBlankSeeKshama(unittest.TestCase):
    def test_blank_renders_placeholder(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"\blank{} test", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertIn("( )", prose["lines"][0])

    def test_math_mode_circ_word_separator(self):
        # yajur-upakarma.tex's \sep macro expands (via expand_local_macros)
        # to \hspace{...}{\small$\circ$}\hspace{...} -- $ has no real math
        # support, just this one decorative symbol, so it's transparent and
        # \circ renders as a word-separator dot.
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"a $\circ$ b", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "a ॰ b")

    def test_see_dropped(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"before\see{app:x} after", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "before after")

    def test_kshama_with_name_splices_verse(self):
        blocks = parse_blocks(r"\kshama{रामाय}", "t", lambda msg: None)
        types = [b["type"] for b in blocks]
        self.assertIn("subheading", types)
        self.assertIn("verse-2", types)
        verse2 = next(b for b in blocks if b["type"] == "verse-2")
        self.assertIn("रामाय", verse2["lines"][1]["text"])

    def test_bare_kshama_tolerates_missing_argument(self):
        # Two shipped files invoke \kshama with no {name} at all -- must not
        # raise, and must leave the following \closesub to be processed
        # normally rather than swallowing it as the argument.
        blocks = parse_blocks(r"\kshama" + "\n" + r"\closesub", "t", lambda msg: None)
        self.assertIn("decoration", [b["type"] for b in blocks])


class TestSpliceMacros(unittest.TestCase):
    def test_shuklambaradharam_splices_a_real_verse(self):
        blocks = parse_blocks(r"\shuklambaradharam", "t", lambda msg: None)
        self.assertEqual(blocks[0]["type"], "verse-2")
        self.assertIn("शुक्लाम्बरधरं", blocks[0]["lines"][0]["text"])


class TestTables(unittest.TestCase):
    def test_simple_two_column_table(self):
        text = r"""\begin{tabular}{ll}
पादौ & पूजयामि\\
गुल्फौ & पूजयामि\\
\end{tabular}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        table = next(b for b in blocks if b["type"] == "table")
        self.assertEqual(table["rows"], [["पादौ", "पूजयामि"], ["गुल्फौ", "पूजयामि"]])

    def test_table_without_trailing_row_separator(self):
        text = r"""\begin{tabular}{ll}
a & b\\
c & d
\end{tabular}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        table = next(b for b in blocks if b["type"] == "table")
        self.assertEqual(table["rows"], [["a", "b"], ["c", "d"]])

    def test_bare_ampersand_outside_table_is_literal(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + "a & b", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "a & b")


class TestEnumerateItem(unittest.TestCase):
    def test_items_become_separate_lines(self):
        text = r"""\sect{t}
\begin{enumerate}
\item first
\item second
\end{enumerate}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"], ["first", "second"])


class TestNamedCounters(unittest.TestCase):
    def test_newcounter_refstepcounter_arabic_roundtrip(self):
        text = r"""\sect{t}
\newcounter{dik}
\refstepcounter{dik}
पूर्वस्यां नमः। \devanumber{\arabic{dik}}
\refstepcounter{dik}
दक्षिणस्यां नमः। \devanumber{\arabic{dik}}
"""
        # \refstepcounter flushes the current prose block (like \resetShloka
        # does), so the two sentences land in separate prose blocks.
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose_blocks = [b for b in blocks if b["type"] == "prose"]
        self.assertEqual(prose_blocks[0]["lines"][0], "पूर्वस्यां नमः। १")
        self.assertEqual(prose_blocks[1]["lines"][0], "दक्षिणस्यां नमः। २")

    def test_unregistered_named_counter_defaults_to_zero(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"\devanumber{\arabic{neverdeclared}}", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "०")

    def test_setcounter_shlokacount_from_named_counter_syncs_real_counter(self):
        # MahaNyasah.tex's \ssankalpaalign pattern: sync shlokacount to a
        # separately-tracked counter's value before a numbered verse.
        text = r"""\sect{t}
\newcounter{ssk}
\refstepcounter{ssk}
\refstepcounter{ssk}
\setcounter{shlokacount}{\value{ssk}}
\twolineshloka{A}{B}
"""
        # ssk is stepped to 2, shlokacount is synced to that 2, and then
        # \twolineshloka's own CounterModel.step() advances it to 3 (matching
        # the real macro: \setcounter{shlokacount}{\value{ssk}} happens
        # *before* the verse steps its own counter).
        blocks = parse_blocks(text, "t", lambda msg: None)
        verse = next(b for b in blocks if b["type"] == "verse-2")
        self.assertEqual(verse["verse_number"], 3)

    def test_setcounter_unknown_counter_dropped_without_crashing(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"\setcounter{page}{0} after", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "after")

    def test_addtocounter_named_counter_then_arabic(self):
        text = r"""\sect{t}
\newcounter{n}
\addtocounter{n}{5}
\devanumber{\arabic{n}}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], to_deva(5))


class TestRawDefSkipped(unittest.TestCase):
    def test_def_with_param_text_and_raw_tex_body_is_skipped(self):
        # surya-namaskara.tex: \def\vhrulefill#1{\leavevmode\leaders\hrule
        # \@height#1\hfill \kern\z@} -- \@height isn't a tokenizable command
        # name for this parser, so the whole definition must be skipped
        # rather than re-entering the main dispatch loop.
        text = r"""\sect{t}
\makeatletter
\def\vhrulefill#1{\leavevmode\leaders\hrule\@height#1\hfill \kern\z@}
\makeatother
after
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "after")


class TestIfboolIndividual(unittest.TestCase):
    def test_individual_true_branch_spliced_like_katha(self):
        text = r"\ifbool{individual}{\sect{shown}}{\sect{hidden}}"
        blocks = parse_blocks(text, "t", lambda msg: None)
        self.assertEqual([b["text"] for b in blocks if b["type"] == "heading"], ["shown"])


class TestTextMacroInsideCapturedArguments(unittest.TestCase):
    def test_devaname_inside_verse_line_is_substituted(self):
        # purvanga/kalasha-puja.tex: "आयान्तु \devaName{}पूजार्थं..." inside a
        # \twolineshloka{} argument -- captured as a raw substring by
        # read_braced_arg(), so it never reaches the main dispatch loop's
        # own text_macros splice and must be substituted in clean_line_text.
        text = r"""\sect{t}
\renewcommand{\devaName}{विष्णु}
\twolineshloka
{आयान्तु \devaName{}पूजार्थं दुरितक्षयकारकाः}
{द्वितीयं पादम्}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        verse = next(b for b in blocks if b["type"] == "verse-2")
        self.assertIn("आयान्तु विष्णुपूजार्थं दुरितक्षयकारकाः", verse["lines"][0]["text"])

    def test_devaname_inside_dnsub_label_is_substituted(self):
        text = r"""\sect{t}
\renewcommand{\devaName}{शिव}
\dnsub{\devaName{} ध्यानम्}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        subheading = next(b for b in blocks if b["type"] == "subheading")
        self.assertEqual(subheading["text"], "शिव ध्यानम्")


class TestVerseArgLeniency(unittest.TestCase):
    def test_stray_danda_between_args_skipped(self):
        text = r"""\sect{t}
\twolineshloka
{पद्यं प्रथमम्}।
{पद्यं द्वितीयम्}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        verse = next(b for b in blocks if b["type"] == "verse-2")
        self.assertEqual(verse["lines"][1]["text"], "पद्यं द्वितीयम्")

    def test_missing_second_arg_before_next_command_becomes_empty(self):
        # A macro missing an argument (e.g. one line of a couplet never
        # supplied) must not swallow the *next* command's name character by
        # character looking for a brace -- it should be treated as an empty
        # argument, leaving the next \twolineshloka intact for its own
        # dispatch.
        text = r"""\sect{t}
\twolineshloka
{only one line supplied}

\twolineshloka
{next verse first line}
{next verse second line}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        verses = [b for b in blocks if b["type"] == "verse-2"]
        self.assertEqual(len(verses), 2)
        self.assertEqual(verses[0]["lines"][1]["text"], "")
        self.assertEqual(verses[1]["lines"][0]["text"], "next verse first line")
        self.assertEqual(verses[1]["lines"][1]["text"], "next verse second line")


class TestMiscDroppedAndUnwrapped(unittest.TestCase):
    def test_underline_and_fbox_keep_content(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"\underline{a} \fbox{b}", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "a b")

    def test_parbox_keeps_content_drops_width_and_position(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"\parbox[t]{0.8\linewidth}{kept text}", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "kept text")

    def test_multicolumn_keeps_cell_content_in_table(self):
        text = r"""\sect{t}
\begin{tabular}{ll}
\multicolumn{2}{l}{spanning text} & tail \\
\end{tabular}
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        table = next(b for b in blocks if b["type"] == "table")
        self.assertEqual(table["rows"], [["spanning text", "tail"]])

    def test_lbrack_rbrack_become_brackets(self):
        blocks = parse_blocks(r"\sect{t}" + "\n" + r"\lbrack text\rbrack", "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["lines"][0], "[ text]")


if __name__ == "__main__":
    unittest.main()
