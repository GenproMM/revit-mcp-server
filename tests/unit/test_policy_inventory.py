# -*- coding: utf-8 -*-
"""Policy inventory guard (Phase 7, SAFE-06/SAFE-07).

The live tool and route surfaces are derived from source through inventory_support.
A developer adding either surface must add its [tools] or [routes] policy.base.toml
entry in the same commit; an unclassified path is a coverage gap, never an allow.
"""

import policy
from inventory_support import (
    LOCAL, TOOL_CLASSES, manifest_names, reachable_calls, route_inventory,
    tool_transport_calls,
)


# This is deliberately a literal decision table rather than a derivation from names,
# route classes, or HTTP methods. All omitted routes are the D-13 default allow set.
EXPECTED = {
    "/delete_elements/": ("confirm", None),
    "/edit_family/": ("check", "family_edit"),
    "/execute_code/": ("confirm", None),
    "/load_family/": ("confirm", None),
    "/modify_element/": ("check", "parameter_write"),
    "/set_parameter/": ("check", "parameter_write"),
    "/transform_elements/": ("confirm", None),
}


def coverage_gaps(active_policy, manifest_names_list, route_keys):
    """Return sorted unclassified tools and routes for the supplied source inventories.

    A new tool or route needs a [tools]/[routes] entry in policy.base.toml in the
    same commit; it is not implicitly classified by its name or transport method.
    """
    return (
        sorted(set(manifest_names_list) - set(active_policy.tools)),
        sorted(set(route_keys) - set(active_policy.rules)),
    )


def _is_get(route):
    return bool(route.methods) and all(method in ("GET", "HEAD") for method in route.methods)


def test_tools_equal_the_manifest():
    active = policy.load_base()

    assert set(active.tools) == set(manifest_names())
    assert len(active.tools) == 59


def test_tools_map_to_their_ast_transport_routes():
    active = policy.load_base()
    calls = tool_transport_calls()

    assert set(calls) == set(manifest_names())
    for name in manifest_names():
        expected_routes = {route for _, route in calls[name]}
        assert set(active.tools[name]["routes"]) == expected_routes, name


def test_route_free_local_tools_are_explicitly_marked_local():
    active = policy.load_base()

    for name in ("discover_revit_targets", "start_revit"):
        assert active.tools[name]["routes"] == (), name
        assert active.tools[name]["local"] is True, name


def test_routes_equal_the_ast_inventory():
    active = policy.load_base()
    routes = route_inventory()

    assert set(active.rules) == {route.key for route in routes}
    assert len(active.rules) == len(routes) == 57


def test_policy_methods_match_route_decorators_and_get_is_always_allow():
    active = policy.load_base()

    for route in route_inventory():
        rule = active.rule_for(route.key)
        assert rule.method == ("GET" if _is_get(route) else "POST"), route.key
        if _is_get(route):
            assert rule.decision == "allow", route.key


def test_document_bound_matches_the_handler_call_graph():
    active = policy.load_base()

    for route in route_inventory():
        expected = "mutation_document_or_response" in reachable_calls(route)
        assert active.rule_for(route.key).document_bound == expected, route.key


def test_literal_decisions_match_the_user_table():
    active = policy.load_base()

    for route in active.rules:
        expected = EXPECTED.get(route, ("allow", None))
        rule = active.rule_for(route)
        assert (rule.decision, rule.check) == expected, route


def test_coverage_gaps_report_a_new_tool_and_route():
    active = policy.load_base()
    route_keys = [route.key for route in route_inventory()]

    assert coverage_gaps(active, manifest_names(), route_keys) == ([], [])
    assert coverage_gaps(active, manifest_names() + ["brand_new_tool"], route_keys) == (
        ["brand_new_tool"], [])
    assert coverage_gaps(active, manifest_names(), route_keys + ["/brand_new_route/"]) == (
        [], ["/brand_new_route/"])


def test_unknown_route_has_no_rule():
    assert policy.load_base().rule_for("/no_such_route/") is None


def test_parameter_redefinition_paths_are_never_allow():
    active = policy.load_base()

    for route in ("/delete_elements/", "/edit_family/", "/execute_code/"):
        assert active.rule_for(route).decision != "allow", route
