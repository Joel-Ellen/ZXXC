# -*- coding: utf-8 -*-
"""Language checks for learner-visible model output."""

from __future__ import annotations

import ast
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_FENCED_CODE_RE = re.compile(r"```([A-Za-z0-9_+.-]*)\s*\n?(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_URL_RE = re.compile(r"https?://\S+")
_BLOCK_MATH_RE = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$(?!\$).*?(?<!\\)\$|\\\(.*?\\\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MERMAID_QUOTED_LABEL_RE = re.compile(r'"([^"\n]+)"')
_MERMAID_PLAIN_LABEL_RE = re.compile(
    r"(?:[A-Za-z_][A-Za-z0-9_-]*)\s*[\[\(\{]([^\"\]\)\}\n]+)[\]\)\}]"
)
_MERMAID_EDGE_LABEL_RE = re.compile(r"\|([^|\n]+)\|")
_MERMAID_SUBGRAPH_RE = re.compile(r"^\s*subgraph\s+(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_MARKDOWN_PREFIX_RE = re.compile(r"^\s*(?:#{1,6}|[-*+]>|\d+\.)\s*")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z](?:[A-Za-z0-9_.+/#:-]*[A-Za-z0-9])?")
_TECHNICAL_TOKEN_RE = re.compile(
    r"^(?:[A-Z][A-Z0-9_.+/#:-]+|[A-Za-z]*[0-9_+./#:-][A-Za-z0-9_.+/#:-]*|"
    r"[a-z]+[A-Z][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*\(\))$"
)
_COMPACT_CALL_RE = re.compile(
    r"\b(?P<name>[A-Za-z_][A-Za-z0-9_.]*)\((?P<body>[^()\n]*)\)"
)
_INDEXED_IDENTIFIER_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:\s*\[[^\]\n]+\])+"
)
_CODE_BLOCK_SIGNAL_RE = re.compile(
    r"(?:"
    r"^\s*(?:#|//|/\*|\*|<!--|--\s)|"
    r"^\s*(?:from\s+\S+\s+import|import\s+\S+|def\s+\w+\s*\(|class\s+\w+|"
    r"if\s+.+:|elif\s+.+:|else\s*:|for\s+\w+\s+in\s+.+:|while\s+.+:|"
    r"try\s*:|except.*:|with\s+.+:|return(?:\s|$)|yield(?:\s|$)|raise(?:\s|$)|"
    r"pass\s*$|break\s*$|continue\s*$)|"
    r"^\s*(?:const|let|var|function|interface|type|public|private|protected)\b|"
    r"^\s*(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b|"
    r"^\s*(?:echo|printf|export|set)\b|"
    r"^\s*</?[A-Za-z][^>]*>|"
    r"^\s*[A-Za-z_][A-Za-z0-9_.\[\]]*\s*(?:=|:=|\+=|-=|\*=|/=)|"
    r"^\s*[A-Za-z_][A-Za-z0-9_.]*\s*\([^\n]*\)\s*;?\s*$|"
    r"=>|\{\s*$|;\s*$"
    r")",
    re.MULTILINE,
)
_NON_SIMPLIFIED_CJK_RE = re.compile(
    r"[學習語説說體驗課內標題圖書問應該輸為與這個關係讓從對於實開發處結總簡"
    r"読覚関発図処経応実広]"
)
_SUPPORTED_MERMAID_RE = re.compile(r"^(?:graph|flowchart)\b", re.IGNORECASE)
_MATH_WORDS = {
    "abs",
    "avg",
    "cos",
    "exp",
    "len",
    "log",
    "max",
    "min",
    "sin",
    "sqrt",
    "sum",
    "tan",
}
_STANDARD_ABBREVIATIONS = {
    "acid",
    "ai",
    "api",
    "ascii",
    "ast",
    "avl",
    "bfs",
    "cap",
    "cdn",
    "ci",
    "cjk",
    "cli",
    "cnn",
    "cpu",
    "crud",
    "css",
    "dag",
    "dbms",
    "dfs",
    "dns",
    "dom",
    "dp",
    "fifo",
    "gan",
    "gpu",
    "grpc",
    "html",
    "http",
    "https",
    "ide",
    "json",
    "jwt",
    "kmp",
    "lifo",
    "llm",
    "lstm",
    "mst",
    "mvc",
    "mvvm",
    "nli",
    "nlp",
    "nosql",
    "oauth",
    "oop",
    "orm",
    "rest",
    "rnn",
    "rpc",
    "sdk",
    "sql",
    "ssl",
    "sse",
    "svm",
    "tcp",
    "tls",
    "udp",
    "ui",
    "uri",
    "url",
    "utf",
    "utf8",
    "uuid",
    "ux",
}
_TRANSLATABLE_UPPERCASE_WORDS = {
    "algorithm",
    "answer",
    "cache",
    "database",
    "end",
    "english",
    "example",
    "execution",
    "explanation",
    "function",
    "graph",
    "input",
    "list",
    "model",
    "output",
    "process",
    "query",
    "question",
    "queue",
    "result",
    "stack",
    "start",
    "summary",
    "tree",
}
_UPPERCASE_PROSE_SEPARATOR_RE = re.compile(r"[\s,.;:/|&()\[\]{}]+")
_PROGRAMMING_FENCE_LANGUAGES = {
    "bash",
    "c",
    "cpp",
    "css",
    "go",
    "html",
    "java",
    "javascript",
    "js",
    "json",
    "jsx",
    "kotlin",
    "python",
    "py",
    "rust",
    "shell",
    "sql",
    "swift",
    "ts",
    "tsx",
    "typescript",
    "vue",
    "xml",
    "yaml",
}
_TECHNICAL_WORDS = {
    "api",
    "http",
    "https",
    "json",
    "linux",
    "numpy",
    "python",
    "pytorch",
    "sql",
    "tcp",
    "udp",
}
_ENGLISH_PROSE_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "because",
    "can",
    "could",
    "does",
    "entirely",
    "english",
    "explanation",
    "explains",
    "for",
    "from",
    "into",
    "is",
    "means",
    "must",
    "provides",
    "requires",
    "returns",
    "should",
    "stores",
    "students",
    "supports",
    "that",
    "the",
    "these",
    "this",
    "those",
    "uses",
    "was",
    "were",
    "when",
    "while",
    "will",
    "with",
    "would",
}
_GENERIC_ENGLISH_MERMAID_LABELS = {
    "answer",
    "concept",
    "end",
    "english",
    "example",
    "false",
    "input",
    "key",
    "next",
    "no",
    "output",
    "question",
    "result",
    "section",
    "start",
    "step",
    "true",
    "yes",
}
_GENERIC_ENGLISH_HEADING_WORDS = {
    "common",
    "description",
    "detail",
    "details",
    "english",
    "explanation",
    "introduction",
    "overview",
    "pitfall",
    "pitfalls",
    "summary",
}
_ALLOWED_PROPER_NAME_WORDS = {
    "api",
    "bayes",
    "bellman",
    "bezier",
    "code",
    "curve",
    "dataset",
    "deepseek",
    "descartes",
    "dijkstra",
    "docker",
    "elasticsearch",
    "floyd",
    "ford",
    "git",
    "github",
    "godel",
    "java",
    "javascript",
    "kubernetes",
    "kruskal",
    "langchain",
    "langgraph",
    "linux",
    "milvus",
    "mysql",
    "node",
    "numpy",
    "openai",
    "pinia",
    "postgresql",
    "prim",
    "pydantic",
    "python",
    "pytorch",
    "qwen",
    "react",
    "redis",
    "rene",
    "scikit",
    "spark",
    "studio",
    "tensorflow",
    "transformer",
    "typescript",
    "vue",
    "visual",
    "warshall",
}

_RESOURCE_IGNORED_FIELDS = {
    "answer_index",
    "code",
    "content_language",
    "critical",
    "difficulty",
    "duration_minutes",
    "evidence_ids",
    "evidence_map",
    "error_signature",
    "example_binding",
    "id",
    "language",
    "level",
    "media_status",
    "objective_ids",
    "pass_threshold",
    "points",
    "practice_id",
    "quality_profile",
    "render_type",
    "source_ref_ids",
    "verification",
    "version",
    "video_source_id",
    "video_url",
}
_RESOURCE_NAME_FIELDS = {"heading", "label", "name", "terms", "title"}
_RESOURCE_CODE_VALUE_FIELDS = {"expected", "input"}

TUTOR_LEARNER_TEXT_FIELDS = frozenset({
    "analogy",
    "best_practices",
    "cheat_sheet",
    "common_exam_traps",
    "common_misconceptions",
    "code_example",
    "core_definition",
    "detailed_explanation",
    "error_analysis",
    "extension_questions",
    "fix_guidance",
    "follow_up_questions",
    "hints",
    "key_topics",
    "learning_tip",
    "practice_questions",
    "response",
    "review_strategy",
    "root_cause",
    "solution_approach",
    "text_explanation",
})


def _looks_like_identifier(value: str) -> bool:
    return bool(
        len(value) == 1
        or value.islower()
        or _TECHNICAL_TOKEN_RE.fullmatch(value)
        or re.search(r"[a-z][A-Z]", value)
    )


def _is_technical_token(value: str) -> bool:
    if not value:
        return False
    if value.isalpha() and value.isupper():
        return len(value) == 1 or value.casefold() in _STANDARD_ABBREVIATIONS
    return bool(
        _TECHNICAL_TOKEN_RE.fullmatch(value)
        or re.search(r"[a-z][A-Z]", value)
    )


def _fold_latin_diacritics(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _looks_like_code_block(body: str) -> bool:
    stripped = body.strip()
    if not stripped:
        return False
    return bool(
        _CODE_BLOCK_SIGNAL_RE.search(stripped)
        or re.fullmatch(r"[\[{].*[\]}]", stripped, re.DOTALL)
    )


def _looks_like_inline_code(body: str) -> bool:
    stripped = body.strip()
    if not stripped or "\n" in stripped:
        return False
    if (
        len(stripped) == 1
        or _TECHNICAL_TOKEN_RE.fullmatch(stripped)
        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stripped)
    ):
        return True
    call = _COMPACT_CALL_RE.fullmatch(stripped)
    if call and _looks_like_identifier(call.group("name")):
        return True
    return _looks_like_code_block(stripped) or _is_formula_or_symbol_expression(stripped)


def _looks_like_fenced_code(language: str, body: str) -> bool:
    if language in {"python", "py"}:
        try:
            parsed = ast.parse(body, filename="<learner-code>", mode="exec")
        except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
            return False
        return bool(parsed.body or re.search(r"^\s*#", body, re.MULTILINE))
    if language == "yaml":
        return bool(re.search(
            r"^\s*[A-Za-z_][A-Za-z0-9_.-]*\s*:\s*\S+",
            body,
            re.MULTILINE,
        ))
    return _looks_like_code_block(body)


def _strip_indented_code(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    found = False
    index = 0
    while index < len(lines):
        if not (lines[index].startswith("    ") or lines[index].startswith("\t")):
            output.append(lines[index])
            index += 1
            continue
        start = index
        block: list[str] = []
        while index < len(lines) and (
            lines[index].startswith("    ")
            or lines[index].startswith("\t")
            or not lines[index].strip()
        ):
            line = lines[index]
            block.append(line[4:] if line.startswith("    ") else line[1:] if line.startswith("\t") else line)
            index += 1
        if _looks_like_code_block("".join(block)):
            output.append("\n")
            found = True
        else:
            output.extend(lines[start:index])
    return "".join(output), found


def _strip_exempt_content(text: str) -> tuple[str, bool]:
    found_exemption = False

    def replace_fence(match: re.Match[str]) -> str:
        nonlocal found_exemption
        language = match.group(1).casefold()
        body = match.group(2)
        if language == "mermaid":
            if is_chinese_mermaid_text(body):
                found_exemption = True
                return " "
            return f"\n{body}\n"
        if (
            (language in _PROGRAMMING_FENCE_LANGUAGES or not language)
            and _looks_like_fenced_code(language, body)
        ):
            found_exemption = True
            return " "
        return f"\n{body}\n"

    def replace_inline(match: re.Match[str]) -> str:
        nonlocal found_exemption
        body = match.group(1).strip()
        if _looks_like_inline_code(body):
            found_exemption = True
            return " "
        return body

    def replace_indexed(match: re.Match[str]) -> str:
        nonlocal found_exemption
        name = match.group(0).split("[", 1)[0].strip()
        if _looks_like_identifier(name):
            found_exemption = True
            return " "
        return match.group(0)

    def replace_call(match: re.Match[str]) -> str:
        nonlocal found_exemption
        name = match.group("name")
        body = match.group("body")
        if _looks_like_identifier(name) and (
            name.islower()
            or not re.search(r"\s", body)
            or name.casefold() in _MATH_WORDS
        ):
            found_exemption = True
            return " "
        return match.group(0)

    prose = _FENCED_CODE_RE.sub(replace_fence, text)
    prose, found_indented = _strip_indented_code(prose)
    found_exemption = found_exemption or found_indented
    prose = _INLINE_CODE_RE.sub(replace_inline, prose)
    patterns = (_BLOCK_MATH_RE, _INLINE_MATH_RE, _URL_RE)
    for pattern in patterns:
        found_exemption = found_exemption or bool(pattern.search(prose))
        prose = pattern.sub(" ", prose)
    prose = _INDEXED_IDENTIFIER_RE.sub(replace_indexed, prose)
    for _ in range(4):
        next_prose = _COMPACT_CALL_RE.sub(replace_call, prose)
        if next_prose == prose:
            break
        prose = next_prose
    return _HTML_TAG_RE.sub(" ", prose), found_exemption


def _is_technical_or_name_fragment(text: str, *, allow_name_only: bool) -> bool:
    fragment = text.strip().strip("()[]{}<>，、")
    if not fragment or len(fragment) > 100 or re.search(r"[.!?;。！？；]$", fragment):
        return False
    if len(fragment) == 1 or _is_technical_token(fragment):
        return True
    words = _LATIN_WORD_RE.findall(_fold_latin_diacritics(fragment))
    if not words or len(words) > 8:
        return False
    lowered_words = {word.casefold() for word in words}
    if lowered_words.intersection(_GENERIC_ENGLISH_HEADING_WORDS):
        return False
    if len(lowered_words.intersection(_ENGLISH_PROSE_WORDS)) >= 2:
        return False
    if allow_name_only:
        if all(
            word.casefold() in _ALLOWED_PROPER_NAME_WORDS
            or word.casefold() in {"and", "of", "the"}
            for word in words
        ):
            return True
    if all(
        _is_technical_token(word)
        or word.casefold() in _TECHNICAL_WORDS
        for word in words
    ):
        return True
    return all(word.casefold() in _ALLOWED_PROPER_NAME_WORDS for word in words)


def _is_formula_or_symbol_expression(text: str) -> bool:
    fragment = _fold_latin_diacritics(text.strip())
    if not re.search(r"[=+*^<>\[\]()]|<=|>=|!=|->", fragment):
        return False
    if re.search(r"[^A-Za-z0-9\s_=+*/^<>\[\](){},.:'\"\\-]", fragment):
        return False
    for token in _LATIN_TOKEN_RE.findall(fragment):
        folded = token.casefold()
        if (
            len(token) == 1
            or folded in _MATH_WORDS
            or folded in _TECHNICAL_WORDS
            or _is_technical_token(token)
        ):
            continue
        return False
    return True


def _contains_other_natural_language_script(text: str) -> bool:
    for char in text:
        if not unicodedata.category(char).startswith("L"):
            continue
        if _CJK_RE.fullmatch(char) or _LATIN_RE.fullmatch(char):
            continue
        unicode_name = unicodedata.name(char, "")
        if "LATIN" in unicode_name or "GREEK" in unicode_name:
            continue
        return True
    greek_runs = re.findall(r"[\u0370-\u03ff\u1f00-\u1fff]+", text)
    return any(len(run) > 1 for run in greek_runs)


def _is_contextual_abbreviation(token: str, text: str) -> bool:
    folded = token.casefold()
    return bool(
        token.isalpha()
        and token.isupper()
        and 2 <= len(token) <= 5
        and _CJK_RE.search(text)
        and folded not in _STANDARD_ABBREVIATIONS
        and folded not in _ENGLISH_PROSE_WORDS
        and folded not in _TRANSLATABLE_UPPERCASE_WORDS
    )


def _latin_token_is_allowed(text: str, match: re.Match[str]) -> bool:
    token = match.group(0)
    folded = token.casefold()
    contextual_abbreviation = _is_contextual_abbreviation(token, text)
    if (
        len(token) == 1
        or contextual_abbreviation
        or folded in _MATH_WORDS
        or folded in _TECHNICAL_WORDS
        or folded in _ALLOWED_PROPER_NAME_WORDS
        or _is_technical_token(token)
    ):
        return True
    before = text[max(0, match.start() - 4):match.start()]
    after = text[match.end():match.end() + 4]
    operator = r"(?:=|\+|-|\*|/|\^|<=|>=|!=|->)"
    adjacent_to_operator = bool(
        re.search(operator + r"\s*$", before)
        or re.match(r"\s*" + operator, after)
    )
    if re.search(r"->\s*$", before) or re.match(r"\s*->", after):
        return False
    return bool(adjacent_to_operator and token.islower() and _CJK_RE.search(text))


def is_chinese_learning_content(
    value: object,
    *,
    allow_name_only: bool = False,
) -> bool:
    """Return whether learner-visible prose satisfies the Chinese contract.

    Code, formulas, URLs, identifiers, acronyms and short proper/technical
    names are allowed to remain unchanged. English explanatory sentences are
    rejected even when another part of the payload contains enough Chinese to
    hide them in an aggregate character ratio.
    """
    text = str(value or "")
    if not text.strip():
        return False

    prose, found_exemption = _strip_exempt_content(text)
    has_visible_content = False
    for raw_line in prose.splitlines():
        line = _MARKDOWN_PREFIX_RE.sub("", raw_line).strip()
        if not line:
            continue
        has_visible_content = True
        if _NON_SIMPLIFIED_CJK_RE.search(line) or _contains_other_natural_language_script(line):
            return False
        scan_line = _fold_latin_diacritics(line)
        latin_tokens = list(_LATIN_TOKEN_RE.finditer(scan_line))
        if not latin_tokens:
            continue
        for previous, current in zip(latin_tokens, latin_tokens[1:]):
            between = scan_line[previous.end():current.start()]
            if (
                between
                and _UPPERCASE_PROSE_SEPARATOR_RE.fullmatch(between)
                and _is_contextual_abbreviation(previous.group(0), scan_line)
                and _is_contextual_abbreviation(current.group(0), scan_line)
            ):
                return False
        connectors = {"and", "of", "the"}
        non_connectors = [
            match
            for match in latin_tokens
            if match.group(0).casefold() not in connectors
        ]
        if not non_connectors or not all(
            _latin_token_is_allowed(scan_line, match)
            for match in non_connectors
        ):
            return False

    if has_visible_content:
        return True
    if found_exemption:
        return True
    # A formula or symbol-only answer may not match the Markdown math forms.
    return bool(re.search(r"[0-9=+*/^_<>≤≥≠∑∫√∞α-ωΑ-Ω]", text))


def is_chinese_explanatory_text(value: object) -> bool:
    """Return whether the explanatory prose is predominantly Chinese.

    Code blocks, inline code and URLs are excluded so normal technical content
    can keep identifiers and API names in their original form.
    """
    return is_chinese_learning_content(value)


def non_chinese_resource_fields(payload: Mapping[str, Any]) -> list[str]:
    """Return learner-visible resource fields that contain English prose."""
    failures: list[str] = []

    def visit(value: Any, path: str, field_name: str) -> None:
        if len(failures) >= 12:
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_text = str(key)
                if key_text in _RESOURCE_IGNORED_FIELDS:
                    continue
                child_path = f"{path}.{key_text}" if path else key_text
                if key_text == "mermaid_source":
                    if not is_chinese_mermaid_text(item):
                        failures.append(child_path)
                    continue
                visit(item, child_path, key_text)
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for index, item in enumerate(value):
                visit(item, f"{path}.{index}", field_name)
            return
        if isinstance(value, str) and value.strip() and not is_chinese_learning_content(
            value,
            allow_name_only=field_name in _RESOURCE_NAME_FIELDS,
        ):
            if not (
                field_name in _RESOURCE_CODE_VALUE_FIELDS
                and _looks_like_inline_code(value)
            ):
                failures.append(path)

    visit(payload, "", "")
    return failures


def non_chinese_tutor_fields(payload: Mapping[str, Any]) -> list[str]:
    """Return structured Tutor fields that contain English explanations."""
    failures: list[str] = []

    def visit(value: Any, path: str, *, code_value: bool = False) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(item, f"{path}.{key}" if path else str(key), code_value=code_value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for index, item in enumerate(value):
                visit(item, f"{path}.{index}", code_value=code_value)
        elif isinstance(value, str) and value.strip():
            if code_value and (
                _looks_like_fenced_code("python", value)
                or _looks_like_code_block(value)
                or _looks_like_inline_code(value)
            ):
                return
            if not is_chinese_learning_content(value):
                failures.append(path)

    for field_name in TUTOR_LEARNER_TEXT_FIELDS:
        if payload.get(field_name) not in (None, "", [], {}):
            visit(
                payload[field_name],
                field_name,
                code_value=field_name == "code_example",
            )
    return failures


def is_chinese_mermaid_text(value: object) -> bool:
    """Return whether Mermaid's user-visible labels satisfy the Chinese contract."""
    text = str(value or "").strip()
    if not text:
        return True

    visible_text = re.sub(r"%%\{.*?\}%%", "", text, flags=re.DOTALL)
    first_directive = next(
        (
            line.strip()
            for line in visible_text.splitlines()
            if line.strip() and not line.lstrip().startswith("%%")
        ),
        "",
    )
    if not first_directive or not _SUPPORTED_MERMAID_RE.match(first_directive):
        return False
    quoted_labels = _MERMAID_QUOTED_LABEL_RE.findall(visible_text)
    plain_source = _MERMAID_QUOTED_LABEL_RE.sub('""', visible_text)
    bare_node_labels: list[str] = []
    for line in visible_text.splitlines():
        if not re.search(r"-->|---|==>|-.->", line):
            continue
        structure_only = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|\|[^|]*\|", " ", line)
        bare_node_labels.extend(
            token
            for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", structure_only)
            if token.casefold() not in {"graph", "flowchart", "subgraph", "td", "lr", "rl", "bt"}
        )
    labels = [
        *quoted_labels,
        *(_MERMAID_PLAIN_LABEL_RE.findall(plain_source)),
        *(_MERMAID_EDGE_LABEL_RE.findall(visible_text)),
        *(_MERMAID_SUBGRAPH_RE.findall(visible_text)),
        *bare_node_labels,
    ]
    if not labels:
        return True

    for label in labels:
        visible = _HTML_TAG_RE.sub(" ", label).strip().strip('"\'')
        bracketed = re.search(r"\[([^\]]+)\]\s*$", visible)
        if bracketed:
            visible = bracketed.group(1).strip().strip('"\'')
        if not visible:
            continue
        if _NON_SIMPLIFIED_CJK_RE.search(visible) or _contains_other_natural_language_script(visible):
            return False
        chinese_count = len(_CJK_RE.findall(visible))
        latin_count = sum(
            1
            for char in visible
            if _LATIN_RE.fullmatch(char) or "LATIN" in unicodedata.name(char, "")
        )
        if latin_count == 0:
            continue
        if chinese_count == 0:
            words = {word.casefold() for word in _LATIN_WORD_RE.findall(visible)}
            if words.intersection(_GENERIC_ENGLISH_MERMAID_LABELS):
                return False
            if _is_formula_or_symbol_expression(visible):
                continue
            if _is_technical_or_name_fragment(visible, allow_name_only=False):
                continue
            return False
        if not is_chinese_learning_content(visible):
            return False
    return True
