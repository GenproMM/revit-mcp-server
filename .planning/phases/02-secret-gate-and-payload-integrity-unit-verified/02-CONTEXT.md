# Phase 2: Secret gate and payload integrity (unit-verified) - Context

**Gathered:** 2026-09-23
**Status:** Ready for planning
**Mode:** `--auto` — все серые зоны выбраны автоматически, по каждому вопросу принят рекомендованный вариант (по поручению пользователя). Альтернативы — в `02-DISCUSSION-LOG.md`.

<domain>
## Phase Boundary

Логика, которая отклонит мутацию без секрета и обнаружит расхождение payload `revit_mcp/` с
эталоном, существует, покрыта unit-тестами и генерируется сборочным конвейером — но **не
подключена** к живому маршруту. Подключение (`startup.py`, обёртка `api.route`) — работа фазы 4.
Требования: SEC-01…SEC-08, INTG-01…INTG-08 (становятся наблюдаемо истинными только после фазы 4).

Вне фазы: правка `startup.py`, отправка секрета клиентом в живых вызовах, восстановление файлов
(RESTORE — будущий офлайн-скрипт), политика разрешений.

</domain>

<decisions>
## Implementation Decisions

### Конверт запроса и секрет в теле
- **D-01:** Секрет едет в теле `text/plain` JSON под одним зарезервированным ключом-конвертом
  `_mcp`: `{"_mcp": {"secret": "..."}, <поля домена>}`. Никаких HTTP-заголовков (SEC-02, решение
  STATE.md). Тот же конверт позже несёт `document` (фаза 4) и `call_id` (фаза 5) — один
  контракт вместо трёх. — **Reversibility:** costly — ключ `_mcp` становится протоколом между
  двумя половинами; смена требует синхронного обновления payload и расширения на всём парке.
- **D-02:** Чистая функция `split_envelope(raw) -> (envelope, payload)` принимает bytes/str/dict
  через `parse_request_data()` и возвращает payload **без** ключа `_mcp`. Фаза 4 передаёт
  обработчику очищенный payload, чтобы секрет не оказался ни в локальных переменных
  обработчика, ни в его traceback.
- **D-03:** Шлюз секрета предназначен для **всех POST-маршрутов** (решение по методу при
  регистрации), никогда для GET. `/status/` и все чтения остаются открытыми (SEC-05).

### Сравнение за постоянное время
- **D-04:** Одна чистая реализация `secret_matches(provided, expected)` для обеих половин:
  оба значения нормализуются в UTF-8 bytes, хешируются SHA-256, 32-байтовые дайджесты
  сравниваются XOR-накоплением без раннего выхода. Хеширование заранее выравнивает длину, поэтому
  длина секрета тоже не утекает. Выбрано вместо `CryptographicOperations.FixedTimeEquals`
  (зависит от версии CLR в pyRevit) и `hmac.compare_digest` (вероятно отсутствует в IronPython 3):
  одна функция, проверяемая под CPython, без CLR-вопроса. Это «ручная реализация с
  задокументированной причиной» из критерия 2. Нужна одна живая проверка, что `hashlib.sha256`
  работает под `IPY342` — через `/execute_code/`, без перезапуска Revit.
- **D-05:** Результат проверки — одна из строк `ok` / `missing` / `mismatch` /
  `server_not_configured`. Любое исключение внутри сравнения даёт `mismatch` без текста,
  содержащего значения. В функции нет других локальных переменных с секретом рядом с
  возможным местом исключения (SEC-06).
- **D-06:** Отказ строит один чистый помощник `auth_failure(reason) -> (data, 401)`:
  `{"error": "Mutation rejected: shared secret <reason>", "auth": "<reason>"}`. Код **401** —
  отличен от 409 (`rolled_back`) и 503 (нет документа). Секрет не попадает в ответ ни в каком
  виде. Пара тестов в `tests/unit/test_format_response.py` в стиле существующей пары
  `rolled_back`: `Error: 401 - ...` доходит до модели видимой ошибкой; тест-сигнал, что словарь
  `{"auth": ...}` сам по себе не распознаётся как отказ — поэтому сигнал несёт код 401.

### Генерация и хранение секрета
- **D-07:** Секрет **стабильный, а не новый на каждую сборку.** Создаётся один раз
  (`secrets.token_urlsafe(32)`) сборочным инструментом, если файла ещё нет, и хранится вне git по
  пути `MCP_SECRET_FILE` из `deploy/config.cmd` (по умолчанию вне публикуемых деревьев `ext\` и
  `payload\`). Каждая сборка копирует одно и то же значение в оба артефакта. Причина: `update.cmd`
  обновляет payload, пока Revit держит загруженным старое расширение; новый секрет на каждую
  сборку отключал бы все мутации до перезапуска Revit на каждой станции. Ротация — осознанное
  действие: удалить файл, пересобрать обе половины, перезапустить Revit. — **Reversibility:**
  reversible — переход на секрет-на-сборку меняет только сборочный скрипт.
- **D-08:** Артефакт секрета — файл `_bridge_secret` (без расширения; ведущее подчёркивание
  исключает его из обнаружения доменов): в расширении `revit_mcp/_bridge_secret`, в payload
  `app/_bridge_secret` рядом с `bridge.py`. Обе половины читают файл при загрузке. Нет файла на
  стороне Revit → `server_not_configured`, мутации отклоняются (fail-closed). Нет файла на стороне
  CPython → секрет не отправляется, Revit отвечает 401 `missing` с подсказкой.
- **D-09:** Dev-машина с junction: `scripts/dev_secret.py` создаёт один `revit_mcp/_bridge_secret`
  в рабочем дереве; `bridge.py` ищет секрет сначала рядом с собой, затем в
  `revit_mcp/_bridge_secret` — на dev обе половины читают один файл и не могут разойтись.
  `.gitignore` получает `_bridge_secret` и `_manifest.json`.
- **D-10:** Проверка пары при сборке: `build-payload.cmd` (через `gate.py`) и
  `publish-extension.cmd` каждый сверяют свой артефакт с `MCP_SECRET_FILE` (не пусто и байт в
  байт) — критерий 7. Отправка секрета из `bridge.py` в живых вызовах включается только в фазе 4;
  в этой фазе строятся и тестируются `load_secret()` и построитель конверта.

### Манифест целостности
- **D-11:** Манифест — `_manifest.json` в корне расширения (рядом с `startup.py`, **не** внутри
  `revit_mcp/`). Схема: `{"schema": 1, "generated_at", "commit": <git sha>, "files":
  {"startup.py": sha256, "extension.json": sha256, "revit_mcp/<name>.py": sha256, ...}}`. Список
  файлов берётся из `git ls-files` (tracked), хеши считаются с **копий в DEST** после robocopy —
  манифест описывает ровно то, что опубликовано. Генерирует Python-скрипт
  `deploy/make_manifest.py`, вызываемый из `publish-extension.cmd` сразу после копирования
  `revit_mcp`. — **Reversibility:** costly — схема читается расширением на парке; смена требует
  поля `schema` (оно заложено) и совместимого читателя.
- **D-12:** Нормализация хеша: содержимое файла с CRLF→LF перед SHA-256 (INTG-06). Проверяются
  только `.py`/`.json` из манифеста. Игнорируются `__pycache__`, `*.pyc`, файлы с `_` без `.py`
  (`_bridge_secret`, `_manifest.json`), артефакты редактора. **Лишний** `.py` в `revit_mcp/`,
  которого нет в манифесте, — расхождение (`unexpected`), потому что обнаружение доменов
  зарегистрирует его как домен.
- **D-13:** Три состояния: `verified_match` / `verified_mismatch` (списки `modified`, `missing`,
  `unexpected`) / `unverifiable` (причина `manifest_missing` | `manifest_unreadable` |
  `read_error`). Чистая функция `evaluate_integrity(manifest, observed)` плюс тонкий читатель
  файлов. Код проверки **никогда не пишет файлы** (INTG-03) — тест это доказывает.
- **D-14:** Dev junction: `_manifest.json` в репозитории нет → `unverifiable(manifest_missing)`
  → мутации разрешены, `/status/` сообщает состояние (INTG-07, INTG-08). Мутации блокирует только
  `verified_mismatch` (INTG-04, включается в фазе 4).
- **D-15:** Отказ при расхождении — HTTP **423** `{"error": "...", "integrity":
  "verified_mismatch", "files": [...]}`; отличен от 401/409/503. Чтения и `/status/` продолжают
  работать.

### Бинд не на loopback (SEC-07)
- **D-16:** Чистый классификатор `classify_listeners(endpoints, port)` → `loopback_only` /
  `exposed` / `unknown`; сторона Revit собирает эндпоинты через .NET
  `IPGlobalProperties.GetActiveTcpListeners()` (тонкий вызов, подключается в фазе 4).
  `exposed` → `/status/` сообщает `bind: exposed` и `health: degraded`, но мутации **не
  блокируются**: сетевой барьер — секрет, `pyrevit configs routes` не умеет ставить host, а
  блокировка отключила бы пилотную станцию на `0.0.0.0`. Расхождение с формулировкой
  PROJECT.md Active («работа при 0.0.0.0 невозможна») записано: действует формулировка SEC-07,
  принудительный бинд отложен.

### Размещение кода
- **D-17:** Чистая логика (конверт, сравнение секрета, оценка целостности, классификатор бинда)
  живёт в новом `revit_mcp/trust.py` — по тем же правилам, что `textutils.py`: ничего не
  импортирует из pyRevit, IronPython-диалект (без f-strings), тестируется из `tests/unit/`.
  `CLAUDE.md` дополняется: общие чистые помощники — `textutils.py` и `trust.py`. Тонкие
  pyRevit-зависимые обёртки (`revit_mcp/integrity.py`, `revit_mcp/security.py`) — модули-помощники
  без регистратора; в этой фазе создаётся только читатель файлов для целостности, установщик
  обёртки — в фазе 4. `scripts/conventions.py` и `test_conventions.py` должны принимать новые файлы.

### Claude's Discretion
- Имена функций и полей сверх зафиксированных выше, тексты сообщений об ошибках.
- Точное значение `MCP_SECRET_FILE` по умолчанию на сборочной машине.
- Разделение тестов по файлам (`test_trust.py` и т.п.).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Объём и требования
- `.planning/ROADMAP.md` §Phase 2 — цель и 8 критериев
- `.planning/REQUIREMENTS.md` §Секрет и сеть (SEC), §Целостность (INTG), §Out of Scope (самовосстановление, секрет на станцию, Authenticode)
- `.planning/STATE.md` §Decisions — секрет в теле, проверка только обнаруживает

### Исследование
- `.planning/research/PITFALLS.md` §Pitfall 1 (401 против silent success), §Pitfall 3 (хеши и CRLF/pycache), §Pitfall 4 (недоступность ≠ повреждение), §Pitfall 9 (`/status/` открыт), §Pitfall 10 (bytes/str в сравнении)
- `.planning/research/ARCHITECTURE.md` §Question 4 и §Build pipeline — место манифеста и секрета в `publish-extension.cmd` / `config.cmd`
- `.planning/research/STACK.md` — `hashlib.sha256` на обоих рантаймах

### Код
- `revit_mcp/textutils.py:98` — `parse_request_data()`, единственный путь разбора тела
- `tests/unit/test_format_response.py:151-190` — образец пары тестов `rolled_back`
- `deploy/config.cmd`, `deploy/build-payload.cmd:109-124`, `deploy/publish-extension.cmd:35-70`, `deploy/gate.py`
- `startup.py:37-57` — правила обнаружения (файлы с `_` не сканируются)
- `scripts/conventions.py` — проверки диалекта, которым должен соответствовать `trust.py`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `parse_request_data()` — уже покрыт тестами для bytes/str/dict; конверт разбирается только через него.
- Пара тестов `rolled_back` в `test_format_response.py` — шаблон для пары 401.
- `publish-extension.cmd` уже имеет жёсткий gate (`default_enabled`/`builtin`) — туда же встаёт проверка секрета и манифеста.

### Established Patterns
- Обнаружение доменов пропускает файлы с `_` — `_bridge_secret` и соседние артефакты не станут доменами.
- Детект рантайма — только `if bytes is str:` (никогда через `unicode`).
- Чистые помощники Revit-половины тестируются из CPython (`textutils.py`) — `trust.py` повторяет схему.

### Integration Points
- Фаза 4: `startup.py` вызывает проверку целостности до импорта доменов и ставит обёртку `api.route`, использующую `split_envelope`, `secret_matches`, `auth_failure`.
- Фаза 4: `bridge.py` начинает класть конверт `_mcp` в тело каждого POST.

</code_context>

<specifics>
## Specific Ideas

- `/status/` должен различать три причины 401: клиент ничего не прислал, сервер не настроен, значения не совпали — не раскрывая сам секрет (из Pitfall 9).

</specifics>

<deferred>
## Deferred Ideas

- Принудительный бинд Routes на 127.0.0.1 на этапе установки — после того как появится надёжный способ задать host в конфиге pyRevit.
- Восстановление разошедшихся файлов (RESTORE-01/02) — отдельный офлайн-скрипт, будущий milestone.
- Секрет-на-сборку с ротацией при каждом релизе — только если стабильный секрет окажется недостаточным.

</deferred>

---

*Phase: 02-secret-gate-and-payload-integrity-unit-verified*
*Context gathered: 2026-09-23*
