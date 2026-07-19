from __future__ import annotations

from src.validation.c_syntax import validate_c_source


def test_c_syntax_accepts_function_and_ignores_comments_and_literals() -> None:
    source = r'''#include <stddef.h>

/* Braces in comments and strings must not affect lexical checks: "}". */
int sum_values(const int *values, size_t count) {
    int total = 0;
    for (size_t i = 0; i < count; ++i) total += values[i];
    return total;
}
'''

    assert validate_c_source(source) is None


def test_c_syntax_rejects_unbalanced_source_without_execution() -> None:
    source = "int main(void) { return does_not_run(1);\n"

    issue = validate_c_source(source)

    assert issue is not None
    assert issue.code == "code_syntax_invalid"


def test_c_syntax_rejects_balanced_but_uncompilable_statements() -> None:
    for source in (
        "int answer(void) { return 1 }",
        "int answer(void) { int value = ; return value; }",
    ):
        issue = validate_c_source(source)
        assert issue is not None
        assert issue.code == "code_syntax_invalid"


def test_c_syntax_rejects_python_and_prose() -> None:
    issue = validate_c_source("def solve(values):\n    return values\n")

    assert issue is not None
    assert issue.code == "code_syntax_invalid"


def test_c_syntax_accepts_pointer_return_and_rejects_unterminated_literal() -> None:
    assert validate_c_source(
        "const char *describe(int value) {\n"
        "    (void)value;\n"
        "    return \"ok\";\n"
        "}\n"
    ) is None

    issue = validate_c_source(
        "int main(void) {\n"
        "    const char *value = \"unterminated;\n"
        "    return value != 0;\n"
        "}\n"
    )
    assert issue is not None
    assert issue.code == "code_syntax_invalid"


def test_c_syntax_accepts_typedef_returns_and_c_identifiers() -> None:
    source = """\
typedef struct Node {
    int value;
} Node;

Node *create_node(int new) {
    Node *pass = 0;
    (void)new;
    return pass;
}
"""

    assert validate_c_source(source) is None


def test_c_syntax_accepts_common_c11_header_types_and_macro_aliases() -> None:
    source = """\
#include <stdalign.h>
#include <stdatomic.h>
#include <stdio.h>

static_assert(sizeof(int) >= 2, "int must be at least 16 bits");

int write_value(FILE *output) {
    alignas(16) atomic_int value = 1;
    return output != NULL ? value : 0;
}
"""

    assert validate_c_source(source) is None


def test_c_syntax_rejects_malformed_preprocessor_directives() -> None:
    for source in (
        "#include ???\nint answer(void) { return 1; }\n",
        "#if 1\nint answer(void) { return 1; }\n",
        "#endif\nint answer(void) { return 1; }\n",
    ):
        issue = validate_c_source(source)
        assert issue is not None
        assert issue.code == "code_syntax_invalid"


def test_c_syntax_rejects_malformed_conditional_directive_branches() -> None:
    for source in (
        "#if\nint answer(void) { return 1; }\n#endif\n",
        "#ifdef\nint answer(void) { return 1; }\n#endif\n",
        "#ifndef\nint answer(void) { return 1; }\n#endif\n",
        "#if 1\n#elif\nint answer(void) { return 1; }\n#endif\n",
        "#if 1\n#else unexpected\nint answer(void) { return 1; }\n#endif\n",
        "#if 1\nint answer(void) { return 1; }\n#endif unexpected\n",
        "#if 1\n#else\n#else\nint answer(void) { return 1; }\n#endif\n",
        "#if 1\n#else\n#elif 1\nint answer(void) { return 1; }\n#endif\n",
    ):
        issue = validate_c_source(source)
        assert issue is not None
        assert issue.code == "code_syntax_invalid"
