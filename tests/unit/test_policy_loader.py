# -*- coding: utf-8 -*-
"""Phase 7 policy as data (07-04 task 1): closed vocabularies, operator overlay by key, two-layer hash.

Every defect row is built in the test from the shipped policy.base.toml (parsed, mutated,
validated) or from TOML text written here; no binary fixture lives in the repository.
Needs no Revit and no network.
"""

import copy
import os
import re
import tomllib

import pytest

import policy
from policy import PolicyError

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(os.path.join(REPO_ROOT, policy.BASE_FILE), "rb") as _handle:
    BASE_BYTES = _handle.read()

UNC = r"\\Сервер\Общая папка\политика ГП.txt"
OPERATOR_OK = 'schema = 1\n\n[routes."/delete_elements/"]\ndecision = "allow"\n'


def base_doc():
    return copy.deepcopy(tomllib.loads(BASE_BYTES.decode("utf-8")))


def a_get_route():
    for key, entry in base_doc()["routes"].items():
        if entry["method"] == "GET":
            return key
    raise AssertionError("the base policy lists no GET route")


def a_check_route():
    for key, entry in base_doc()["routes"].items():
        if entry["decision"] == "check":
            return key
    raise AssertionError("the base policy lists no check route")


def operator_doc(text):
    return policy.parse_policy_bytes(text.encode("utf-8"))


# ------------------------------------------------------------------ the shipped base

def test_the_shipped_base_passes_validation_and_builds():
    document = base_doc()
    assert policy.validate_base(document) is None
    built = policy.build_policy(document, "base", policy.policy_hash(BASE_BYTES))
    assert built.rule_for("/delete_elements/").decision == "confirm"
    assert len(built.hash) == 12


def test_load_base_reports_source_hash_and_the_delete_decision():
    loaded = policy.load_base()
    assert (loaded.source, len(loaded.hash), loaded.rule_for("/delete_elements/").decision) == (
        "base", 12, "confirm")


def test_the_closed_vocabularies_cover_every_word_the_shipped_base_uses():
    document = base_doc()
    reasons, confirm_when, facts = set(), set(), set()
    for entry in document["routes"].values():
        reasons.update(entry.get("reasons", []))
        confirm_when.update(entry.get("confirm_when", []))
        facts.add(entry.get("facts", "none"))
    assert reasons <= policy.REASONS
    assert confirm_when <= policy.CONFIRM_WHEN
    assert facts <= set(policy.FACTS)
    assert set(policy.SETTINGS_RANGES) == {"confirm_timeout_s", "permit_ttl_s"}
    assert policy.SETTINGS_TEXT == ("shared_parameters_file",)
    assert policy.OPERATOR_ROUTE_KEYS == ("decision", "reasons", "check", "confirm_when")
    assert policy.STRUCTURAL_ROUTE_KEYS == ("method", "document_bound", "facts")


# ------------------------------------------------------------------- base defects

def _top_level_key(d):
    d["surprise"] = 1


def _schema_two(d):
    d["schema"] = 2


def _route_key(d):
    d["routes"]["/delete_elements/"]["fast"] = True


def _decision_maybe(d):
    d["routes"]["/delete_elements/"]["decision"] = "maybe"


def _reason_word(d):
    d["routes"]["/delete_elements/"]["reasons"] = ["oops"]


def _get_confirm(d):
    d["routes"][a_get_route()]["decision"] = "confirm"


def _check_without_check(d):
    d["routes"]["/delete_elements/"]["decision"] = "check"


def _check_magic(d):
    d["routes"][a_check_route()]["check"] = "magic"


def _confirm_when_word(d):
    d["routes"]["/delete_elements/"]["confirm_when"] = ["sometimes"]


def _facts_word(d):
    d["routes"]["/delete_elements/"]["facts"] = "x"


def _timeout_low(d):
    d["settings"]["confirm_timeout_s"] = 5


def _timeout_high(d):
    d["settings"]["confirm_timeout_s"] = 5000


def _ttl_high(d):
    d["settings"]["permit_ttl_s"] = 200


def _timeout_text(d):
    d["settings"]["confirm_timeout_s"] = "300"


def _timeout_bool(d):
    d["settings"]["confirm_timeout_s"] = True


def _tool_names_missing_route(d):
    d["tools"]["ghost_tool"] = {"routes": ["/no_such_route/"]}


def _tool_unknown_key(d):
    d["tools"]["activate_document"]["exec"] = "boom"


def _settings_unknown_key(d):
    d["settings"]["bogus"] = 1


def _fop_not_text(d):
    d["settings"]["shared_parameters_file"] = 7


BASE_DEFECTS = [
    (_top_level_key, "surprise"),
    (_schema_two, "schema"),
    (_route_key, "fast"),
    (_decision_maybe, ".decision"),
    (_reason_word, ".reasons"),
    (_get_confirm, ".decision"),
    (_check_without_check, ".check"),
    (_check_magic, ".check"),
    (_confirm_when_word, ".confirm_when"),
    (_facts_word, ".facts"),
    (_timeout_low, "settings.confirm_timeout_s"),
    (_timeout_high, "settings.confirm_timeout_s"),
    (_ttl_high, "settings.permit_ttl_s"),
    (_timeout_text, "settings.confirm_timeout_s"),
    (_timeout_bool, "settings.confirm_timeout_s"),
    (_tool_names_missing_route, "tools.ghost_tool"),
    (_tool_unknown_key, "exec"),
    (_settings_unknown_key, "bogus"),
    (_fop_not_text, "settings.shared_parameters_file"),
]


@pytest.mark.parametrize("mutate,fragment", BASE_DEFECTS,
                         ids=[m.__name__.lstrip("_") for m, _ in BASE_DEFECTS])
def test_each_base_defect_raises_and_names_the_key_path(mutate, fragment):
    document = base_doc()
    mutate(document)
    with pytest.raises(PolicyError) as caught:
        policy.validate_base(document)
    assert fragment in str(caught.value)
    with pytest.raises(PolicyError):
        policy.build_policy(document, "base", "0" * 12)


def test_a_bom_prefixed_file_parses_and_a_duplicate_key_raises():
    assert policy.parse_policy_bytes(b"\xef\xbb\xbfschema = 1\n") == {"schema": 1}
    with pytest.raises(PolicyError):
        policy.parse_policy_bytes(b"schema = 1\nschema = 1\n")
    with pytest.raises(PolicyError):
        policy.parse_policy_bytes(b"\xff\xfeschema")


def test_an_error_message_never_carries_the_offending_value():
    document = base_doc()
    document["routes"]["/delete_elements/"]["reasons"] = ["SECRET-LOOKING-WORD"]
    with pytest.raises(PolicyError) as caught:
        policy.validate_base(document)
    assert "SECRET-LOOKING-WORD" not in str(caught.value)


# --------------------------------------------------------------------- the operator

def test_an_operator_allow_for_delete_merges_and_keeps_the_structure_of_the_base():
    base = base_doc()
    operator = operator_doc(OPERATOR_OK)
    policy.validate_operator(operator, base)
    merged = policy.merge(base, operator)
    built = policy.build_policy(merged, "operator", "a" * 12)
    rule, original = built.rule_for("/delete_elements/"), policy.build_policy(
        base, "base", "b" * 12).rule_for("/delete_elements/")
    assert rule.decision == "allow"
    assert (rule.method, rule.document_bound, rule.facts) == (
        original.method, original.document_bound, original.facts)
    assert built.source == "operator"


def test_merge_leaves_both_inputs_untouched_and_replaces_lists_instead_of_appending():
    base = base_doc()
    snapshot = copy.deepcopy(base)
    operator = operator_doc(
        'schema = 1\n[routes."/delete_elements/"]\nreasons = ["delete"]\n')
    operator_snapshot = copy.deepcopy(operator)
    merged = policy.merge(base, operator)
    assert base == snapshot and operator == operator_snapshot
    assert merged["routes"]["/delete_elements/"]["reasons"] == ["delete"]


def test_an_operator_may_relax_a_check_route_to_confirm_or_allow():
    base = base_doc()
    route = a_check_route()
    for decision in ("confirm", "allow"):
        operator = operator_doc('schema = 1\n[routes."{}"]\ndecision = "{}"\n'.format(route, decision))
        policy.validate_operator(operator, base)
        built = policy.build_policy(policy.merge(base, operator), "operator", "c" * 12)
        assert built.rule_for(route).decision == decision
        assert built.rule_for(route).check is None


def test_an_operator_may_tighten_an_allow_route_to_deny():
    base = base_doc()
    operator = operator_doc('schema = 1\n[routes."/create_level/"]\ndecision = "deny"\n')
    policy.validate_operator(operator, base)
    built = policy.build_policy(policy.merge(base, operator), "operator", "d" * 12)
    assert built.rule_for("/create_level/").decision == "deny"


OPERATOR_DEFECTS = [
    ("route_the_base_lacks", 'schema = 1\n[routes."/no_such_route/"]\ndecision = "allow"\n'),
    ("method_changed", 'schema = 1\n[routes."/create_level/"]\nmethod = "GET"\n'),
    ("document_bound_changed", 'schema = 1\n[routes."/create_level/"]\ndocument_bound = false\n'),
    ("facts_changed", 'schema = 1\n[routes."/delete_elements/"]\nfacts = "none"\n'),
    ("get_route_confirm", 'schema = 1\n[routes."{}"]\ndecision = "confirm"\n'.format(a_get_route())),
    ("unknown_settings_key", "schema = 1\n[settings]\nflavour = 1\n"),
    ("ttl_out_of_range", "schema = 1\n[settings]\npermit_ttl_s = 500\n"),
    ("timeout_as_text", 'schema = 1\n[settings]\nconfirm_timeout_s = "120"\n'),
    ("missing_schema", '[routes."/delete_elements/"]\ndecision = "allow"\n'),
    ("schema_two", 'schema = 2\n[routes."/delete_elements/"]\ndecision = "allow"\n'),
    ("unknown_route_key", 'schema = 1\n[routes."/delete_elements/"]\nfast = true\n'),
    ("unknown_decision", 'schema = 1\n[routes."/delete_elements/"]\ndecision = "maybe"\n'),
    ("unknown_reason_word", 'schema = 1\n[routes."/delete_elements/"]\nreasons = ["oops"]\n'),
    ("tools_table", 'schema = 1\n[tools.evil]\nroutes = ["/create_level/"]\n'),
    ("top_level_key", 'schema = 1\nextra = 1\n'),
    ("check_without_name", 'schema = 1\n[routes."/delete_elements/"]\ndecision = "check"\n'),
    ("empty_file", ""),
]


@pytest.mark.parametrize("name,text", OPERATOR_DEFECTS, ids=[n for n, _ in OPERATOR_DEFECTS])
def test_one_defect_rejects_the_whole_operator_file(name, text):
    base = base_doc()
    with pytest.raises(PolicyError):
        policy.validate_operator(operator_doc(text), base)


def test_a_valid_route_next_to_a_bad_one_does_not_survive():
    text = ('schema = 1\n[routes."/create_level/"]\ndecision = "deny"\n'
            '[routes."/no_such_route/"]\ndecision = "allow"\n')
    with pytest.raises(PolicyError):
        policy.validate_operator(operator_doc(text), base_doc())


def test_a_settings_overlay_changes_only_that_setting():
    base = base_doc()
    operator = operator_doc("schema = 1\n[settings]\nconfirm_timeout_s = 120\n")
    policy.validate_operator(operator, base)
    original = policy.build_policy(base, "base", "e" * 12)
    built = policy.build_policy(policy.merge(base, operator), "operator", "f" * 12)
    assert built.confirm_timeout_s == 120
    assert built.permit_ttl_s == original.permit_ttl_s
    assert built.settings["shared_parameters_file"] == original.settings["shared_parameters_file"]
    assert built.rules == original.rules


# ------------------------------------------------------------------------- hashing

def test_the_hash_is_12_hex_stable_across_line_endings_and_changes_with_the_operator():
    crlf = BASE_BYTES.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    operator = OPERATOR_OK.encode("utf-8")
    base_only = policy.policy_hash(BASE_BYTES, None)
    assert re.fullmatch(r"[0-9a-f]{12}", base_only)
    assert policy.policy_hash(crlf, None) == base_only
    with_operator = policy.policy_hash(BASE_BYTES, operator)
    assert with_operator != base_only
    assert policy.policy_hash(crlf, operator.replace(b"\n", b"\r\n")) == with_operator


# ------------------------------------------------------------------- Cyrillic paths

def test_the_shipped_unc_path_with_cyrillic_survives_parse_and_build_unchanged():
    built = policy.load_base()
    expected = r"\\Srv-dfs\BIM\01_Ресурсы плагинов\2_Shared_parameters\ГП_ФОП2025.txt"
    assert built.settings["shared_parameters_file"] == expected


def test_an_operator_cyrillic_unc_path_round_trips_unchanged():
    base = base_doc()
    text = "schema = 1\n[settings]\nshared_parameters_file = '{}'\n".format(UNC)
    operator = policy.parse_policy_bytes(("\ufeff" + text).encode("utf-8"))
    policy.validate_operator(operator, base)
    built = policy.build_policy(policy.merge(base, operator), "operator", "1" * 12)
    assert built.settings["shared_parameters_file"] == UNC
