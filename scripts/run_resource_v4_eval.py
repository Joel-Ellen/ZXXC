"""Run the minimum 120-scenario offline resource-v4 contract evaluation."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.resource_generation.context import ResourceContext
from src.resource_generation.generator import ResourceGenerator
from src.resource_generation.validator import validate_resource_payload


SCENARIOS = (
    ("foundational", "definition", False),
    ("developing", "boundary", False),
    ("proficient", "transfer", False),
    ("advanced", "none", False),
    ("developing", "code_trace", True),
    ("foundational", "media_missing", False),
)
CARD_TYPES = (
    "concept_map",
    "code_snippet",
    "interactive_exercise",
    "video_summary",
    "diagnostic_quiz",
)


def scenario_context(node_number: int, scenario: tuple[str, str, bool]) -> ResourceContext:
    mastery_bucket, error_signature, has_video = scenario
    node_id = f"N{node_number:02d}"
    source = {
        "id": f"kb:{node_id}:core",
        "type": "knowledge_base",
        "title": f"节点 {node_id} 证据",
        "excerpt": f"节点 {node_id} 的定义、机制、适用条件和边界均以此课程证据为准。",
        "course_id": "data_structures",
        "node_ids": [node_id],
        "content_kind": "explanation",
        "locale": "zh-CN",
        "content_version": "resource-kb-v4",
    }
    if has_video:
        source.update({
            "type": "video",
            "video_url": f"https://trusted.example/{node_id}",
            "video_source_id": f"video:{node_id}",
        })
    mastery = {
        "foundational": 0.2,
        "developing": 0.5,
        "proficient": 0.75,
        "advanced": 0.92,
    }[mastery_bucket]
    return ResourceContext(
        user_id="offline-eval",
        course_id="data_structures",
        node_id=node_id,
        node_title=f"数据结构节点 {node_id}",
        capability_target="定义、机制、应用、边界与迁移",
        knowledge_refs=[source],
        mastery=mastery,
        mastery_bucket=mastery_bucket,
        error_signature=error_signature,
        content_version="resource-v4",
        knowledge_index_version="resource-kb-v4",
        locale="zh-CN",
        evidence_status="grounded",
    )


def main() -> int:
    generator = ResourceGenerator()
    failures: list[dict[str, object]] = []
    scenario_count = 0
    card_count = 0
    for node_number in range(1, 21):
        for scenario in SCENARIOS:
            scenario_count += 1
            context = scenario_context(node_number, scenario)
            concept = generator.template(context, "concept_map")
            context = replace(
                context,
                blueprint_snapshot=dict(
                    concept.structured_payload["learning_blueprint"]
                ),
            )
            generated = {
                "concept_map": concept,
                **{
                    card_type: generator.template(context, card_type)
                    for card_type in CARD_TYPES
                    if card_type != "concept_map"
                },
            }
            for card_type, card in generated.items():
                card_count += 1
                validation = validate_resource_payload(
                    card_type,
                    card.structured_payload,
                    context,
                )
                if not validation.valid:
                    failures.append({
                        "node_id": context.node_id,
                        "scenario": scenario,
                        "card_type": card_type,
                        "issues": [issue.code for issue in validation.issues],
                    })
    result = {
        "scenarios": scenario_count,
        "cards": card_count,
        "failures": len(failures),
        "sample_failures": failures[:10],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if scenario_count < 120:
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
