import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from tex_to_ir import (  # noqa: E402
    CounterModel,
    ParseError,
    TexScanner,
    expand_local_macros,
    parse_blocks,
    strip_comments_and_extract_meta,
    to_deva,
)


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
