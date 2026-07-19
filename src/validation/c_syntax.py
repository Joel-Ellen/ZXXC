"""Bounded, non-executing syntax checks for learner-facing C examples."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pycparser import c_ast, c_parser
from pycparser.c_parser import ParseError


MAX_C_SOURCE_BYTES = 16 * 1024
MAX_C_SOURCE_LINES = 600

NON_EXECUTABLE_FENCE_LANGUAGES = frozenset({
    "csv",
    "diff",
    "json",
    "latex",
    "markdown",
    "math",
    "md",
    "mermaid",
    "output",
    "plain",
    "plaintext",
    "text",
    "xml",
    "yaml",
    "yml",
})
_CODE_FENCE_RE = re.compile(r"```([^\n`]*)\r?\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class CSyntaxIssue:
    code: str
    message: str


_COMMON_TYPEDEFS = """\
typedef unsigned long size_t;
typedef long ptrdiff_t;
typedef int wchar_t;
typedef long double max_align_t;
typedef _Bool bool;
typedef signed char int8_t;
typedef unsigned char uint8_t;
typedef short int16_t;
typedef unsigned short uint16_t;
typedef int int32_t;
typedef unsigned int uint32_t;
typedef long long int64_t;
typedef unsigned long long uint64_t;
typedef struct __eduagent_FILE FILE;
typedef void *va_list;
typedef _Atomic _Bool atomic_bool;
typedef _Atomic int atomic_int;
typedef _Atomic unsigned int atomic_uint;
typedef _Atomic long atomic_long;
typedef _Atomic unsigned long atomic_ulong;
"""

_STANDARD_MACRO_ALIASES = {
    "alignas": "_Alignas",
    "alignof": "_Alignof",
    "static_assert": "_Static_assert",
    "thread_local": "_Thread_local",
}

_KNOWN_PREPROCESSOR_DIRECTIVES = {
    "define",
    "elif",
    "else",
    "endif",
    "error",
    "if",
    "ifdef",
    "ifndef",
    "ident",
    "import",
    "include",
    "include_next",
    "line",
    "pragma",
    "undef",
    "warning",
}


def _preprocessor_issue(source: str) -> str | None:
    """Validate the small preprocessor subset used by generated C11 code."""
    logical_lines: list[str] = []
    current: list[str] = []
    in_directive = False
    for line in source.splitlines(keepends=True):
        stripped = line.lstrip()
        if not in_directive:
            if not stripped.startswith("#"):
                continue
            in_directive = True
        current.append(line)
        if not line.rstrip("\r\n").rstrip().endswith("\\"):
            logical_lines.append("".join(current))
            current = []
            in_directive = False
    if in_directive:
        return "Generated C source has an unterminated preprocessor directive."

    # Track whether each open conditional has already consumed an ``#else``.
    # This catches malformed branches without trying to evaluate expressions.
    conditional_frames: list[bool] = []
    for logical_line in logical_lines:
        compact = re.sub(r"\\\r?\n", " ", logical_line)
        match = re.match(r"\s*#\s*([A-Za-z_][A-Za-z0-9_]*)(.*)", compact, re.DOTALL)
        if not match:
            return "Generated C source contains a malformed preprocessor directive."
        directive = match.group(1).lower()
        argument = match.group(2).strip()
        if directive not in _KNOWN_PREPROCESSOR_DIRECTIVES:
            return f"Generated C source uses unsupported preprocessor directive: {directive}."
        if directive in {"include", "include_next", "import"} and not re.fullmatch(
            r"(?:<[^<>\r\n]+>|\"[^\"\r\n]+\")", argument
        ):
            return "Generated C source contains an invalid include directive."
        if directive in {"define", "undef"} and not re.match(
            r"[A-Za-z_][A-Za-z0-9_]*(?:\([^\r\n]*\))?(?:\s|$)", argument
        ):
            return "Generated C source contains an invalid macro directive."
        if directive == "if":
            if not argument:
                return "Generated C source contains an empty #if expression."
            conditional_frames.append(False)
        elif directive in {"ifdef", "ifndef"}:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", argument):
                return "Generated C source contains an invalid conditional identifier."
            conditional_frames.append(False)
        elif directive == "elif":
            if not conditional_frames:
                return "Generated C source contains an unmatched conditional directive."
            if conditional_frames[-1]:
                return "Generated C source contains #elif after #else."
            if not argument:
                return "Generated C source contains an empty #elif expression."
        elif directive == "else":
            if not conditional_frames:
                return "Generated C source contains an unmatched conditional directive."
            if argument:
                return "Generated C source contains arguments after #else."
            if conditional_frames[-1]:
                return "Generated C source contains duplicate #else directives."
            conditional_frames[-1] = True
        elif directive == "endif":
            if argument:
                return "Generated C source contains arguments after #endif."
            if not conditional_frames:
                return "Generated C source contains an unmatched #endif."
            conditional_frames.pop()
    if conditional_frames:
        return "Generated C source contains an unterminated conditional directive."
    return None


def _strip_comments(source: str) -> tuple[str, bool]:
    """Remove comments while preserving literals, offsets, and line breaks."""
    output: list[str] = []
    index = 0
    state = "code"
    quote = ""
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and next_char == "/":
                output.extend((" ", " "))
                index += 2
                state = "line_comment"
                continue
            if char == "/" and next_char == "*":
                output.extend((" ", " "))
                index += 2
                state = "block_comment"
                continue
            if char in {"'", '"'}:
                quote = char
                output.append(char)
                index += 1
                state = "literal"
                continue
            output.append(char)
            index += 1
            continue
        if state == "line_comment":
            if char in "\r\n":
                output.append(char)
                state = "code"
            else:
                output.append(" ")
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and next_char == "/":
                output.extend((" ", " "))
                index += 2
                state = "code"
            else:
                output.append(char if char in "\r\n" else " ")
                index += 1
            continue
        # Escape sequences keep a quote from closing a literal.
        if char == "\\":
            output.append(char)
            if index + 1 < len(source):
                output.append(source[index + 1])
                index += 2
            else:
                index += 1
            continue
        if char == quote:
            output.append(char)
            index += 1
            state = "code"
            continue
        output.append(char)
        index += 1
    terminated = state in {"code", "line_comment"}
    return "".join(output), terminated


def _strip_preprocessor_directives(source: str) -> str:
    """Blank preprocessor directives; pycparser expects preprocessed input."""
    output: list[str] = []
    in_directive = False
    for line in source.splitlines(keepends=True):
        if not in_directive and line.lstrip().startswith("#"):
            in_directive = True
        if in_directive:
            output.append("".join(char if char in "\r\n" else " " for char in line))
            in_directive = line.rstrip("\r\n").rstrip().endswith("\\")
        else:
            output.append(line)
    return "".join(output)


def _expand_standard_macro_aliases(source: str) -> str:
    """Expand identifier-like C11 convenience macros for parser input only."""
    for alias, keyword in _STANDARD_MACRO_ALIASES.items():
        source = re.sub(rf"\b{alias}\b", keyword, source)
    return source


def validate_c_source(source: str) -> CSyntaxIssue | None:
    """Return one bounded syntax issue, or ``None`` when lexical checks pass."""
    if not isinstance(source, str) or not source.strip():
        return CSyntaxIssue("code_syntax_invalid", "Generated C source is empty.")
    if "\x00" in source:
        return CSyntaxIssue("code_syntax_invalid", "Generated C source contains a NUL byte.")
    if len(source.encode("utf-8")) > MAX_C_SOURCE_BYTES:
        return CSyntaxIssue(
            "code_too_large",
            "Generated C source exceeds the local validation size limit.",
        )
    if source.count("\n") + 1 > MAX_C_SOURCE_LINES:
        return CSyntaxIssue(
            "code_too_many_lines",
            "Generated C source exceeds the local validation line limit.",
        )

    without_comments, terminated = _strip_comments(source)
    if not terminated:
        return CSyntaxIssue(
            "code_syntax_invalid",
            "Generated C source has an unterminated comment or literal.",
        )
    directive_issue = _preprocessor_issue(without_comments)
    if directive_issue:
        return CSyntaxIssue("code_syntax_invalid", directive_issue)

    parser_source = _COMMON_TYPEDEFS + _expand_standard_macro_aliases(
        _strip_preprocessor_directives(without_comments)
    )
    try:
        translation_unit = c_parser.CParser().parse(
            parser_source,
            filename="<generated-resource>",
        )
    except (ParseError, AssertionError, RuntimeError, RecursionError, ValueError, TypeError):
        return CSyntaxIssue(
            "code_syntax_invalid",
            "Generated C source does not parse as standard C.",
        )

    if not any(isinstance(node, c_ast.FuncDef) for node in translation_unit.ext):
        return CSyntaxIssue(
            "code_syntax_invalid",
            "Generated C source must contain at least one function definition.",
        )
    return None


def is_c_learner_resource(
    content: object,
    *,
    card_type: str = "",
    structured_payload: object = None,
    require_structured_language: bool = False,
) -> bool:
    """Return whether learner-visible executable fences use valid C11.

    Non-executable fences such as Mermaid, JSON, and diagnostic ``text`` are
    allowed in explanatory cards. A ``code_snippet`` is stricter: its
    structured payload and every fenced block must explicitly declare C/C11
    and contain parseable source.
    """
    text = str(content or "")
    blocks = list(_CODE_FENCE_RE.finditer(text))
    if text.count("```") != len(blocks) * 2:
        return False

    payload = structured_payload if isinstance(structured_payload, dict) else {}
    has_payload = isinstance(structured_payload, dict)
    language = str(payload.get("language") or "").strip().lower()
    strict_code_card = str(card_type or "").strip() == "code_snippet"
    if strict_code_card and require_structured_language:
        if not has_payload or language not in {"c", "c11"}:
            return False
    elif strict_code_card and language and language not in {"c", "c11"}:
        return False

    structured_code = payload.get("code")
    if strict_code_card and structured_code is None and not blocks:
        return False
    if strict_code_card and structured_code is not None and validate_c_source(str(structured_code)) is not None:
        return False

    for block in blocks:
        block_language = block.group(1).strip().lower()
        if block_language in NON_EXECUTABLE_FENCE_LANGUAGES:
            if strict_code_card:
                return False
            continue
        if block_language not in {"c", "c11"}:
            return False
        if validate_c_source(block.group(2)) is not None:
            return False
    return True


__all__ = [
    "CSyntaxIssue",
    "MAX_C_SOURCE_BYTES",
    "MAX_C_SOURCE_LINES",
    "NON_EXECUTABLE_FENCE_LANGUAGES",
    "is_c_learner_resource",
    "validate_c_source",
]
