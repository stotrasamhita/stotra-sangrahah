import sys
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
    def test_ifbool_dropped_entirely(self):
        text = r"""\sect{t}
before \ifbool{katha}{\input{kathas/some-katha.tex}}{} after
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["text"], "before after")

    def test_bare_input_dropped(self):
        text = r"""\sect{t}
before \input{purvanga/ghanta-puja.tex} after
"""
        blocks = parse_blocks(text, "t", lambda msg: None)
        prose = next(b for b in blocks if b["type"] == "prose")
        self.assertEqual(prose["text"], "before after")


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


if __name__ == "__main__":
    unittest.main()
