# -*- coding: utf-8 -*-
"""Pure decision-table tests for the Phase 7 mutation-safety policy."""

import os

import approval
import policy
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


BASE = policy.load_base()


def rule(route):
    return BASE.rule_for(route)


def parameter_facts(parameters=None, element=None, available=True):
    return {
        "available": available,
        "element": element or {
            "id": 101, "exists": True, "is_type": False, "group_member": False,
            "type_instance_count": 1,
        },
        "parameters": parameters if parameters is not None else [{
            "name": "Comment", "resolved": "instance", "has_value": False, "read_only": False,
        }],
    }


def decision(route, data=None, facts=None, fop=None):
    return policy.decide(rule(route), data or {}, facts=facts, fop=fop)


def merged_rule(route, overlay):
    with open(os.path.join(policy._HERE, policy.BASE_FILE), "rb") as handle:
        base_document = policy.parse_policy_bytes(handle.read())
    document = policy.merge(base_document, overlay)
    return policy.build_policy(document, "test", "0123456789ab").rule_for(route)


def test_safe_empty_instance_parameter_write_is_allow():
    result = decision("/set_parameter/", {"parameters": [{"name": "Comment"}]}, parameter_facts())

    assert result == policy.Decision("allow", ("parameter_write",))


@pytest.mark.parametrize("route", ("/set_parameter/", "/modify_element/"))
def test_missing_facts_confirm_parameter_writes(route):
    assert decision(route) == policy.Decision("confirm", ("parameter_write", "facts_unavailable"))


@pytest.mark.parametrize("facts", (None, {"available": False}, {"available": True}))
def test_unavailable_or_incomplete_facts_confirm(facts):
    assert decision("/set_parameter/", facts=facts) == policy.Decision(
        "confirm", ("parameter_write", "facts_unavailable"))


def test_type_level_parameter_write_confirms_with_type_and_multiple_reasons():
    facts = parameter_facts(
        [{"name": "Type Mark", "resolved": "type", "has_value": False, "read_only": False}],
        element={"id": 101, "exists": True, "is_type": False, "group_member": False,
                 "type_instance_count": 340},
    )

    assert decision("/set_parameter/", facts=facts) == policy.Decision(
        "confirm", ("parameter_write", "type_parameter", "multiple_elements"))


def test_type_element_confirms_with_type_reason():
    facts = parameter_facts(element={"id": 101, "exists": True, "is_type": True,
                                     "group_member": False, "type_instance_count": 1})

    assert decision("/set_parameter/", facts=facts) == policy.Decision(
        "confirm", ("parameter_write", "type_parameter"))


def test_unknown_type_instance_count_is_conservatively_multiple():
    facts = parameter_facts(
        [{"name": "Type Mark", "resolved": "type", "has_value": False, "read_only": False}],
        element={"id": 101, "exists": True, "is_type": False, "group_member": False,
                 "type_instance_count": None},
    )

    assert decision("/set_parameter/", facts=facts) == policy.Decision(
        "confirm", ("parameter_write", "type_parameter", "multiple_elements"))


def test_existing_value_confirms_overwrite():
    facts = parameter_facts(
        [{"name": "Comment", "resolved": "instance", "has_value": True, "read_only": False}])

    assert decision("/set_parameter/", facts=facts) == policy.Decision(
        "confirm", ("parameter_write", "overwrites_value"))


def test_unknown_value_or_missing_parameter_confirms_with_unavailable_facts():
    unknown = parameter_facts(
        [{"name": "Comment", "resolved": "instance", "has_value": None, "read_only": False}])
    missing = parameter_facts(
        [{"name": "Comment", "resolved": "not_found", "has_value": None, "read_only": False}])

    assert decision("/set_parameter/", facts=unknown) == policy.Decision(
        "confirm", ("parameter_write", "facts_unavailable"))
    assert decision("/set_parameter/", facts=missing) == policy.Decision(
        "confirm", ("parameter_write", "facts_unavailable"))


@pytest.mark.parametrize("parameters", ([],))
def test_missing_element_or_parameters_confirms_with_unavailable_facts(parameters):
    not_found = parameter_facts(parameters, element={"id": 101, "exists": False, "is_type": False,
                                                      "group_member": False, "type_instance_count": 1})
    empty = parameter_facts(parameters)

    assert decision("/set_parameter/", facts=not_found) == policy.Decision(
        "confirm", ("parameter_write", "facts_unavailable"))
    assert decision("/set_parameter/", facts=empty) == policy.Decision(
        "confirm", ("parameter_write", "facts_unavailable"))


def test_group_member_confirms():
    facts = parameter_facts(element={"id": 101, "exists": True, "is_type": False,
                                     "group_member": True, "type_instance_count": 1})

    assert decision("/set_parameter/", facts=facts) == policy.Decision(
        "confirm", ("parameter_write", "group_member"))


def test_modify_with_any_nonempty_parameter_confirms_overwrite():
    facts = parameter_facts([
        {"name": "Comment", "resolved": "instance", "has_value": False, "read_only": False},
        {"name": "Mark", "resolved": "instance", "has_value": True, "read_only": False},
    ])

    assert decision("/modify_element/", facts=facts) == policy.Decision(
        "confirm", ("parameter_write", "overwrites_value"))


def test_empty_confirm_when_overlay_relaxes_parameter_check_to_allow():
    changed = merged_rule("/set_parameter/", {
        "schema": 1,
        "routes": {"/set_parameter/": {"confirm_when": []}},
    })
    facts = parameter_facts(
        [{"name": "Type Mark", "resolved": "type", "has_value": False, "read_only": False}],
        element={"id": 101, "exists": True, "is_type": False, "group_member": False,
                 "type_instance_count": 340},
    )

    assert policy.decide(changed, {}, facts=facts) == policy.Decision("allow", ("parameter_write",))


def test_allow_overlay_relaxes_delete_rule():
    changed = merged_rule("/delete_elements/", {
        "schema": 1,
        "routes": {"/delete_elements/": {"decision": "allow"}},
    })

    assert policy.decide(changed, {}) == policy.Decision("allow", ("delete",))


def test_family_edit_without_shared_parameters_confirms():
    assert decision("/edit_family/", {}) == policy.Decision("confirm", ("edit_family",))


def test_family_edit_with_all_matching_shared_parameters_confirms():
    fop = {"state": "ok", "verdicts": {"Width": "match", "Height": "match"}}
    data = {"add_shared_parameters": ["Width", "Height"]}

    assert decision("/edit_family/", data, fop=fop) == policy.Decision("confirm", ("edit_family",))


@pytest.mark.parametrize("verdict", ("not_in_fop", "name_mismatch", "ambiguous", "unresolved"))
def test_family_edit_rejects_untrusted_shared_parameter(verdict):
    fop = {"state": "ok", "verdicts": {"Width": verdict}}

    assert decision("/edit_family/", {"add_shared_parameters": ["Width"]}, fop=fop) == policy.Decision(
        "deny", ("edit_family", "shared_parameter_source"))


@pytest.mark.parametrize("fop", (None, {"state": "unreadable", "verdicts": {}},
                                 {"state": "not_configured", "verdicts": {}}))
def test_family_edit_rejects_unavailable_fop(fop):
    assert decision("/edit_family/", {"add_shared_parameters": ["Width"]}, fop=fop) == policy.Decision(
        "deny", ("edit_family", "shared_parameter_source"))


@pytest.mark.parametrize("route", ("/load_family/", "/execute_code/", "/delete_elements/", "/transform_elements/"))
def test_always_confirm_routes_ignore_facts(route):
    assert decision(route, facts={"available": False}) == policy.Decision(
        "confirm", rule(route).reasons)


def test_create_routes_and_operator_denials_return_their_literal_rules():
    for active_rule in BASE.rules.values():
        if "create" in active_rule.reasons:
            assert policy.decide(active_rule, {}) == policy.Decision("allow", active_rule.reasons)
    changed = merged_rule("/delete_elements/", {
        "schema": 1,
        "routes": {"/delete_elements/": {"decision": "deny"}},
    })
    assert policy.decide(changed, {}) == policy.Decision("deny", ("delete",))


@pytest.mark.anyio
async def test_authorize_uses_decide_for_facts_unavailable_parameter_and_shared_family_edits(monkeypatch):
    async def current():
        return BASE

    monkeypatch.setattr(policy, "current", current)
    parameter_request = approval.AuthorizationRequest(
        route="/set_parameter/", endpoint="/set_parameter/", data={}, ctx=None, target={}, call=None,
        secret="secret", read_post=None, timeout=1.0)
    family_request = approval.AuthorizationRequest(
        route="/edit_family/", endpoint="/edit_family/", data={"add_shared_parameters": ["Width"]},
        ctx=None, target={}, call=None, secret="secret", read_post=None, timeout=1.0)

    parameter = await approval.authorize(parameter_request)
    family = await approval.authorize(family_request)

    assert parameter.reasons == ("parameter_write", "facts_unavailable", "approval_unavailable")
    assert parameter.audit_fields["reasons"] == ["parameter_write", "facts_unavailable", "approval_unavailable"]
    assert family.reasons == ("edit_family", "shared_parameter_source")
