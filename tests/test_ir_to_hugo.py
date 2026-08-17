import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ir_to_hugo import (  # noqa: E402
    assign_weights,
    build_front_matter,
    group_columns,
    is_blank_verse,
    render_block,
    render_body,
    transform_blocks,
)


def make_ir(blocks, meta=None, columns_hint=None, slug="test-slug", category="test"):
    return {
        "source_file": f"stotras/{category}/Test.tex",
        "slug": slug,
        "category": category,
        "meta": meta or {},
        "columns_hint": columns_hint,
        "blocks": blocks,
    }


class TestCounterAdjustDropped(unittest.TestCase):
    def test_counter_adjust_removed(self):
        ir = make_ir(
            [
                {"type": "heading", "text": "T"},
                {"type": "counter-adjust", "op": "reset"},
                {"type": "verse-2", "lines": []},
            ]
        )
        _, blocks = transform_blocks(ir)
        types = [b["type"] for b in blocks]
        self.assertNotIn("counter-adjust", types)


class TestTitleExtraction(unittest.TestCase):
    def test_first_heading_becomes_title_rest_stay(self):
        ir = make_ir(
            [
                {"type": "heading", "text": "First"},
                {"type": "prose", "lines": ["x"], "text": "x"},
                {"type": "heading", "text": "Second"},
            ]
        )
        title, blocks = transform_blocks(ir)
        self.assertEqual(title, "First")
        heading_texts = [b["text"] for b in blocks if b["type"] == "heading"]
        self.assertEqual(heading_texts, ["Second"])

    def test_no_heading_falls_back_to_wiki_title(self):
        ir = make_ir([{"type": "prose", "lines": ["x"], "text": "x"}], meta={"wiki_title": "Dhyanam"})
        title, _ = transform_blocks(ir)
        self.assertEqual(title, "Dhyanam")

    def test_no_heading_no_meta_falls_back_to_slug(self):
        ir = make_ir([{"type": "prose", "lines": ["x"], "text": "x"}], slug="foo-bar")
        title, _ = transform_blocks(ir)
        self.assertEqual(title, "Foo Bar")


class TestBlankVerseFilter(unittest.TestCase):
    def test_empty_fourlineshloka_dropped(self):
        blank = {
            "type": "verse-4-plain",
            "lines": [{"pada": "odd", "text": "", "ending": "none"} for _ in range(4)],
        }
        self.assertTrue(is_blank_verse(blank))
        ir = make_ir([{"type": "heading", "text": "T"}, blank, {"type": "verse-2", "lines": [{"text": "real", "ending": "none", "pada": None}]}])
        _, blocks = transform_blocks(ir)
        types = [b["type"] for b in blocks]
        self.assertNotIn("verse-4-plain", types)

    def test_nonblank_fourlineplain_kept(self):
        nonblank = {
            "type": "verse-4-plain",
            "lines": [{"pada": "odd", "text": "real text", "ending": "none"}] + [{"pada": "even", "text": "", "ending": "none"}] * 3,
        }
        self.assertFalse(is_blank_verse(nonblank))


class TestColumnsGrouping(unittest.TestCase):
    def test_open_close_pair_grouped(self):
        blocks = [
            {"type": "heading", "text": "T"},
            {"type": "columns-open", "n": 2, "source": "multicols"},
            {"type": "verse-2", "lines": [{"text": "a"}]},
            {"type": "verse-2", "lines": [{"text": "b"}]},
            {"type": "columns-close"},
            {"type": "prose", "lines": ["after"], "text": "after"},
        ]
        grouped = group_columns(blocks)
        types = [b["type"] for b in grouped]
        self.assertEqual(types, ["heading", "columns", "prose"])
        self.assertEqual(grouped[1]["n"], 2)
        self.assertEqual(len(grouped[1]["blocks"]), 2)

    def test_unmatched_open_raises(self):
        with self.assertRaises(ValueError):
            group_columns([{"type": "columns-open", "n": 2}])

    def test_unmatched_close_raises(self):
        with self.assertRaises(ValueError):
            group_columns([{"type": "columns-close"}])


class TestTaxonomyAndMeta(unittest.TestCase):
    def test_multivalue_deity_split_into_list(self):
        ir = make_ir([{"type": "heading", "text": "T"}], meta={"deity": "Shiva, Shakti", "language": "Sanskrit"})
        title, _ = transform_blocks(ir)
        fm = build_front_matter(ir, title)
        self.assertEqual(fm["deity"], ["Shiva", "Shakti"])
        self.assertEqual(fm["language"], "Sanskrit")

    def test_single_value_deity_still_a_list(self):
        ir = make_ir([{"type": "heading", "text": "T"}], meta={"deity": "Hanuman"})
        title, _ = transform_blocks(ir)
        fm = build_front_matter(ir, title)
        self.assertEqual(fm["deity"], ["Hanuman"])

    def test_meta_type_renamed_to_avoid_hugo_reserved_key(self):
        ir = make_ir([{"type": "heading", "text": "T"}], meta={"type": "Ashtakam"})
        title, _ = transform_blocks(ir)
        fm = build_front_matter(ir, title)
        self.assertNotIn("type", fm)  # front matter no longer sets a routing "type" at all
        self.assertEqual(fm["stotra_type"], "Ashtakam")  # the stotra's own genre, preserved


class TestWeightAssignment(unittest.TestCase):
    def test_alphabetical_within_category_gaps_of_ten(self):
        entries = [
            ("cat", {"slug": "zeta"}),
            ("cat", {"slug": "alpha"}),
            ("cat", {"slug": "mid"}),
        ]
        assign_weights(entries)
        by_slug = {fm["slug"]: fm["weight"] for _, fm in entries}
        self.assertEqual(by_slug["alpha"], 10)
        self.assertEqual(by_slug["mid"], 20)
        self.assertEqual(by_slug["zeta"], 30)


class TestHtmlRendering(unittest.TestCase):
    def test_numbered_verse_ending(self):
        block = {
            "type": "verse-2",
            "verse_number_deva": "१",
            "lines": [
                {"pada": None, "text": "line one", "ending": "danda"},
                {"pada": None, "text": "line two", "ending": "double-danda-numbered"},
            ],
        }
        out = render_block(block)
        self.assertIn("line one।", out)
        self.assertIn("line two॥१॥", out)

    def test_starred_verse_no_number(self):
        block = {
            "type": "verse-2",
            "verse_number_deva": None,
            "lines": [
                {"pada": None, "text": "a", "ending": "danda"},
                {"pada": None, "text": "b", "ending": "double-danda"},
            ],
        }
        out = render_block(block)
        self.assertIn("a।", out)
        self.assertIn("b॥", out)
        self.assertNotIn("॥None॥", out)

    def test_pada_even_gets_class(self):
        block = {
            "type": "verse-4-indented",
            "verse_number_deva": "१",
            "lines": [
                {"pada": "odd", "text": "a", "ending": "none"},
                {"pada": "even", "text": "b", "ending": "danda"},
                {"pada": "odd", "text": "c", "ending": "none"},
                {"pada": "even", "text": "d", "ending": "double-danda-numbered"},
            ],
        }
        out = render_block(block)
        self.assertEqual(out.count('class="line pada-even"'), 2)
        self.assertEqual(out.count('class="line"'), 2)

    def test_citation_attached_to_last_line_only(self):
        block = {
            "type": "verse-annotated-2",
            "verse_number_deva": "१",
            "citation": "1-2-43",
            "lines": [
                {"pada": None, "text": "a", "ending": "danda"},
                {"pada": None, "text": "b", "ending": "double-danda-numbered"},
            ],
        }
        out = render_block(block)
        self.assertEqual(out.count("citation"), 1)
        self.assertIn('<span class="citation">1-2-43</span>', out)

    def test_html_escaping(self):
        block = {"type": "prose", "lines": ["x < y & z"]}
        out = render_block(block)
        self.assertIn("&lt; y &amp; z", out)
        self.assertNotIn("< y", out)

    def test_columns_wraps_nested_blocks_in_one_div(self):
        block = {
            "type": "columns",
            "n": 2,
            "blocks": [
                {"type": "prose", "lines": ["a"]},
                {"type": "prose", "lines": ["b"]},
            ],
        }
        out = render_block(block)
        self.assertEqual(out.count('class="verse-columns"'), 1)
        self.assertIn("column-count:2", out)

    def test_render_body_has_no_blank_lines(self):
        blocks = [
            {"type": "subheading", "text": "X"},
            {"type": "prose", "lines": ["y"]},
        ]
        body = render_body(blocks)
        self.assertNotIn("\n\n", body)

    def test_render_body_prepends_stotra_type(self):
        body = render_body([{"type": "prose", "lines": ["x"]}], stotra_type="Ashtakam")
        self.assertTrue(body.startswith('<p class="stotra-meta">Ashtakam</p>'))


if __name__ == "__main__":
    unittest.main()
