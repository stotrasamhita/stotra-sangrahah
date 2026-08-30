import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ir_to_hugo import (  # noqa: E402
    assign_weights,
    build_front_matter,
    group_columns,
    is_blank_verse,
    parse_pdf_variants,
    render_block,
    render_body,
    render_pdf_links,
    split_into_chapters,
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
    def test_single_heading_becomes_title_and_stays_in_body(self):
        ir = make_ir([{"type": "heading", "text": "Sole Heading"}, {"type": "prose", "lines": ["x"], "text": "x"}])
        title, blocks = transform_blocks(ir)
        self.assertEqual(title, "Sole Heading")
        heading_texts = [b["text"] for b in blocks if b["type"] == "heading"]
        self.assertEqual(heading_texts, ["Sole Heading"])  # not removed

    def test_multiple_headings_no_override_uses_first_heading(self):
        # mahabharatam/adhyatmaramayanam: many headings (one per chapter),
        # but the first one is reliably the whole file's own name (the
        # \part{parva}/\chapt{kanda} heading, verified against the real
        # corpus to always immediately precede the first chapter's heading
        # with nothing in between) -- used as the title without needing a
        # curated override for every single file.
        ir = make_ir(
            [{"type": "heading", "text": "First"}, {"type": "heading", "text": "Second"}],
            slug="test-slug",
        )
        title, blocks = transform_blocks(ir)
        self.assertEqual(title, "First")
        heading_texts = [b["text"] for b in blocks if b["type"] == "heading"]
        self.assertEqual(heading_texts, ["First", "Second"])  # both kept, neither consumed

    def test_no_heading_falls_back_to_wiki_title(self):
        ir = make_ir([{"type": "prose", "lines": ["x"], "text": "x"}], meta={"wiki_title": "Dhyanam"})
        title, _ = transform_blocks(ir)
        self.assertEqual(title, "Dhyanam")

    def test_no_heading_no_meta_falls_back_to_slug(self):
        ir = make_ir([{"type": "prose", "lines": ["x"], "text": "x"}], slug="foo-bar")
        title, _ = transform_blocks(ir)
        self.assertEqual(title, "Foo Bar")

    def test_multiple_headings_use_curated_override_not_the_first_one(self):
        # NityaShloka.tex: 11 \sect calls bundling independent, unrelated
        # verses -- none of which is "the" title (unlike mahabharatam/
        # adhyatmaramayanam's kandas/parvas, where the first heading really
        # is the file's own name). The bug this override fixes was
        # displaying the first one ("Chiranjivi Stotram") as the whole
        # file's title.
        ir = make_ir(
            [{"type": "heading", "text": "चिरञ्जीविस्तोत्रम्"}, {"type": "heading", "text": "पञ्चकन्यास्मरणम्"}],
            slug="nitya-shloka",
            category="dhyanam",
        )
        title, blocks = transform_blocks(ir)
        self.assertEqual(title, "नित्यश्लोकाः")

    def test_title_override_scoped_by_category_not_slug_alone(self):
        # gita's and adhyatmaramayanam's mahatmyam.tex both slugify to
        # "mahatmyam" but need different titles -- an override for one must
        # not leak into the other.
        ir = make_ir([{"type": "heading", "text": "अध्यात्मरामायणमाहात्म्यम्"}], slug="mahatmyam", category="kandas")
        title, _ = transform_blocks(ir)
        self.assertEqual(title, "अध्यात्मरामायणमाहात्म्यम्")

    def test_title_heading_stays_in_body(self):
        # The bug report: "Currently ... not displayed inside the page at
        # all" -- no heading should ever be removed from blocks[] now.
        ir = make_ir([{"type": "heading", "text": "Only Heading"}, {"type": "prose", "lines": ["x"]}])
        title, blocks = transform_blocks(ir)
        self.assertEqual(title, "Only Heading")
        heading_texts = [b["text"] for b in blocks if b["type"] == "heading"]
        self.assertEqual(heading_texts, ["Only Heading"])


class TestChapterSplitting(unittest.TestCase):
    def test_no_split_for_zero_or_one_heading(self):
        self.assertIsNone(split_into_chapters("T", [{"type": "prose", "lines": ["x"]}]))
        self.assertIsNone(split_into_chapters("T", [{"type": "heading", "text": "T"}, {"type": "prose", "lines": ["x"]}]))

    def test_book_level_heading_excluded_from_chapters(self):
        # adhyatmaramayanam kanda / mahabharatam parva shape: a book-level
        # heading (used as `title`) immediately followed by per-chapter
        # headings -- the book heading itself isn't "chapter 1".
        blocks = [
            {"type": "heading", "text": "बालकाण्डः"},
            {"type": "heading", "text": "प्रथमः सर्गः"},
            {"type": "prose", "lines": ["a"]},
            {"type": "heading", "text": "द्वितीयः सर्गः"},
            {"type": "prose", "lines": ["b"]},
        ]
        chapters = split_into_chapters("बालकाण्डः", blocks)
        self.assertEqual([t for t, _ in chapters], ["प्रथमः सर्गः", "द्वितीयः सर्गः"])
        self.assertEqual(len(chapters[0][1]), 2)  # its heading + the "a" prose block
        self.assertEqual(len(chapters[1][1]), 2)

    def test_no_book_level_heading_every_heading_is_a_chapter(self):
        # gita.tex shape: title comes from a curated override (never equal
        # to any heading text), every \chapt is itself a chapter.
        blocks = [
            {"type": "heading", "text": "प्रथमोऽध्यायः"},
            {"type": "prose", "lines": ["a"]},
            {"type": "heading", "text": "द्वितीयोऽध्यायः"},
            {"type": "prose", "lines": ["b"]},
        ]
        chapters = split_into_chapters("श्रीमद्भगवद्गीता", blocks)
        self.assertEqual([t for t, _ in chapters], ["प्रथमोऽध्यायः", "द्वितीयोऽध्यायः"])
        self.assertEqual(len(chapters[0][1]), 2)

    def test_last_chapter_runs_to_end_of_blocks(self):
        blocks = [
            {"type": "heading", "text": "A"},
            {"type": "heading", "text": "B"},
            {"type": "prose", "lines": ["x"]},
            {"type": "prose", "lines": ["y"]},
        ]
        chapters = split_into_chapters("Z", blocks)
        self.assertEqual(len(chapters[1][1]), 3)  # B's heading + both prose blocks


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

    def test_category_order_override_beats_alphabetical(self):
        # adhyatmaramayanam's kandas: story order, not alphabetical.
        entries = [
            ("kandas", {"slug": "yuddha-kanda"}),
            ("kandas", {"slug": "bala-kanda"}),
            ("kandas", {"slug": "aranya-kanda"}),
        ]
        assign_weights(entries)
        by_slug = {fm["slug"]: fm["weight"] for _, fm in entries}
        self.assertLess(by_slug["bala-kanda"], by_slug["aranya-kanda"])
        self.assertLess(by_slug["aranya-kanda"], by_slug["yuddha-kanda"])

    def test_category_order_override_unlisted_slug_sorts_last(self):
        entries = [("kandas", {"slug": "bala-kanda"}), ("kandas", {"slug": "not-in-the-list"})]
        assign_weights(entries)
        by_slug = {fm["slug"]: fm["weight"] for _, fm in entries}
        self.assertLess(by_slug["bala-kanda"], by_slug["not-in-the-list"])


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

    def test_simple_verse_types_get_justify_class(self):
        for t in ("verse-1", "verse-2", "verse-3", "verse-annotated-2"):
            block = {"type": t, "verse_number_deva": "१", "lines": [{"pada": None, "text": "a", "ending": "danda"}]}
            out = render_block(block)
            self.assertIn('class="verse-block verse-justify"', out, msg=t)

    def test_four_line_verse_types_do_not_get_justify_class(self):
        for t in ("verse-4-indented", "verse-4-plain", "verse-annotated-4"):
            block = {"type": t, "verse_number_deva": "१", "lines": [{"pada": None, "text": "a", "ending": "danda"}]}
            out = render_block(block)
            self.assertIn('class="verse-block"', out, msg=t)
            self.assertNotIn("verse-justify", out, msg=t)

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

    def test_table_renders_rows_and_cells(self):
        block = {"type": "table", "rows": [["a", "b & c"], ["d", "e"]]}
        out = render_block(block)
        self.assertEqual(out.count("<tr>"), 2)
        self.assertIn("<td>a</td><td>b &amp; c</td>", out)
        self.assertIn('class="stotra-table"', out)

    def test_render_body_has_no_blank_lines(self):
        blocks = [
            {"type": "subheading", "text": "X"},
            {"type": "prose", "lines": ["y"]},
        ]
        body = render_body(blocks)
        self.assertNotIn("\n\n", body)

    def test_render_body_prepends_stotra_type(self):
        body = render_body([{"type": "prose", "lines": ["x"]}], stotra_type="Ashtakam")
        self.assertIn('<div class="stotra-article"><p class="stotra-meta">Ashtakam</p>', body)

    def test_render_body_wraps_verse_content_in_stotra_article(self):
        # This is the class the script-switcher and CSS target; the theme's
        # own default template gives no other hook to select just the verse
        # content (as opposed to page chrome), so this script supplies it.
        body = render_body([{"type": "prose", "lines": ["x"]}])
        self.assertIn('<div class="stotra-article">', body)

    def test_pdf_links_excluded_from_stotra_article_wrapper(self):
        # PDF link labels ("A5 / print", "Kindle") are plain English, not
        # Devanagari verse text -- the script-switcher must not touch them.
        body = render_body([{"type": "prose", "lines": ["x"]}], source_file="stotras/hanuman/HanumanChalisa.tex")
        article_end = body.index("</div>") + len("</div>")
        self.assertNotIn("pdf-links", body[:article_end])
        self.assertIn("pdf-links", body[article_end:])


class TestPdfLinks(unittest.TestCase):
    def test_three_variants_linked_with_matching_path(self):
        out = render_pdf_links("stotras/hanuman/HanumanChalisa.tex")
        self.assertIn(
            'href="https://raw.githubusercontent.com/stotrasamhita/stotra-sangrahah/master/stotras-pdf/hanuman/HanumanChalisa.pdf"',
            out,
        )
        self.assertIn("stotras-kindle-pdf/hanuman/HanumanChalisa.pdf", out)
        self.assertIn("stotras-kindle-scribe-pdf/hanuman/HanumanChalisa.pdf", out)

    def test_appended_to_body_when_source_file_given(self):
        body = render_body([{"type": "prose", "lines": ["x"]}], source_file="stotras/hanuman/HanumanChalisa.tex")
        self.assertIn("pdf-links", body)

    def test_omitted_when_no_source_file(self):
        body = render_body([{"type": "prose", "lines": ["x"]}])
        self.assertNotIn("pdf-links", body)

    def test_other_repo_variants_and_strip_prefix(self):
        out = render_pdf_links(
            "100/Ganesha_108.tex",
            pdf_repo="stotrasamhita/namavali-manjari",
            pdf_variants=(("Kindle", "namavalis-kindle-pdf"),),
            strip_prefix="",
        )
        self.assertIn(
            'href="https://raw.githubusercontent.com/stotrasamhita/namavali-manjari/master/namavalis-kindle-pdf/100/Ganesha_108.pdf"',
            out,
        )
        self.assertNotIn("stotras-pdf", out)

    def test_empty_variants_yields_no_links(self):
        out = render_pdf_links("100/Ganesha_108.tex", pdf_variants=(), strip_prefix="")
        self.assertEqual(out, "")


class TestParsePdfVariants(unittest.TestCase):
    def test_parses_label_equals_dirname_pairs(self):
        self.assertEqual(
            parse_pdf_variants("A5 / print=namavalis-pdf,Kindle=namavalis-kindle-pdf"),
            (("A5 / print", "namavalis-pdf"), ("Kindle", "namavalis-kindle-pdf")),
        )

    def test_empty_string_yields_no_variants(self):
        self.assertEqual(parse_pdf_variants(""), ())

    def test_missing_equals_raises(self):
        with self.assertRaises(ValueError):
            parse_pdf_variants("just-a-label")


if __name__ == "__main__":
    unittest.main()
