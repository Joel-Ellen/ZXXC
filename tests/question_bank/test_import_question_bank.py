from __future__ import annotations

import json
import zipfile

import pytest

import scripts.import_question_bank as importer
from scripts.import_question_bank import (
    QuestionBankImportError,
    build_question_bank,
)


def _document(text: str, *, title: str = "第1章 绪论") -> dict:
    return {
        "schema_version": "1.0",
        "source": {"file_name": f"{title}.doc", "format": "doc"},
        "title": title,
        "extraction": {},
        "statistics": {"characters": len(text), "blocks": 2, "question_candidates": 1},
        "text": text,
        "blocks": [
            {"index": 1, "line": 1, "type": "title", "text": title},
            {"index": 2, "line": 2, "type": "numbered_item", "text": text},
        ],
        "question_candidates": [{
            "number": 1,
            "section": "一、选择题",
            "text": text,
            "blocks": [2],
        }],
    }


def test_import_ignores_duplicate_aggregate_and_is_deterministic(tmp_path) -> None:
    document = _document("算法的时间复杂度通常用于衡量什么？\nA. 时间增长量 B. 颜色 C. 文件名 D. 用户名")
    archive = tmp_path / "bank.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("bank/chapter.json", json.dumps(document, ensure_ascii=False))
        value.writestr("bank/manifest.json", json.dumps({"files": ["chapter.doc"]}))
        value.writestr("aggregate.json", json.dumps({"documents": [document]}, ensure_ascii=False))

    first = build_question_bank(archive)
    second = build_question_bank(archive)

    assert first["statistics"]["question_count"] == 1
    assert len(first["raw_documents"]) == 1
    assert first["collection_version"] == second["collection_version"]
    assert first["questions"][0]["node_ids"] == ["N01"]


def test_import_redacts_source_embedded_answer_from_prompt_text(tmp_path) -> None:
    document = _document(
        "栈的访问原则是（ B ）。\nA）先进先出 B）后进先出 C）随机访问 D）按值排序",
        title="经典数据结构习题集含答案",
    )
    archive = tmp_path / "answers.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("chapter.json", json.dumps(document, ensure_ascii=False))

    question = build_question_bank(archive)["questions"][0]

    assert question["source_answer"] == {
        "label": "B",
        "status": "source_embedded_unverified",
    }
    assert "（ B ）" not in question["prompt_text"]
    assert "____" in question["prompt_text"]


def test_import_rejects_path_traversal(tmp_path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("../chapter.json", json.dumps(_document("valid question text")))

    with pytest.raises(QuestionBankImportError, match="unsafe archive member"):
        build_question_bank(archive)


def test_import_skips_duplicate_chapter_documents(tmp_path) -> None:
    document = _document(
        "算法的时间复杂度通常用于衡量什么？\nA. 时间增长量 B. 颜色 C. 文件名 D. 用户名"
    )
    archive = tmp_path / "duplicate-chapter.zip"
    with zipfile.ZipFile(archive, "w") as value:
        serialized = json.dumps(document, ensure_ascii=False)
        value.writestr("chapter.json", serialized)
        value.writestr("copied/chapter.json", serialized)

    bank = build_question_bank(archive)

    assert bank["statistics"]["question_count"] == 1
    assert len(bank["raw_documents"]) == 1


def test_import_assigns_unique_ids_to_repeated_candidates(tmp_path) -> None:
    document = _document(
        "算法的时间复杂度通常用于衡量什么？\nA. 时间增长量 B. 颜色 C. 文件名 D. 用户名"
    )
    document["question_candidates"].append(
        dict(document["question_candidates"][0])
    )
    archive = tmp_path / "repeated-candidate.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("chapter.json", json.dumps(document, ensure_ascii=False))

    bank = build_question_bank(archive)

    assert len(bank["questions"]) == 2
    assert len({question["id"] for question in bank["questions"]}) == 2
    assert bank["questions"][1]["duplicate_of"] == bank["questions"][0]["id"]
    assert bank["questions"][1]["usable_for_generation"] is False


def test_import_rejects_candidate_count_above_runtime_limit(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document("足够长的第一道测试题目文本")
    document["question_candidates"].append({
        **document["question_candidates"][0],
        "text": "足够长的第二道测试题目文本",
    })
    archive = tmp_path / "too-many-candidates.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr("chapter.json", json.dumps(document, ensure_ascii=False))
    monkeypatch.setattr(importer, "MAX_BANK_QUESTIONS", 1)

    with pytest.raises(QuestionBankImportError, match="too many question candidates"):
        build_question_bank(archive)


def test_import_rejects_output_above_runtime_size_limit(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "oversized-output.zip"
    with zipfile.ZipFile(archive, "w") as value:
        value.writestr(
            "chapter.json",
            json.dumps(_document("足够长的题目文本"), ensure_ascii=False),
        )
    monkeypatch.setattr(importer, "MAX_BANK_OUTPUT_BYTES", 512)

    with pytest.raises(QuestionBankImportError, match="runtime size limit"):
        build_question_bank(archive)
