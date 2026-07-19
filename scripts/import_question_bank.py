"""Import the supplied data-structures JSON archive into a compact bank.

The source archive is an OCR/text extraction artifact, not an application
contract.  This importer deliberately keeps every question candidate for
auditability while marking only bounded, text-complete records as eligible
LLM inspiration.  It never treats an extracted answer as verified truth.

Usage::

    python scripts/import_question_bank.py path/to/question-bank.zip

The default output is ``src/question_bank/data_structures_questions.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"
COURSE_ID = "data_structures"
MAX_ARCHIVE_FILES = 64
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED_BYTES = 12 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_GENERATION_TEXT_CHARS = 2_400
MAX_BANK_QUESTIONS = 20_000
MAX_BANK_OUTPUT_BYTES = 16 * 1024 * 1024

NODE_TITLES: dict[str, str] = {
    "N01": "算法复杂度分析",
    "N02": "线性表与顺序存储",
    "N03": "链表与链式存储",
    "N04": "栈及其应用",
    "N05": "队列及其应用",
    "N06": "树与二叉树基础",
    "N07": "二叉搜索树",
    "N08": "AVL 平衡树",
    "N09": "散列表与哈希",
    "N10": "图的基本概念与存储",
    "N11": "图的遍历 DFS/BFS",
    "N12": "最小生成树",
    "N13": "最短路径算法",
    "N14": "拓扑排序与关键路径",
    "N15": "排序算法基础",
    "N16": "高级排序算法",
    "N17": "查找与索引技术",
    "N18": "动态规划入门",
    "N19": "贪心算法与回溯",
    "N20": "数据结构综合应用",
}

_CHINESE_CHAPTERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
}
_ANSWER_RE = re.compile(r"[（(]\s*([A-D])\s*[）)]")
_SOURCE_CITATION_RE = re.compile(r"【[^】]*】")
_OPTION_MARKER_RE = re.compile(r"(?<![A-Za-z0-9])([A-H])[\.．、)）]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class QuestionBankImportError(ValueError):
    """Raised when an archive is unsafe or does not match the expected shape."""


def _contains(text: str, terms: Iterable[str]) -> bool:
    folded = text.casefold()
    return any(term.casefold() in folded for term in terms)


def _normalize_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _chapter_number(*values: str) -> int | None:
    text = " ".join(values)
    match = re.search(r"第\s*(\d{1,2}|十一|十|[一二三四五六七八九])\s*章", text)
    if not match:
        return None
    value = match.group(1)
    if value.isdigit():
        return int(value)
    return _CHINESE_CHAPTERS.get(value)


def _add(nodes: list[str], *values: str) -> None:
    for value in values:
        if value in NODE_TITLES and value not in nodes:
            nodes.append(value)


def _classify_classic(text: str) -> list[str]:
    nodes: list[str] = []
    if _contains(text, ("时间复杂度", "空间复杂度", "算法复杂度", "大O", "Big O")):
        _add(nodes, "N01")
    if _contains(text, ("链表", "链式", "链栈", "链队列", "头结点", "指针域")):
        _add(nodes, "N03")
    if _contains(text, ("顺序表", "顺序存储", "向量", "数组", "矩阵")):
        _add(nodes, "N02")
    if _contains(text, ("栈", "PUSH", "POP", "括号")):
        _add(nodes, "N04")
    if _contains(text, ("队列", "队首", "队尾", "循环队列", "双端队列")):
        _add(nodes, "N05")
    if _contains(text, ("AVL", "平衡二叉树", "平衡树")):
        _add(nodes, "N08")
    elif _contains(text, ("二叉排序树", "二叉查找树", "搜索树", "查找树")):
        _add(nodes, "N07")
    elif _contains(text, ("二叉树", "树", "遍历", "线索化")):
        _add(nodes, "N06")
    if _contains(text, ("哈希", "散列")):
        _add(nodes, "N09")
    if _contains(text, ("快速排序", "归并排序", "堆排序", "基数排序", "希尔排序", "Shell")):
        _add(nodes, "N16")
    if _contains(text, ("冒泡排序", "起泡排序", "插入排序", "选择排序", "排序方法")):
        _add(nodes, "N15")
    if _contains(text, ("串", "字符串", "广义表")):
        _add(nodes, "N20")
    return nodes or ["N20"]


def _classify_nodes(chapter: int | None, text: str) -> list[str]:
    if chapter is None:
        return _classify_classic(text)
    if chapter == 1:
        return ["N01"]
    if chapter == 2:
        nodes: list[str] = []
        if _contains(text, ("链表", "链式", "指针", "结点", "静态链表")):
            _add(nodes, "N03")
        if _contains(text, ("顺序表", "顺序存储", "数组", "向量")):
            _add(nodes, "N02")
        return nodes or ["N02", "N03"]
    if chapter == 3:
        nodes = []
        if _contains(text, ("栈", "进栈", "退栈", "出栈", "PUSH", "POP", "递归", "括号")):
            _add(nodes, "N04")
        if _contains(text, ("队列", "入队", "出队", "队首", "队尾", "循环队列", "双端队列")):
            _add(nodes, "N05")
        return nodes or ["N04", "N05"]
    if chapter == 4:
        return ["N20"]
    if chapter == 5:
        nodes = []
        if _contains(text, ("数组", "矩阵", "稀疏", "行序", "列序", "顺序存储")):
            _add(nodes, "N02")
        if _contains(text, ("广义表", "递归表")):
            _add(nodes, "N20")
        return nodes or ["N20"]
    if chapter == 6:
        if _contains(text, ("AVL", "平衡二叉树", "平衡树")):
            return ["N08"]
        if _contains(text, ("二叉排序树", "二叉查找树", "搜索树", "查找树")):
            return ["N07"]
        if _contains(text, ("堆排序", "大顶堆", "小顶堆", "最大堆", "最小堆")):
            return ["N16"]
        return ["N06"]
    if chapter == 7:
        if _contains(text, ("拓扑", "关键路径", "AOV", "AOE")):
            return ["N14"]
        if _contains(text, ("最短路径", "Dijkstra", "Floyd", "迪杰斯特拉", "弗洛伊德")):
            return ["N13"]
        if _contains(text, ("最小生成树", "Prim", "Kruskal", "普里姆", "克鲁斯卡尔")):
            return ["N12"]
        if _contains(text, ("遍历", "深度优先", "广度优先", "DFS", "BFS", "连通分量")):
            return ["N11"]
        return ["N10"]
    if chapter == 8:
        return ["N20"]
    if chapter == 9:
        if _contains(text, ("哈希", "散列")):
            return ["N09"]
        if _contains(text, ("AVL", "平衡二叉树", "平衡树")):
            return ["N08"]
        if _contains(text, ("二叉排序树", "二叉查找树", "搜索树", "查找树")):
            return ["N07"]
        return ["N17"]
    if chapter == 10:
        nodes = []
        if _contains(text, ("快速排序", "归并排序", "堆排序", "基数排序", "希尔排序", "Shell", "外部排序", "多路归并")):
            _add(nodes, "N16")
        if _contains(text, ("冒泡排序", "起泡排序", "直接插入", "简单选择", "插入排序", "选择排序", "交换排序")):
            _add(nodes, "N15")
        return nodes or ["N15", "N16"]
    if chapter == 11:
        return ["N17"]
    return ["N20"]


def _question_type(section: str, text: str, *, answer_source: bool) -> str:
    if "选择" in section or answer_source or len(_OPTION_MARKER_RE.findall(text)) >= 2:
        return "multiple_choice"
    if "判断" in section:
        return "true_false"
    if "填空" in section:
        return "fill_blank"
    if any(value in section for value in ("应用", "算法", "简答", "综合", "设计")):
        return "open_response"
    return "unknown"


def _answer_from_source(text: str, *, answer_source: bool) -> tuple[str, str]:
    if not answer_source:
        return text, ""
    first_option = min(
        (match.start() for match in _OPTION_MARKER_RE.finditer(text)),
        default=len(text),
    )
    match = _ANSWER_RE.search(text, 0, first_option)
    if not match:
        return text, ""
    prompt_text = text[: match.start(1)] + "____" + text[match.end(1) :]
    return prompt_text, match.group(1)


def _dedupe_key(text: str) -> str:
    without_sources = _SOURCE_CITATION_RE.sub("", text)
    return re.sub(r"\W+", "", without_sources.casefold(), flags=re.UNICODE)


def _stable_question_id(source_file: str, blocks: list[Any], text: str) -> str:
    block_span = ",".join(str(value) for value in blocks)
    raw = f"{source_file}|{block_span}|{_dedupe_key(text)}".encode("utf-8")
    return "dsqb-" + hashlib.sha256(raw).hexdigest()[:20]


def _validate_member(info: zipfile.ZipInfo) -> None:
    member_path = PurePosixPath(info.filename.replace("\\", "/"))
    if member_path.is_absolute() or ".." in member_path.parts:
        raise QuestionBankImportError(f"unsafe archive member: {info.filename!r}")
    mode = (info.external_attr >> 16) & 0xFFFF
    if mode and stat.S_ISLNK(mode):
        raise QuestionBankImportError(f"symbolic links are not accepted: {info.filename!r}")
    if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
        raise QuestionBankImportError(f"archive member is too large: {info.filename!r}")
    if info.file_size and not info.compress_size:
        raise QuestionBankImportError(f"invalid compressed member: {info.filename!r}")
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise QuestionBankImportError(f"suspicious compression ratio: {info.filename!r}")


def _load_documents(archive_path: Path) -> list[dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise QuestionBankImportError(f"cannot open archive: {type(exc).__name__}") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise QuestionBankImportError("archive contains too many files")
        total_size = 0
        total_candidate_records = 0
        documents: list[dict[str, Any]] = []
        seen_document_digests: set[str] = set()
        for info in infos:
            _validate_member(info)
            total_size += info.file_size
            if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise QuestionBankImportError("archive uncompressed size exceeds the safety limit")
            if info.is_dir() or not info.filename.lower().endswith(".json"):
                continue
            try:
                value = json.loads(archive.read(info).decode("utf-8-sig"))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValueError,
                RecursionError,
            ) as exc:
                raise QuestionBankImportError(
                    f"invalid JSON member {info.filename!r}: {type(exc).__name__}"
                ) from exc
            # Deliberately ignore manifest.json and the aggregate document.
            # The latter contains the same 12 documents and would double the
            # bank if recursively traversed.
            if not isinstance(value, dict) or not isinstance(value.get("question_candidates"), list):
                continue
            candidates = value["question_candidates"]
            total_candidate_records += len(candidates)
            if total_candidate_records > MAX_BANK_QUESTIONS:
                raise QuestionBankImportError("archive contains too many question candidates")
            try:
                document_digest = hashlib.sha256(
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
            except (TypeError, ValueError, RecursionError) as exc:
                raise QuestionBankImportError(
                    f"invalid JSON structure in {info.filename!r}"
                ) from exc
            if document_digest in seen_document_digests:
                continue
            seen_document_digests.add(document_digest)
            document = dict(value)
            document["_archive_member"] = info.filename.replace("\\", "/")
            documents.append(document)
        if not documents:
            raise QuestionBankImportError("archive contains no question-candidate documents")
        return documents


def build_question_bank(archive_path: Path) -> dict[str, Any]:
    try:
        compressed_size = archive_path.stat().st_size
    except OSError as exc:
        raise QuestionBankImportError(f"cannot stat archive: {type(exc).__name__}") from exc
    if compressed_size <= 0 or compressed_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        raise QuestionBankImportError("archive compressed size exceeds the safety limit")
    archive_bytes = archive_path.read_bytes()
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    documents = _load_documents(archive_path)
    questions: list[dict[str, Any]] = []
    raw_documents: list[dict[str, Any]] = []
    first_by_dedupe_key: dict[str, str] = {}
    used_question_ids: set[str] = set()

    for document in documents:
        source = document.get("source") if isinstance(document.get("source"), dict) else {}
        source_file = _normalize_text(source.get("file_name") or document.get("title") or "unknown")
        source_title = _normalize_text(document.get("title") or source_file)
        archive_member = _normalize_text(document.get("_archive_member") or source_file)
        answer_source = "含答案" in source_file or "含答案" in source_title
        chapter = _chapter_number(source_file, source_title)
        raw_documents.append({
            "schema_version": str(document.get("schema_version") or ""),
            "source": source,
            "title": source_title,
            "extraction": document.get("extraction") if isinstance(document.get("extraction"), dict) else {},
            "statistics": document.get("statistics") if isinstance(document.get("statistics"), dict) else {},
            "text": str(document.get("text") or ""),
            "blocks": document.get("blocks") if isinstance(document.get("blocks"), list) else [],
        })
        for ordinal, raw_question in enumerate(document.get("question_candidates", []), start=1):
            if not isinstance(raw_question, dict):
                continue
            text = _normalize_text(raw_question.get("text"))
            if not text:
                continue
            prompt_text, answer_label = _answer_from_source(text, answer_source=answer_source)
            section = _normalize_text(raw_question.get("section"))
            question_type = _question_type(section, text, answer_source=answer_source)
            node_ids = _classify_nodes(chapter, prompt_text)
            raw_blocks = raw_question.get("blocks")
            blocks = raw_blocks if isinstance(raw_blocks, list) else []
            question_id = _stable_question_id(source_file, blocks, text)
            if question_id in used_question_ids:
                collision_seed = f"{question_id}|{archive_member}|{ordinal}"
                question_id = "dsqb-" + hashlib.sha256(
                    collision_seed.encode("utf-8")
                ).hexdigest()[:20]
                collision_index = 1
                while question_id in used_question_ids:
                    collision_index += 1
                    question_id = "dsqb-" + hashlib.sha256(
                        f"{collision_seed}|{collision_index}".encode("utf-8")
                    ).hexdigest()[:20]
            used_question_ids.add(question_id)
            issues: list[str] = []
            if "[OBJECT]" in text.upper():
                issues.append("object_placeholder")
            if len(prompt_text) < 12:
                issues.append("text_too_short")
            if len(prompt_text) > MAX_GENERATION_TEXT_CHARS:
                issues.append("text_too_long")
            if question_type == "unknown":
                issues.append("question_type_unknown")
            if not node_ids:
                issues.append("node_mapping_missing")
            if len(re.findall(r"[①②③④⑤⑥⑦⑧]|\(\s*\d+\s*\)", prompt_text)) >= 3:
                issues.append("complex_multi_part")
            if "类似本题的另外叙述有" in prompt_text:
                issues.append("bundled_variants")
            if "参考文献" in prompt_text or "Power by YOZOSOFT" in prompt_text:
                issues.append("source_tail_noise")
            dedupe_key = _dedupe_key(prompt_text)
            duplicate_of = first_by_dedupe_key.get(dedupe_key, "") if dedupe_key else ""
            if duplicate_of:
                issues.append("duplicate")
            elif dedupe_key:
                first_by_dedupe_key[dedupe_key] = question_id
            blocking = {
                "object_placeholder",
                "text_too_short",
                "text_too_long",
                "question_type_unknown",
                "node_mapping_missing",
                "complex_multi_part",
                "bundled_variants",
                "source_tail_noise",
                "duplicate",
            }
            questions.append({
                "id": question_id,
                "course_id": COURSE_ID,
                "node_ids": node_ids,
                "question_type": question_type,
                "text": text,
                "prompt_text": prompt_text,
                "source": {
                    "file_name": source_file,
                    "title": source_title,
                    "chapter": chapter,
                    "section": section,
                    "number": raw_question.get("number", ordinal),
                    "blocks": blocks,
                },
                "source_answer": (
                    {
                        "label": answer_label,
                        "status": "source_embedded_unverified",
                    }
                    if answer_label
                    else {"status": "missing"}
                ),
                "issues": issues,
                "duplicate_of": duplicate_of,
                "usable_for_generation": not any(issue in blocking for issue in issues),
            })

    node_index: dict[str, list[str]] = defaultdict(list)
    for question in questions:
        if not question["usable_for_generation"]:
            continue
        for node_id in question["node_ids"]:
            node_index[node_id].append(question["id"])
    for node_id in NODE_TITLES:
        node_index.setdefault(node_id, [])

    type_counts = Counter(question["question_type"] for question in questions)
    issue_counts = Counter(issue for question in questions for issue in question["issues"])
    digest_payload = {
        "questions": questions,
        "node_index": dict(sorted(node_index.items())),
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    bank = {
        "schema_version": SCHEMA_VERSION,
        "collection_version": f"ds-qbank-v1-{digest[:16]}",
        "course_id": COURSE_ID,
        "title": "数据结构题库",
        "source_archive": {
            "file_name": archive_path.name,
            "sha256": archive_sha256,
            "document_count": len(documents),
        },
        "node_titles": NODE_TITLES,
        "statistics": {
            "question_count": len(questions),
            "generation_eligible_count": sum(
                1 for question in questions if question["usable_for_generation"]
            ),
            "question_types": dict(sorted(type_counts.items())),
            "issues": dict(sorted(issue_counts.items())),
            "questions_by_node": {
                node_id: len(question_ids)
                for node_id, question_ids in sorted(node_index.items())
            },
        },
        "node_index": dict(sorted(node_index.items())),
        # Preserve the complete extraction layer, including blocks that the
        # source heuristic failed to attach to a question candidate. Runtime
        # generation never reads this field; it exists for traceability and
        # future re-segmentation without needing the original ZIP.
        "raw_documents": raw_documents,
        "questions": questions,
    }
    try:
        serialized_size = len(
            (json.dumps(bank, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise QuestionBankImportError("normalized question bank is not serializable") from exc
    if serialized_size > MAX_BANK_OUTPUT_BYTES:
        raise QuestionBankImportError("normalized question bank exceeds the runtime size limit")
    return bank


def _default_output() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "question_bank" / "data_structures_questions.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the data-structures JSON question bank")
    parser.add_argument("archive", type=Path, help="Path to the supplied ZIP archive")
    parser.add_argument("--output", type=Path, default=_default_output())
    args = parser.parse_args()
    archive_path = args.archive.expanduser().resolve()
    if not archive_path.is_file():
        parser.error(f"archive does not exist: {archive_path}")
    bank = build_question_bank(archive_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(bank, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=args.output.parent,
            prefix=f".{args.output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, args.output)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "collection_version": bank["collection_version"],
                **bank["statistics"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
