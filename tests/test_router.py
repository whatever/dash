from dash.queue import UPDATE, Job
from dash.router import Action, RoutedBy, route


def test_chat_job_routes_to_chat_by_rule() -> None:
    decision = route(Job("1-0", "j1", "c1"), None)

    assert (decision.action, decision.routed_by, decision.confidence) == (
        Action.CHAT,
        RoutedBy.RULES,
        None,
    )


def test_source_route_decides_an_update() -> None:
    decision = route(Job("1-0", "j1", kind=UPDATE, data={"source": "web:x"}), Action.FLAG)

    assert (decision.action, decision.routed_by) == (Action.FLAG, RoutedBy.RULES)


def test_update_without_a_rule_falls_back_to_remember() -> None:
    decision = route(Job("1-0", "j1", kind=UPDATE, data={"source": "web:x"}), None)

    assert (decision.action, decision.routed_by) == (Action.REMEMBER, RoutedBy.FALLBACK)
