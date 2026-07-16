from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.resource_v4_load_test import load_targets


def test_generation_load_requires_distinct_concurrent_targets(tmp_path) -> None:
    accounts = tmp_path / "accounts.jsonl"
    accounts.write_text(
        "\n".join([
            '{"session_id":"u1:c1","node_id":"N01","token":"t1"}',
            '{"session_id":"u2:c1","node_id":"N02","token":"t2"}',
        ]),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        accounts_file=str(accounts),
        session_id=None,
        node_id="N01",
        token=None,
        mode="generation",
        concurrency=2,
    )

    targets = load_targets(args)

    assert [target.session_id for target in targets] == ["u1:c1", "u2:c1"]


def test_generation_load_rejects_collapsed_single_user_pressure() -> None:
    args = SimpleNamespace(
        accounts_file=None,
        session_id="u1:c1",
        node_id="N01",
        token="token",
        mode="generation",
        concurrency=50,
    )

    with pytest.raises(ValueError, match="distinct target"):
        load_targets(args)
