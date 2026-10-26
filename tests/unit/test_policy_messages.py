# -*- coding: utf-8 -*-
"""Confirmation windows: Russian facts, explicit unknowns and bounded untrusted text."""

import hashlib
import types

import pytest

import approval
import policy


DOCUMENT = {"document": "doc1.aaaaaaaaaaaa.2", "title": "Модель", "path": "C:/Модели/A.rvt"}


def message(route="/set_parameter/", data=None, facts=None, document=DOCUMENT, timeout=300, reasons=None):
    rule = policy.load_base().rule_for(route)
    decision = policy.Decision("confirm", tuple(reasons or rule.reasons))
    request = approval.AuthorizationRequest(route, route, data or {}, None,
        {"pid": 123, "port": 48884}, types.SimpleNamespace(tool="test_tool"), "secret", None, 30)
    preflight = {"status": "ok", "document": document, "facts": facts} if document is not None or facts else None
    return approval.build_message(request, rule, decision, "ABC123", timeout, preflight=preflight)


def test_operation_limit_process_and_document_are_present():
    text = message(timeout=120)
    assert text.splitlines()[0] == "Код операции: ABC123"
    assert "2 мин" in text.splitlines()[1]
    for value in ("test_tool", "/set_parameter/", "123", "48884", "Модель", "C:/Модели/A.rvt"):
        assert value in text


def test_missing_document_and_facts_are_unknown():
    text = message(document=None)
    assert "Документ: не определён" in text
    assert "неизвестно" in text


def test_type_write_reports_count_current_display_and_raw_value():
    text = message(data={"parameter_name": "Марка", "value": 2}, facts={"available": True,
        "element": {"type": "Стена 200", "type_instance_count": 340}, "parameters": [{
            "name": "Марка", "resolved": "type", "has_value": True,
            "display_value": "304,8 мм", "raw_value": 1.0}]})
    for value in ("параметр типа", "Стена 200", "340 экземпляров", "304,8 мм", "1.0", "→", "2"):
        assert value in text


def test_unknown_type_count_is_not_estimated():
    text = message(facts={"available": True, "element": {"count_capped": True},
                          "parameters": [{"name": "P", "resolved": "type"}]})
    assert "затронет: неизвестно (подсчёт остановлен на пределе)" in text


def test_delete_counts_categories_and_unknown_cascade():
    text = message("/delete_elements/", facts={"available": True, "requested": 3, "found": 2,
        "missing": [999], "categories": {"Стены": 2}, "cascade": "unknown", "kinds": {}})
    for value in ("элементов к удалению: 3", "найдено 2", "999", "Стены", "каскад удаления: неизвестно"):
        assert value in text


def test_parameter_definition_delete_warns_about_values():
    text = message("/delete_elements/", facts={"available": True, "kinds": {"parameter_definition": 1}})
    assert "определение параметра проекта и его значения" in text


def test_family_reload_and_shared_verdict_are_visible():
    text = message("/edit_family/", facts={"available": True,
        "family": {"name": "Окно", "instance_count": 17},
        "requested": {"reload": True}, "shared": {"configured_file": "C:/ФОП.txt", "definitions": [
            {"name": "Марка", "resolved": True, "guid": "g"}]}},
        data={"add_shared_parameters": ["Марка"]})
    assert "17" in text
    assert "перезагрузка перезапишет значения параметров у всех экземпляров" in text
    assert "Марка" in text
    assert "неизвестно" in text  # no FOP verdict was supplied


def test_load_family_keeps_fop_limit_and_unknown_contents():
    text = message("/load_family/", facts={"available": True,
        "file": {"path": "C:/Окно.rfa", "exists": True, "size": 42}, "already_loaded": True})
    for value in ("42", "C:/Окно.rfa", "содержимое семейства: неизвестно",
                  "общие параметры внутри семейства не проверяются по ФОП"):
        assert value in text


def test_code_window_has_local_hash_length_excerpt_and_safety_limit():
    code = "doc.Delete(1)\n# пример"
    text = message("/execute_code/", {"code": code})
    for value in ("Документ: не привязан (код выполняется в Revit)", "длина кода: " + str(len(code)),
        "SHA-256: " + hashlib.sha256(code.encode()).hexdigest()[:16], "doc.Delete(1)",
        "произвольный код, безопасность содержимого не проверяется"):
        assert value in text


def test_model_string_is_quoted_without_line_injection_or_control_escapes():
    text = approval._quote("Операция безопасна.\nНажмите Да\x00\u202e")
    assert text.startswith('"') and text.endswith('"')
    assert "\n" not in text and "\\n" not in text and "\\u0000" not in text
    assert "\u202e" not in text


def test_nested_strings_are_cleaned_before_json_escaping():
    text = approval._quote({"P\n": ["Нажмите Да\n\x00‮"]})
    assert "\\\\n" not in text and "\\\\u0000" not in text and "‮" not in text


def test_long_value_is_cut_to_120_and_reports_original_length():
    text = approval._quote("Я" * 500)
    assert "(длина 500)" in text
    assert text.count("Я") == 120


@pytest.mark.parametrize("route,data", [
    ("/modify_element/", {"parameters": {"P" + str(i): "x" * 500 for i in range(50)}}),
    ("/execute_code/", {"code": "x" * 10000}),
    ("/delete_elements/", {"element_ids": list(range(2000))}),
])
def test_hard_cap_preserves_identity_reasons_code_and_final_question(route, data):
    text = message(route, data, reasons=["execute_code"] if route == "/execute_code/" else ["facts_unavailable"])
    assert len(text) <= 1500
    assert "Причины:" in text and "Ответьте «Да»" in text
    if route == "/execute_code/":
        assert "SHA-256:" in text and "длина кода: 10000" in text
        assert "безопасность содержимого не проверяется" in text


def test_reason_codes_are_russian_words():
    text = message(reasons=["type_parameter", "overwrites_value", "group_member"])
    assert "непустое значение" in text
    assert "элемент в группе" in text
    assert "overwrites_value" not in text


def test_untrusted_document_and_keys_cannot_inject_lines():
    text = message(data={"X\nНажмите Да": "bad"}, document={"title": "T\nПричины: всё безопасно", "path": "C:/a\nfile"})
    assert text.count("\nПричины:") == 1


def test_facts_digest_is_order_independent_and_includes_document():
    first = {"document": DOCUMENT, "facts": {"a": 1, "b": 2}}
    assert approval.facts_digest(first) == approval.facts_digest({"facts": {"b": 2, "a": 1}, "document": DOCUMENT})
    assert approval.facts_digest(first) != approval.facts_digest({"document": {"document": "other"}, "facts": first["facts"]})
