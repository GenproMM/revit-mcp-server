---
tags: [debugging, classifier, localization, phase-2, ru-RU]
date: 2026-10-23
---

# Классификатор требовал Project1, а русский Revit называет первый проект Проект1

**Симптом.** После двухпроцессной проверки блок `two` стал STOP с причиной `two-no-project1`: «process N lists no unsaved document titled Project1». На стенде два процесса, у обоих неsaved документ, но его название «Проект1».

**Причина.** `_unit_two` в `tests/test_phase2_live_identity.py` сравнивал название строго с `"Project1"`. Это та же ru-RU-ловушка, что и у парсера netstat ([[netstat на ru-RU Windows печатает заголовки в cp866, строгий парсер возвращал None]]).

**Исправление.** Коммит `4f3bc66`: константа `UNSAVED_DEFAULT_TITLES = ("Project1", "Проект1")`, RED-тест первым; сохранённый документ и произвольное имя по-прежнему отвергаются. 4054 теста зелёные.
