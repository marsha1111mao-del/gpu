#!/usr/bin/env python3
"""Verify formatting-independent mutation contracts without compiling GPU code."""

import unittest

from gpu_c_source import c_fragment_spans, extract_c_function, replace_c_fragment


class CFragmentTests(unittest.TestCase):
    def test_formatted_guard(self):
        source = "if (owner != current)\n\treturn false;\n"
        self.assertEqual(
            replace_c_fragment(source, "owner!=current", "false"),
            "if (false)\n\treturn false;\n",
        )

    def test_comment_between_tokens(self):
        self.assertEqual(
            replace_c_fragment(
                "owner /* bound */ != current", "owner!=current", "false"
            ),
            "false",
        )

    def test_literal_contents_are_not_code(self):
        with self.assertRaises(ValueError):
            replace_c_fragment('log("owner != current");', "owner!=current", "false")

    def test_complete_literal_can_be_matched(self):
        self.assertEqual(
            replace_c_fragment('log("old");', '"old"', '"new"'), 'log("new");'
        )

    def test_identifier_prefix_is_not_a_match(self):
        with self.assertRaises(ValueError):
            replace_c_fragment("owner_id != current", "owner!=current", "false")

    def test_equivalent_spelling_is_still_ambiguous(self):
        with self.assertRaises(ValueError):
            replace_c_fragment(
                "owner!=current; owner != current;", "owner!=current", "false"
            )

    def test_explicit_multiple_sites(self):
        self.assertEqual(
            replace_c_fragment(
                "owner!=current; owner != current;",
                "owner!=current",
                "false",
                expected=2,
            ),
            "false; false;",
        )

    def test_comments_and_strings_do_not_hide_a_second_code_site(self):
        source = 'owner!=current; /* owner != current */ log("owner != current");'
        self.assertEqual(len(c_fragment_spans(source, "owner!=current")), 1)

    def test_operator_identity(self):
        with self.assertRaises(ValueError):
            replace_c_fragment("bits > > 8", "bits>>8", "0")

    def test_spliced_comment_does_not_become_code(self):
        with self.assertRaises(ValueError):
            replace_c_fragment(
                "// note \\\nowner!=current\nvalue=1;", "owner!=current", "false"
            )

    def test_spliced_identifier_keeps_original_replacement_offsets(self):
        self.assertEqual(
            replace_c_fragment("owner\\\n_id!=current;", "owner_id!=current", "false"),
            "false;",
        )

    def test_spliced_operator_and_literal(self):
        self.assertEqual(replace_c_fragment("bits >\\\n> 8;", "bits>>8", "0"), "0;")
        self.assertEqual(
            replace_c_fragment('log("owner \\\ncurrent");', '"owner current"', '"new"'),
            'log("new");',
        )

    def test_missing_and_empty_sites_reject(self):
        for fragment in ("missing", "", "/* comment */"):
            with self.subTest(fragment=fragment), self.assertRaises(ValueError):
                replace_c_fragment("return value;", fragment, "false")

    def test_overlapping_sites_reject(self):
        with self.assertRaises(ValueError):
            replace_c_fragment("a+a+a", "a+a", "0", expected=2)

    def test_replacement_keeps_existing_first_line_indentation(self):
        self.assertEqual(
            replace_c_fragment("\treturn value;", "return value;", "\treturn other;"),
            "\treturn other;",
        )

    def test_extract_wrapped_return_type_and_nested_braces(self):
        source = (
            'struct item *\ncreate(int x)\n{\n\tif (x) { log("}"); }\n\treturn 0;\n}\n'
        )
        self.assertEqual(extract_c_function(source, "create"), source)

    def test_extract_ignores_declaration_and_call(self):
        definition = "static int value(void)\n{ return 1; }\n"
        source = (
            "int value(void);\n" + definition + "int other(void)\n{ return value(); }\n"
        )
        self.assertEqual(extract_c_function(source, "value"), definition)

    def test_extract_rejects_missing_duplicate_and_unbalanced_definitions(self):
        for source in [
            "int value(void);",
            "int value(void) { return 1; }\nint value(void) { return 2; }",
            "int value(void) { return 1;",
        ]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                extract_c_function(source, "value")

    def test_preprocessor_and_zero_site_contracts_reject(self):
        with self.assertRaises(ValueError):
            replace_c_fragment(
                "#define CALL(x) x", "#define CALL(x)", "#define CALL (x)"
            )
        with self.assertRaises(ValueError):
            replace_c_fragment("return value;", "return value;", "", expected=0)


if __name__ == "__main__":
    unittest.main()
