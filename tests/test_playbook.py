from workflows.playbook import load_default_playbook, rule_ids_by_route
from workflows.routing import ROUTES


def test_default_playbook_loads() -> None:
    playbook = load_default_playbook()

    assert playbook.name == "ai-flowops-default-playbook"
    assert len(playbook.rules) == 18


def test_default_playbook_routes_are_supported() -> None:
    playbook = load_default_playbook()
    supported_routes = set(ROUTES)

    assert {rule.route for rule in playbook.rules}.issubset(supported_routes)


def test_default_playbook_covers_all_mvp_routes() -> None:
    route_map = rule_ids_by_route(load_default_playbook())

    assert set(route_map) == set(ROUTES)
