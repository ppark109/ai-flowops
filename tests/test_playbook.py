from pathlib import Path

import yaml

from workflows.playbook import load_default_playbook, rule_ids_by_route, validate_playbook
from workflows.routing import ROUTES


def test_default_playbook_loads() -> None:
    playbook = load_default_playbook()

    assert playbook.name == "default-commercial-intake-playbook"
    assert len(playbook.rules) == 14


def test_default_playbook_routes_are_supported() -> None:
    playbook = load_default_playbook()
    supported_routes = set(ROUTES)

    assert {rule.route for rule in playbook.rules}.issubset(supported_routes)


def test_default_playbook_covers_all_mvp_routes() -> None:
    route_map = rule_ids_by_route(load_default_playbook())

    assert set(route_map) == set(ROUTES)


def test_invalid_playbook_rejects_duplicate_rule_id(tmp_path: Path) -> None:
    payload = {
        "name": "bad",
        "version": "1.0",
        "approval_policy": "on_high_risk",
        "rules": [
            {
                "id": "dup-rule",
                "description": "a",
                "when": {"contains_any": ["standard"]},
                "severity": "low",
                "route": "auto_approve",
                "approval_required": False,
            },
            {
                "id": "dup-rule",
                "description": "b",
                "when": {"contains_any": ["standard"]},
                "severity": "low",
                "route": "auto_approve",
                "approval_required": False,
            },
        ],
    }
    playbook_path = tmp_path / "bad.yaml"
    playbook_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    from workflows.playbook import load_playbook

    bad = load_playbook(playbook_path)
    import pytest

    with pytest.raises(ValueError, match="Duplicate rule id"):
        validate_playbook(bad)


def test_invalid_playbook_rejects_unsupported_route(tmp_path: Path) -> None:
    payload = {
        "name": "bad",
        "version": "1.0",
        "approval_policy": "on_high_risk",
        "rules": [
            {
                "id": "x",
                "description": "x",
                "when": {"contains_any": ["x"]},
                "severity": "low",
                "route": "not_a_route",
                "approval_required": False,
            }
        ],
    }
    playbook_path = tmp_path / "bad.yaml"
    playbook_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    import pytest

    from workflows.playbook import load_playbook

    bad = load_playbook(playbook_path)
    with pytest.raises(ValueError, match="unsupported route"):
        validate_playbook(bad)


def test_invalid_playbook_rejects_high_without_approval(tmp_path: Path) -> None:
    payload = {
        "name": "bad",
        "version": "1.0",
        "approval_policy": "on_high_risk",
        "rules": [
            {
                "id": "x",
                "description": "x",
                "when": {"contains_any": ["x"]},
                "severity": "high",
                "route": "legal",
                "approval_required": False,
            }
        ],
    }
    playbook_path = tmp_path / "bad.yaml"
    playbook_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    import pytest

    from workflows.playbook import load_playbook

    bad = load_playbook(playbook_path)
    with pytest.raises(ValueError, match="requires approval"):
        validate_playbook(bad)
