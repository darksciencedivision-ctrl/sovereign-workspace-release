#!/usr/bin/env python
"""Tests for innerhtml_sink_audit.py (SWS-REM-DIR-20260828 R2 B2-4)."""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import innerhtml_sink_audit as isa  # noqa: E402


class ExtractTests(unittest.TestCase):
    def test_finds_nested_templates(self):
        src = "el.innerHTML = `a ${x ? `b ${y}` : `c`} d`;"
        temps = isa.lex_templates(src)
        texts = [t[2] for t in temps]
        self.assertTrue(any("a ${" in t for t in texts))
        self.assertTrue(any(t == "`b ${y}`" for t in texts), texts)
        self.assertTrue(any(t == "`c`" for t in texts), texts)

    def test_quotes_inside_regex_do_not_derail(self):
        src = 'const e = (s) => String(s).replace(/[&<>"]/g, f); el.innerHTML = `${v}`;'
        temps = isa.lex_templates(src)
        self.assertEqual(len(temps), 1)
        self.assertEqual(isa.top_level_interpolations(temps[0][2]), ["v"])

    def test_string_with_backtick_not_template(self):
        src = 'const s = "not `a` template"; el.innerHTML = `${v}`;'
        temps = isa.lex_templates(src)
        self.assertEqual(len(temps), 1)

    def test_comment_with_backtick_ignored(self):
        src = '// note `not a template`\nel.innerHTML = `${v}`;'
        temps = isa.lex_templates(src)
        self.assertEqual(len(temps), 1)


class ClassifyTests(unittest.TestCase):
    def test_esc_wrapped(self):
        self.assertEqual(isa.classify("esc(x)"), "ESCAPED")
        self.assertEqual(isa.classify("  esc(a || b) "), "ESCAPED")

    def test_guaranteed(self):
        self.assertEqual(isa.classify("3"), "GUARANTEED")
        self.assertEqual(isa.classify("rows.length"), "GUARANTEED")

    def test_composite(self):
        self.assertEqual(isa.classify("a ? `x` : `y`"), "COMPOSITE")

    def test_other_needs_justification(self):
        self.assertEqual(isa.classify("op.summary.task_count"), "MUST-JUSTIFY")

    def test_esc_prefix_plus_raw_is_not_escaped(self):
        self.assertEqual(isa.classify("esc(a) + raw"), "MUST-JUSTIFY")

    def test_length_suffix_of_ternary_is_not_guaranteed(self):
        self.assertEqual(isa.classify("cond ? html : x.length"), "MUST-JUSTIFY")

    def test_escapeHtml_whole_call_is_escaped(self):
        self.assertEqual(isa.classify("escapeHtml(row.model)"), "ESCAPED")


class ScanTests(unittest.TestCase):
    def test_hazard_flagged_without_ledger(self):
        src = "el.innerHTML = `${model.supplied}`;"
        report = isa.scan(src, {})
        bad = [r for r in report["interpolations"] if r.get("unjustified")]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["expr"], "model.supplied")

    def test_ledger_entry_clears(self):
        src = "el.innerHTML = `${model.supplied}`;"
        ledger = {"justifications": {"model.supplied": {
            "class": "STATIC", "reason": "unit fixture"}}}
        report = isa.scan(src, ledger)
        self.assertFalse(any(r.get("unjustified")
                             for r in report["interpolations"]))

    def test_nested_builder_template_reaches_scope(self):
        # A builder's own nested template must be in scope through scope
        # closure when its parent template is in scope (renderer.js case:
        # taskCard is enumerated by fragment; its routed-count leaf is nested).
        src = ("const card = (t) => `outer-FRAG ${t.contextRouted ? `inner "
               "${t.contextRouted.count} entries` : `none`}`;\n"
               "el.innerHTML = `${x}`;")
        report = isa.scan(src, {"construction_fragments": ["outer-FRAG"]})
        exprs = [r["expr"] for r in report["interpolations"]]
        self.assertIn("t.contextRouted.count", exprs)
        self.assertTrue(any(r.get("unjustified")
                            and r["expr"] == "t.contextRouted.count"
                            for r in report["interpolations"]))

    def test_nested_leaf_scanned(self):
        src = "el.innerHTML = `${ok ? `safe` : `bad ${raw.thing}`}`;"
        report = isa.scan(src, {})
        exprs = [r["expr"] for r in report["interpolations"]]
        self.assertIn("raw.thing", exprs)
        self.assertTrue(any(r.get("unjustified") and r["expr"] == "raw.thing"
                            for r in report["interpolations"]))

    def test_compound_assignment_and_outerhtml_are_sinks(self):
        src = "el.innerHTML += `${rawA}`; node.outerHTML = `${rawB}`;"
        report = isa.scan(src, {})
        exprs = {r["expr"] for r in report["interpolations"]}
        self.assertEqual(exprs, {"rawA", "rawB"})

    def test_insertAdjacentHTML_is_a_sink(self):
        src = 'el.insertAdjacentHTML("beforeend", `${rawCall}`);'
        report = isa.scan(src, {})
        self.assertTrue(any(r.get("unjustified") and r["expr"] == "rawCall"
                            for r in report["interpolations"]))

    def test_document_write_is_a_sink(self):
        src = "document.write(`${rawWrite}`);"
        report = isa.scan(src, {})
        self.assertTrue(any(r.get("unjustified") and r["expr"] == "rawWrite"
                            for r in report["interpolations"]))

    def test_concatenation_rhs_templates_are_in_scope(self):
        src = 'el.innerHTML = prefix + `${rawConcat}` + suffix;'
        report = isa.scan(src, {})
        self.assertTrue(any(r.get("unjustified") and r["expr"] == "rawConcat"
                            for r in report["interpolations"]))

    def test_textContent_is_not_a_sink(self):
        src = "el.textContent = `${safe}`; el.innerHTML = `${raw}`;"
        report = isa.scan(src, {})
        exprs = {r["expr"] for r in report["interpolations"]}
        self.assertEqual(exprs, {"raw"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

