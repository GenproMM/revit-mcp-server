---
phase: 02-live-identity-ambiguity-refusal-and-multi-document-addressin
verified: 2026-10-23T12:00:00Z
status: gaps_found
score: 8/9 must-haves verified
covered_files:
  - .planning/REQUIREMENTS.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-01-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-01-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-02-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-02-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-03-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-03-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-04-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-04-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-05-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-05-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-06-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-06-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-07-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-07-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-08-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-08-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-09-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-09-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-10-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-10-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-11-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-11-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-12-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-12-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-13-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-13-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-14-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-14-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-15-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-15-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-16-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-16-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-17-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-17-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-18-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-18-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-19-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-19-SUMMARY.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-20-PLAN.md
  - .planning/phases/02-live-identity-ambiguity-refusal-and-multi-document-addressin/02-20-SUMMARY.md
  - bridge.py
  - revit_mcp/documents.py
  - revit_mcp/identity.py
  - revit_mcp/status.py
  - startup.py
  - tests/test_phase2_live_identity.py
  - tests/unit/tool_manifest.txt
  - tools/document_tools.py
  - tools/target_tools.py
  - tools/utils.py
covered_digest: "v1:sha256:18d6aa6f6055d4e6e5b5cb95c3df365873bef3d5a75b1edce8e94b95c3b92ecb"
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "С видимой идентичностью гипотеза «отвечал другой процесс» для param-write-rolls-back перепроверена вживую, и её исход (подтверждена или опровергнута) записан (ROADMAP SC5 / AMBIG-04)"
    status: failed
    reason: "Классификатор живой приёмки остался в verdict=stop (g6-listing-unusable). Последовательные записи не воспроизвели откат; параллельные ответы перепутались внутри одного Revit (один PID/порт/сессия во всех ответах), одна запись потеряна. Гипотеза «другой процесс» этим прогоном не подтверждена, но и исход G6 классификатором не присвоен. Собственный контракт плана 02-18 (D-14): фаза принимается, только когда каждый критерий observed. Пользователь на блокирующем чекпойнте ответил accept — это зафиксировано как принятие с AMBIG-04 как принятым открытым риском (backlog 999.1), а не как девять наблюдённых критериев."
    artifacts:
      - path: "C:\\Users\\Admin\\Documents\\revit-mcp-phase2-evidence-2026-10-23\\acc.json"
        issue: "g6 section: verdict stop, g6-listing-unusable; воспроизведено командой phase2-classify (PHASE2_ACCEPTANCE_STOP approval=not-granted)"
    missing:
      - "Revit-сторонняя сериализация обработчика pyRevit (backlog 999.1, d27-c) — единственное, что закрывает cross-process overlap; per-process lock его не покрывает"
      - "Повторный G6-прогон после 999.1 (или явный override от пользователя в frontmatter этого файла — см. раздел «Предложение override»)"
deferred:
  - truth: "Мутирующие маршруты, отбрасывающие статус Transaction.Commit() и отвечающие success после тихого отката (REVIEW CR-01, 25 обработчиков, существовало до Phase 2)"
    addressed_in: "Phase 4"
    evidence: "Phase 4 goal: «Every mutating route ... reports what actually happened in Revit rather than an assumed success», требования TRUTH-01..TRUTH-04"
human_verification: []
---

# Phase 2: Live identity, ambiguity refusal, and multi-document addressing — отчёт верификации

**Цель фазы:** каждый ответ можно отнести к конкретному документу в конкретном процессе Revit; два процесса на одном порту дают громкий именованный отказ вместо непредсказуемого ответа; инженер может перечислить, адресовать и переключать документы одной сессии Revit.
**Проверено:** 2026-10-23
**Статус:** gaps_found
**Повторная верификация:** нет, первичная проверка

## Итог

Фаза выполнена почти полностью: 8 из 9 критериев ROADMAP наблюдены вживую и подкреплены кодом и офлайн-тестами. Критерий 5 (AMBIG-04, gate G6) не выполнен: классификатор остался в `stop`. Это принятый пользователем открытый риск, а не удовлетворённое требование. Статус `gaps_found`, а не `passed` и не `human_needed`, по причинам из раздела «Почему именно gaps_found».

## Достижение цели

### Наблюдаемые истины (ROADMAP Success Criteria)

| # | Истина | Статус | Свидетельство |
|---|--------|--------|---------------|
| 1 | `/status/` отдаёт PID, версию Revit, порт, токен сессии (IDENT-01) | VERIFIED | `revit_mcp/identity.py:85-87` формирует `pid`, `actual_port`, `session_token`; живая запись c1: перезапуск Revit меняет PID 63032 на 52588 и токен, старый селектор отказывает с подсказкой. Классификатор: c1 observed |
| 2 | Мутирующий ответ называет изменённый документ, определённый на момент запроса (IDENT-02/03) | VERIFIED | `mutation_document_or_response` в `identity.py:570` вызывается явно в каждом мутирующем обработчике (подтверждено REVIEW: все, кроме `/execute_code/` по D-15 и `/open_model/`); живая запись c2 включает активацию и ручное UI-переключение |
| 3 | Два Revit с `Project1` различимы по полям ответа (IDENT-04) | VERIFIED | живая запись c3: PID 52588:48884 и PID 36764:48885, у обоих несохранённый «Проект1» (локализованный заголовок принят коммитом `4f3bc66`) |
| 4 | Два слушателя на одном порту дают именованный отказ с обоими PID (AMBIG-01/02/03) | VERIFIED с оговоркой | `bridge.listener_snapshot` (bridge.py:247) разбирает полный `netstat -ano -p tcp`; живая запись c4/G5: отказ с PID [8308, 69116], ноль соединений ко второму слушателю. Оговорка: коллизия создана вспомогательным TCP-слушателем (`aux_listener.py`), а не автоназначением порта Revit; SUMMARY фиксирует это явно |
| 5 | Гипотеза «ответил другой процесс» для `param-write-rolls-back` перепроверена с видимой идентичностью, исход записан (AMBIG-04) | FAILED | см. gaps. Классификатор: `stop`; последовательные записи без отката, перекрывающиеся ответы перепутались при одной идентичности, одна запись потеряна |
| 6 | Список документов, явная адресация, отдельный инструмент переключения (MDOC-01/02/04) | VERIFIED | `revit_mcp/documents.py` маршруты `/documents/`, `/activate_document/`, `/document_summary/`, `/document_levels/`; `tools/target_tools.py`, `tools/document_tools.py`; живая запись c6: неактивная запись даёт HTTP 412 `document-not-active`. MDOC-04 сужен до сохранённого нешаренного документа с существующим путём (решение пользователя 2026-10-16) |
| 7 | Сравнение документов из одной сессии без переключения UI (MDOC-01, D-11) | VERIFIED | живая запись c7 / G3: чтения неактивного документа в обоих направлениях без UI-переключения |
| 8 | Мутация без документа следует документированному умолчанию (MDOC-03) | VERIFIED | живая запись c8: один открытый документ, применено к нему; два, HTTP 400 `document-selector-required`; докстринги и инвентаризация в `tests/unit/test_document_contracts.py` |
| 9 | Закрытый после перечисления документ даёт именованную ошибку (MDOC-05) | VERIFIED | живая запись c9: устаревший токен, HTTP 404 `document-closed`, в том числе после замены (новый токен); `identity.py:478` |

**Счёт:** 8/9 истин проверено; `behavior_unverified: 0` (поведенческие истины подтверждены живым наблюдением и офлайн-тестами).

### Поведенчески-зависимые истины

Отмена/порядок/состояние (откаты, закрытие, активация) подтверждены живыми наблюдениями инженера в Revit 2024 (PID 52588, 36764, 8308) и офлайн-инвентаризацией. Свидетельство вне репозитория: `C:\Users\Admin\Documents\revit-mcp-phase2-evidence-2026-10-23\acc.json`. Я воспроизвёл классификацию (read-only), вывод совпал с SUMMARY: c1-c4 и c6-c9 observed, c5 stop, G1-G5 observed, G6 stop, `verdict=stop`. Независимо подтвердить живые наблюдения я не могу: Revit не запускался.

### Отложенные пункты

| # | Пункт | Где закрывается | Свидетельство |
|---|-------|-----------------|---------------|
| 1 | 25 мутирующих обработчиков отбрасывают статус `Commit()` и отвечают success после тихого отката (REVIEW CR-01, существовало до Phase 2) | Phase 4 | Цель Phase 4 и TRUTH-01..04 прямо про честный исход каждого мутирующего маршрута |

Предупреждение: после Phase 2 `format_response` ставит на такие ответы строку «Verified Revit process / document», и ложный success выглядит проверенным. Это не ломает истины Phase 2, но Phase 4 обязана закрыть это до заявлений о честности исходов.

### Артефакты

| Артефакт | Ожидалось | Статус | Детали |
|----------|-----------|--------|--------|
| `bridge.py` (1057 строк) | per-target блокировка, `listener_snapshot`, `parse_target`, отказ при дубле | VERIFIED | существует, содержателен, подключён к инструментам через инъекцию |
| `revit_mcp/identity.py` (706) | идентичность процесса, guard мутации | VERIFIED | pid/actual_port/session_token; коды 400/404/412/503 |
| `revit_mcp/documents.py` (722) | `/documents/`, `/activate_document/`, addressed reads | VERIFIED | 4 маршрута |
| `revit_mcp/status.py` | `/status/` с идентичностью | VERIFIED | идентичность подмешана через `identity_data` |
| `tools/target_tools.py`, `tools/document_tools.py`, `tools/utils.py` | инструменты, рендер идентичности | VERIFIED | в манифесте 59 инструментов, включая документные |
| `tests/test_phase2_live_identity.py` | процедура живой приёмки и классификатор | VERIFIED | классификатор воспроизводит verdict stop |
| `tests/unit/tool_manifest.txt` | манифест | VERIFIED | `activate_document` и документные инструменты присутствуют |

### Ключевые связи

| От | К | Через | Статус |
|----|---|-------|--------|
| `bridge.py` | `/status/` процесса | выбор цели, preflight по `listener_snapshot` | WIRED (живая запись c4) |
| `revit_mcp/*` мутирующие обработчики | `identity.mutation_document_or_response` | явный вызов в каждом обработчике | WIRED (REVIEW: все, кроме D-15 и `/open_model/`) |
| `tools/utils.format_response` | ответ маршрута | рендер подтверждённого процесса и документа | WIRED |

### Покрытие требований

Каждый ID из PLAN frontmatter найден в REQUIREMENTS.md; осиротевших нет (ID Phase 2 в трассировке = 13, все заявлены планами, 02-18 заявляет все 13).

| Требование | Статус | Свидетельство |
|-----------|--------|---------------|
| IDENT-01 | SATISFIED | c1, `identity.py:85-87` |
| IDENT-02 | SATISFIED | c2, guard во всех мутирующих маршрутах |
| IDENT-03 | SATISFIED | c2, повторное разрешение на момент запроса |
| IDENT-04 | SATISFIED | c3 |
| AMBIG-01 | SATISFIED | c4/G5, ранняя проверка слушателей |
| AMBIG-02 | SATISFIED | c4/G5, отказ вместо обращения |
| AMBIG-03 | SATISFIED | c4/G5, PID в сообщении |
| AMBIG-04 | NOT SATISFIED (accepted open risk) | c5/G6 `stop`, 02-18-SUMMARY `requirements-open: [AMBIG-04]`, backlog 999.1 |
| MDOC-01 | SATISFIED | c6, c7 |
| MDOC-02 | SATISFIED | c6 |
| MDOC-03 | SATISFIED | c8 |
| MDOC-04 | SATISFIED на суженном классе | c6, G4; сужено решением пользователя 2026-10-16 |
| MDOC-05 | SATISFIED | c9 |

Бухгалтерия: в `.planning/REQUIREMENTS.md` все 13 пунктов остаются `[ ]` / `Pending`, а в ROADMAP Phase 2 не отмечена `[x]` в списке фаз. Для 12 удовлетворённых требований это устаревшая трассировка (предупреждение, чинится при закрытии фазы). AMBIG-04 должно остаться `Pending`.

### Поведенческие проверки

| Поведение | Команда | Результат | Статус |
|-----------|---------|-----------|--------|
| Офлайн-набор | `uv run pytest tests/unit -q` | 4054 passed, 3 skipped (49 с) | PASS |
| Классификация живой приёмки | `uv run python tests/test_phase2_live_identity.py phase2-classify <acc.json>` | c5 stop, остальные observed, `verdict=stop`, `PHASE2_ACCEPTANCE_STOP approval=not-granted` | PASS (воспроизводит записанный stop) |
| Cold start | по SUMMARY `INIT_LATENCY_S=0.429` | не перезапускался мной | SKIP (по SUMMARY) |

Проверки с живым Revit не выполнялись по условию задачи.

### Анти-паттерны

| Файл | Строка | Паттерн | Серьёзность | Влияние |
|------|--------|---------|-------------|---------|
| маркеры TBD/FIXME/XXX | grep по `bridge.py`, `startup.py`, `main.py`, `revit_mcp/`, `tools/`, процедуре приёмки | не найдено | OK | блокирующих долговых маркеров нет |
| 25 обработчиков `revit_mcp/*` | см. REVIEW CR-01 | `t.Commit()` без чтения статуса | Предупреждение (до Phase 2, отложено в Phase 4) | ложный success с отметкой «Verified» |
| `revit_mcp/code_execution.py` 126-187 | WR-01 | закрытый `StringIO`, висящая транзакция | Предупреждение | вне истин Phase 2 |
| `revit_mcp/placement.py` 921-972, 907-913 | WR-02, WR-03 | success после отката семейства, неверный overload | Предупреждение | вне истин Phase 2 |
| `tools/process_tools.py` 376-456 | WR-04 | workshared `model_path` в командной строке | Предупреждение | вне истин Phase 2 |
| `revit_mcp/worksharing.py` 171-203 | WR-05 | `overwrite_local=True` удаляет произвольный файл | Предупреждение | вне истин Phase 2 |
| IN-01..IN-07 | REVIEW | информационные | Info | не блокируют |

Ревью (quick depth) 1 critical, 5 warning, 7 info носит рекомендательный характер; ни один пункт не опровергает истины 1-4 и 6-9.

### Пропуски запретов (prohibitions)

Все `must_haves.prohibitions` планов 02-08..02-17 помечены самими планами `status: unverified, flagged: true` (judgment-tier). Я не повышаю их до проверенных: это не-авторитетные суждения, рекомендован человеческий просмотр. Косвенное подтверждение: REVIEW подтверждает, что guard вызывается до побочных эффектов и что `parameters.py` сохраняет откат как 409 (в духе запрета «не превращать rolled-back в success»). Не блокирует статус.

### Требуется проверка человеком

Нет новых пунктов. Решение человека по G6 уже принято (`accept` на чекпойнте 02-18), и оно отражено как принятый открытый риск.

## Почему именно gaps_found

- Не `passed`: SC5 / AMBIG-04 не выполнен. Классификатор `stop`, собственный контракт 02-18 требует всех критериев observed. Ответ `accept` пользователя зафиксирован как принятие риска, а не как наблюдение.
- Не `human_needed`: человеческое решение уже получено, нового ручного действия, которое превратило бы stop в observed, не существует. Такая метка скрыла бы реальный незакрытый пробел.
- Не override: в frontmatter `overrides:` пусто, а решение пользователя сформулировано как принятие риска чекпойнта, а не как приёмка отклонения от SC5. Я не создаю override за пользователя.
- Не `deferred`: backlog 999.1 не входит в поздние фазы этого milestone (Phase 3-7), и его требования `TBD`, поэтому по правилу консервативного сопоставления пробел остаётся реальным.

Существенный оттенок для решения: по тексту SC5 «исход (подтверждена или опровергнута) записан» прогон дал содержательные данные. Идентичность была постоянной, значит версия «другой процесс» не подтверждена; перепутывание внутри одного Revit совпадает со вторым кандидатом отладки (999.1). Но это вывод по одному одноразовому прогону, классификатор исход не присвоил, и AMBIG-04 в SUMMARY честно оставлен открытым. Я следую этому, а не смягчаю.

### Предложение override (если пользователь хочет закрыть SC5 формально)

Только по явному решению пользователя добавить в frontmatter:

```yaml
overrides:
  - must_have: "С видимой идентичностью гипотеза «отвечал другой процесс» для param-write-rolls-back перепроверена вживую, и её исход записан"
    reason: "Прогон G6 один раз, классификатор stop; wrong-process не подтверждена (одна идентичность), cross-wire внутри одного Revit закрывается backlog 999.1; AMBIG-04 остаётся открытым"
    accepted_by: "<имя пользователя>"
    accepted_at: "<ISO timestamp>"
```

Даже при override AMBIG-04 в REQUIREMENTS.md не должен отмечаться выполненным.

## Краткий список пробелов

1. **BLOCKER (принят как открытый риск):** SC5 / AMBIG-04 / G6 в `stop`; закрывается backlog 999.1 и повторным G6.
2. **WARNING:** REQUIREMENTS.md и ROADMAP не синхронизированы: 12 выполненных требований `Pending`, Phase 2 не отмечена `[x]`.
3. **WARNING:** CR-01 (25 обработчиков глотают статус `Commit()`) теперь маскируется строкой «Verified»; закрыть в Phase 4.
4. **WARNING:** G5 подтверждён на вспомогательном слушателе, не на автоназначении порта Revit; workshared-отказ (G4) не запускался из-за отсутствия модели.
5. **INFO:** на диске остались тестовые копии `MCP_TEST_nofile*_221026.rvt` в Documents (по SUMMARY).

---

_Проверено: 2026-10-23_
_Верификатор: Claude (gsd-verifier)_
