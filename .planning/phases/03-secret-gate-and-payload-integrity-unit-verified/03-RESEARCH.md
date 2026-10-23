# Phase 3: Secret gate and payload integrity (unit-verified) - Research

**Researched:** 2026-10-23
**Domain:** Pure trust logic (shared-secret check, request envelope, file-integrity evaluation, bind classification) for a dual-runtime Revit MCP bridge, plus the Windows build pipeline that generates the secret and the hash manifest. Inert by design: nothing in this phase is wired into a live route.
**Confidence:** HIGH on repo facts and test seams (all opened and read this session); MEDIUM on IronPython 3 runtime behaviour (one live gate outstanding, D-04); HIGH on the `FixedTimeEquals` finding (Microsoft docs).

<user_constraints>
## User Constraints (from CONTEXT.md)

> Copied verbatim from `03-CONTEXT.md` (gathered 2026-09-23, **old phase numbering** — "фаза 4" there means the current Phase 5 live wiring; "фаза 4 carries `document`" is superseded by shipped Phase 2, see "Conflicts" below). The Russian text is deliberately not translated.

### Locked Decisions

#### Конверт запроса и секрет в теле
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

#### Сравнение за постоянное время
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

#### Генерация и хранение секрета
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

#### Манифест целостности
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

#### Бинд не на loopback (SEC-07)
- **D-16:** Чистый классификатор `classify_listeners(endpoints, port)` → `loopback_only` /
  `exposed` / `unknown`; сторона Revit собирает эндпоинты через .NET
  `IPGlobalProperties.GetActiveTcpListeners()` (тонкий вызов, подключается в фазе 4).
  `exposed` → `/status/` сообщает `bind: exposed` и `health: degraded`, но мутации **не
  блокируются**: сетевой барьер — секрет, `pyrevit configs routes` не умеет ставить host, а
  блокировка отключила бы пилотную станцию на `0.0.0.0`. Расхождение с формулировкой
  PROJECT.md Active («работа при 0.0.0.0 невозможна») записано: действует формулировка SEC-07,
  принудительный бинд отложен.

#### Размещение кода
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

### Deferred Ideas (OUT OF SCOPE)
- Принудительный бинд Routes на 127.0.0.1 на этапе установки — после того как появится надёжный способ задать host в конфиге pyRevit.
- Восстановление разошедшихся файлов (RESTORE-01/02) — отдельный офлайн-скрипт, будущий milestone.
- Секрет-на-сборку с ротацией при каждом релизе — только если стабильный секрет окажется недостаточным.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-01 | Мутирующие маршруты требуют общий секрет; запрос без верного секрета отклоняется до открытия транзакции | `check_secret()` / `auth_failure()` in `revit_mcp/trust.py` (pure, unit-proven). Live "before any transaction" is Phase 5; the Phase 2 chokepoint is the per-handler guard in `identity.py`, not a `startup.py` wrapper (Conflict C2). |
| SEC-02 | Секрет едет в теле `text/plain` + `parse_request_data()` | `split_envelope()` routes through `parse_request_data` (`revit_mcp/textutils.py:231`); CPython-side envelope builder in `bridge.py`; no header path. Test: bytes/str/dict inputs. |
| SEC-03 | Отказ по секрету — не-200, видимая ошибка | `auth_failure()` returns status 401; paired tests in `tests/unit/test_format_response.py` modelled on the `rolled_back` pair (note the `error` key nuance, Pitfall 7). |
| SEC-04 | Сравнение за постоянное время на обеих половинах | D-04 hash-then-XOR; structural (not timing-measured) proof; `FixedTimeEquals` ruled out by docs (Conflict C3). Only the CPython unit run + the CLR-independent design: "both halves" = one module executed under CPython tests and simulated IronPython conditions. |
| SEC-05 | Чтения и `/status/` без секрета | Gate is a method-level decision (D-03). Phase 3 proves it with a pure `gate_applies(method)` or by test that the helper exposes no GET path; live is Phase 5. |
| SEC-06 | Секрет не попадает в журнал, лог, текст ошибки | Narrow compare function, `except Exception` returns without text, no logging in `trust.py`; caplog + monkeypatched-failure tests; client-side envelope builder never stringifies the body. |
| SEC-07 | Бинд не на loopback обнаруживается и сообщается | `classify_listeners(endpoints, port)` pure; the .NET collection call is Phase 5. |
| SEC-08 | Секрет генерируется и внедряется при сборке; пара согласована | `deploy/secret_tool.py` (create-if-missing, stage into both artifacts, byte-equal verify); `MCP_SECRET_FILE` in `config.cmd`; `/XF` exclusions so a dev secret is never published. |
| INTG-01 | Манифест хешей формируется при сборке | `deploy/make_manifest.py` called from `publish-extension.cmd` right after the `revit_mcp` robocopy; file list from `git ls-files -z`. |
| INTG-02 | Расхождение обнаруживается при загрузке расширения | `evaluate_integrity` + reader (`revit_mcp/integrity.py`) built and unit-proven; invocation from `startup.py` is Phase 5. |
| INTG-03 | Проверка не пишет файлы | Read-only reader; test with write-guards on `open`/`os`/`shutil` plus directory snapshot before/after plus AST scan. |
| INTG-04 | При расхождении мутации отклоняются, чтения работают | `integrity_failure(files)` -> `(data, 423)` pure helper; blocking is Phase 5. |
| INTG-05 | `/status/` называет разошедшиеся файлы | Result dict carries sorted `modified` / `missing` / `unexpected` lists; rendering in `/status/` is Phase 5. |
| INTG-06 | Нет ложных срабатываний на `__pycache__`, `.pyc`, переводах строк, артефактах редактора | Hash normalization (CRLF->LF), manifest from tracked files, reader ignores non-`.py`/`.json`; table-driven tests. |
| INTG-07 | Недоступность эталона не равна повреждению | Three-state model; `read_error` only for non-ENOENT I/O errors; property test: no input turns unreachable into mismatch. |
| INTG-08 | На dev-junction проверка не мешает | `_manifest.json` absent in repo -> `unverifiable(manifest_missing)`; test runs the reader on the real `REPO_ROOT`; `make_manifest.py` refuses `--dest` equal to the repo. |
</phase_requirements>

## Summary

Phase 3 is a pure-logic-plus-build-tooling phase. Nothing was found partially implemented: a repo-wide search for `trust.py`, `_bridge_secret`, `_manifest.json`, `secret_matches`, `split_envelope`, `evaluate_integrity`, `make_manifest`, `auth_failure`, `classify_listeners` matches only planning documents. The unit baseline today is **4054 passed, 3 skipped in 22 s** (`uv run pytest tests/unit`, Python 3.13.7, uv 0.11.1), so every new test has a fast, stable home. Phase 3 adds no external packages (standard library only).

The decisions in 03-CONTEXT.md hold up against the shipped code with **three exceptions that must be acknowledged by the planner/user** (full detail in "Conflicts"): (C1) Phase 2 shipped the target document as a **flat top-level `document` key**, not inside an envelope, so D-01's forward-looking clause "the same envelope later carries `document`" is superseded — `_mcp` and `document` are disjoint keys, so there is no collision and `_mcp` stays secret-only; (C2) Phase 2 explicitly forbids a `startup.py` handler wrapper (G1, enforced by `tests/unit/test_phase2_inventory.py:597`), so the Phase 5 wiring described in D-02/D-17 and ROADMAP Phase 5 must instead go through the per-handler guard in `revit_mcp/identity.py`; Phase 3 must therefore expose composable pure functions rather than a decorator; (C3) the `.planning/research/STACK.md` claim that `CryptographicOperations.FixedTimeEquals` exists on every runtime Revit 2024-2027 hosts is wrong: Microsoft lists it only for .NET Core 2.1+/.NET 5+/.NET Standard 2.1, and Revit 2024 runs .NET Framework 4.8 — which independently confirms D-04's hand-rolled compare.

Three build-pipeline traps are specific to this repo: `publish-extension.cmd` robocopies the whole `revit_mcp/` directory, which would publish a developer's gitignored `revit_mcp/_bridge_secret` (D-09) unless excluded; `build-payload.cmd` ships only an explicit list of root modules, so CPython-side secret code must live in `bridge.py` (the payload contains no `revit_mcp/`, so it cannot import `trust.py`); and working-tree line endings are mixed (`i/lf w/crlf` for some files, `w/lf` for others, `core.autocrlf=true`), which is exactly why CRLF-normalized hashing (D-12) is mandatory, not optional.

**Primary recommendation:** Build `revit_mcp/trust.py` (pure, 3.4-dialect) and `revit_mcp/integrity.py` (read-only reader) test-first; put the CPython client half (`load_secret`, `with_envelope`) inside `bridge.py`; generate secret and manifest with two stdlib Python tools (`deploy/secret_tool.py`, `deploy/make_manifest.py`) called from the existing `.cmd` scripts with `/XF _bridge_secret _manifest.json` added to the extension robocopy; keep `startup.py`, every route and the live send path untouched; and make the one D-04 live `/execute_code/` check an explicit human checkpoint.

## Conflicts between locked decisions and shipped code (planner/user must acknowledge)

| # | Locked text | Shipped reality (evidence) | Impact / recommendation |
|---|-------------|----------------------------|-------------------------|
| C1 | D-01: "Тот же конверт позже несёт `document` (фаза 4) и `call_id` (фаза 5)" | Phase 2 carries `document` as a **flat top-level key**: `tools/editing_tools.py:63-66` `data = {"element_ids": element_ids}` / `if document is not None:` / `data["document"] = document` / `response = await revit_post("/delete_elements/", data, ctx, **_target_options(target))`. Server side: `revit_mcp/identity.py:634` `if not isinstance(data, dict) or "document" not in data:` (in `request_document_selector`, 616-637) and `revit_mcp/documents.py:570` `return data.get("document"), None`. The process `target` is **not in the body** at all: it is a `revit_post(..., target=...)` argument that selects the incarnation/client (`bridge.py:803`, `_dispatch(... target)` at 963-983). `[VERIFIED: files read this session]` | `_mcp` and `document` do **not** collide (disjoint top-level keys; `grep` for a `"_mcp"` literal in `tools/`, `revit_mcp/`, `bridge.py`, `main.py`, `tests/` finds none). **Keep `_mcp` secret-only now** (extensible for `call_id`/Phase 7 approval); do **not** migrate `document` into it (31 `data["document"]` sites in `tools/` plus every guard would change for no gain). The forward clause of D-01 is superseded by shipped Phase 2; the locked part (reserved `_mcp` key, no headers) is unaffected. Needs user acknowledgement that the "one contract instead of three" aspiration is dropped for `document`. |
| C2 | D-02 / D-17 / Integration Points: Phase 5 "`startup.py` ставит обёртку `api.route`, использующую `split_envelope`…"; ROADMAP Phase 5 goal: "wired into the live request chokepoint in `startup.py` (the same one Phase 2 uses for identity)" | Phase 2 chose **explicit per-handler guards** (G1). `revit_mcp/identity.py:581-583`: "Explicit per-handler call only (G1): no wrapper or decorator is installed in startup.py." Enforced by `tests/unit/test_phase2_inventory.py:597-616` `test_startup_installs_no_common_handler_wrapper` (forbids any `api.<attr>`, decorated functions, `wraps`, `setattr`, `functools` in `startup.py`). The chokepoint is `mutation_document_or_response(...)` in `identity.py:570`, called first in each mutating handler (31 guarded mutations per STATE.md 02-17). | **Phase 3 is unaffected** (no `startup.py` edit; do not touch it, that test would fail). It shapes the Phase 3 API: expose small composable pure functions (`split_envelope`, `check_secret`, `auth_failure`, `evaluate_integrity`, `integrity_failure`) usable from a guard, not a decorator. D-02's premise "handler receives cleaned payload" does not hold with per-handler guards, because each handler re-parses `request.data` itself (`parse_request_data(request.data)`); Phase 5 must decide: guard rewrites `request.data`, or accepts that the raw body (with `_mcp`) stays in `request.data`. Note Python tracebacks print source lines, not local values, so D-02's traceback rationale is weaker than assumed. Flag for Phase 5 discuss; no Phase 3 action beyond keeping `split_envelope` as locked. |
| C3 | ROADMAP SC2 / STATE.md Blockers: "whether `CryptographicOperations.FixedTimeEquals` exists on pyRevit's hosted CLR ... requires the live CLR-availability check"; STACK.md: "predates .NET Core 2.1, so it is present on every .NET runtime version Revit 2024-2027 could plausibly host" | Microsoft docs monikers for `CryptographicOperations.FixedTimeEquals`: netcore-2.1 ... netcore-3.1, netstandard-2.1, net-5.0 ... net-11.0; **.NET Framework is not listed**; parameters are `ReadOnlySpan<byte>`, not `byte[]`. Revit 2024 and earlier use .NET Framework 4.8; Revit 2025+ use .NET 8. `[CITED: learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.cryptographicoperations.fixedtimeequals]` `[CITED: forums.autodesk.com Revit API forum / blog.autodesk.io "Revit 2025 .NET 8"]` Live bench was Revit 2024.3.30 (bridge.py module docstring). | STACK.md is wrong on this point; D-04's hand-rolled compare is the correct branch of SC2 ("hand-rolled fixed-length compare with a documented fallback reason"). Record the reason in the function docstring and CONTEXT. The literal SC2 wording asks for a live CLR check; recommend the planner treat the cited docs as the evidence for the fallback branch and bundle a free `Type.GetType` probe into the same live snippet (below) so the claim is also observed, not only cited. |
| C4 | D-06: "тест-сигнал, что словарь `{"auth": ...}` сам по себе не распознаётся как отказ" | `tools/utils.py:169-170`: `has_error = (bool(response.get("error")) or status in ("error", "failed", "failure", "exception"))`. `auth_failure()`'s own dict carries a truthy `"error"` key, so as a **dict** it **is** recognised as a failure (unlike `rolled_back`, whose dict has no `error` key). | The paired test must use the `auth`-only dict (error key removed) for the alarm assertion, and separately assert the real `auth_failure()` body renders as an error whether it arrives as a dict or as `Error: 401 - ...`. See Pitfall 7. |
| C5 | D-07/D-08 put the secret in the extension tree published to the share; `publish-extension.cmd:10-12` says the point of publishing a copy is to keep material "off a department-readable share" | The shared secret in `ext\` on the share is readable by everyone who can read the share; REQUIREMENTS Out of Scope already excludes local bypass ("Рубеж сетевой, не локальный"). | Not a violation, but state it plainly in docs: the secret is a network barrier, not protection against any fleet user. Open Question 1 (share ACL / default `MCP_SECRET_FILE` location). |
| C6 | ROADMAP SC7: "`deploy/config.cmd` or equivalent generates one shared secret" | `deploy/config.cmd` is `call`ed by both scripts and only `set`s variables (lines 26, 31, 42). A `.cmd` cannot generate a CSPRNG token reliably. | `config.cmd` defines `MCP_SECRET_FILE`; generation is `deploy/secret_tool.py` (CPython, stdlib `secrets`), which satisfies "or equivalent". |

Staleness already noted by the orchestrator and confirmed: phase numbers inside 03-CONTEXT.md use the old numbering (live enforcement = Phase 5, not 4); Phase 2 is closed (git log `42c80b4`, `74b19a6`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Secret compare, result states, `auth_failure` body | Revit extension, pure helper (`revit_mcp/trust.py`) | CPython unit suite (runs it) | Only the Revit side ever compares; the CPython side only sends. Pure so CPython tests prove it. |
| Envelope split (`_mcp`) | Revit extension, pure helper | CPython `bridge.py` builds it | `split_envelope` is server-side; `with_envelope` is the client half and lives in `bridge.py` (payload has no `revit_mcp/`). |
| Secret file loading | Both halves, duplicated small functions | Build pipeline places the files | Payload cannot import `revit_mcp`; parity test pins identical behaviour. |
| Integrity evaluation | Revit extension, pure (`trust.py`) | Reader `revit_mcp/integrity.py` (filesystem I/O only) | Evaluation is pure; reading files is the only I/O; no writes ever. |
| Manifest generation | Build pipeline (`deploy/make_manifest.py`) | Reuses `revit_mcp.integrity.hash_normalized` | One hashing implementation shared by generator and runtime reader prevents drift. |
| Secret generation / pair verification | Build pipeline (`deploy/secret_tool.py`) | `deploy/gate.py` (payload-side check) | Needs CSPRNG and byte-equal verify on the build server. |
| Bind classification | Revit extension, pure | Live .NET collection call: Phase 5 | `classify_listeners` is pure over `(host, port)` pairs. |
| Live enforcement (gate in handlers, 401/423 emission, `/status/` reporting) | **Phase 5, not this phase** | `identity.py` guard (Phase 2 chokepoint) | Out of scope; Phase 3 stays inert. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `hashlib` | CPython 3.13.7 local / pyRevit CPython 3.12 build / IronPython 3.4 (IPY342) | SHA-256 for secret digests and file hashes | Already used in-repo (`scripts/build_contrib_kit.py:17,64`); available on both runtimes. IPY342 availability is `[ASSUMED]` until the D-04 live gate runs. |
| Python stdlib `json`, `os`, `errno` | both runtimes | Manifest I/O, file reading, ENOENT discrimination | Same dependency set as `textutils.py`. |
| Python stdlib `secrets`, `subprocess` | CPython only (build tools in `deploy/`, `scripts/`) | Secret generation (`token_urlsafe(32)`, D-07); `git ls-files` | `secrets` is banned only inside `revit_mcp/` (`scripts/conventions.py:32-35` `PY3_ONLY_MODULES` contains `"secrets"`); `deploy/` and `scripts/` are not dialect-checked. |
| `git` | 2.56.0.windows.2 locally; build server already uses `git -C "%REPO%"` (`build-payload.cmd:66,78`) | `git ls-files -z` tracked-file source | Structural exclusion of caches/untracked files (PITFALLS.md Pitfall 3). |
| pytest | >=8 (dev group, `pyproject.toml`); 9.1.1 observed in `.pyc` names | Unit suite | Existing; `testpaths = ["tests/unit"]`. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | >=0.28.1 (existing) | Not changed; the envelope builder only reshapes the dict `bridge._send` already JSON-encodes | Test via `httpx.MockTransport` only if a send-level test is wanted; not required in Phase 3 because live send is disabled. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hash-then-XOR (`D-04`) | `hmac.compare_digest` | CPython has it; IronPython 3.4 availability unverified (STACK.md: `hmac.rst` omits it). One shared implementation was locked; do not branch per runtime. |
| Hash-then-XOR | `CryptographicOperations.FixedTimeEquals` | Not on .NET Framework 4.8 (Revit 2024); takes `ReadOnlySpan<byte>`. Rejected (Conflict C3). |
| `git ls-files` | `os.walk` over DEST | Walk picks up `__pycache__`, `.pyc`, editor files, a dev `_bridge_secret`; locked out by D-11 and SC5. |

**Installation:** none. No package is installed by this phase.

**Version verification:** no external package recommended, so no `npm view`/`pip index` applies. Tool versions probed this session: `uv 0.11.1`, `Python 3.13.7` (via `uv run python`), `git 2.56.0.windows.2`.

## Package Legitimacy Audit

No external packages are installed by this phase (standard library only: `hashlib`, `json`, `os`, `errno`, `secrets`, `subprocess`). The `gsd_run query package-legitimacy check` seam was therefore not run; there is nothing to check.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
BUILD TIME (build server, CPython from pyRevit; Phase 3 delivers this)
                                   MCP_SECRET_FILE (outside ext\ and payload\)
                                          |  secret_tool.py ensure  (create once, token_urlsafe(32))
                       +------------------+------------------+
                       v                                     v
  build-payload.cmd                                publish-extension.cmd
   copy bridge.py, tools\, ...                      copy extension.json, startup.py
   stage  app\_bridge_secret  <---- byte-equal ---> robocopy revit_mcp (/XF _bridge_secret _manifest.json)
   gate.py: pair check (if MCP_SECRET_FILE set)     stage  revit_mcp\_bridge_secret
   robocopy /MIR -> payload\                        make_manifest.py: git ls-files -z -> hash DEST copies
                                                       -> DEST\_manifest.json  (fails on untracked .py in DEST)
                                                    robocopy install scripts

RUN TIME (inert in Phase 3; unit-proven only)
 CPython MCP server                                   Revit extension (IronPython 3, in Revit)
 bridge.py                                            revit_mcp/trust.py  (pure)
   load_secret()  -> app\_bridge_secret                 split_envelope(raw) --parse_request_data--> (envelope, payload)
   with_envelope(data, secret)                          check_secret(provided, expected) -> ok|missing|mismatch|server_not_configured
   [NOT called by _send in Phase 3]                     auth_failure(reason) -> (body, 401)
                                                        evaluate_integrity(manifest, observed) -> verified_match|verified_mismatch|unverifiable
 text/plain POST  ------------------------------->      integrity_failure(files) -> (body, 423)
 {"_mcp":{"secret":...}, "document":..., ...}           classify_listeners(endpoints, port) -> loopback_only|exposed|unknown
                                                      revit_mcp/integrity.py (read-only I/O)
                                                        read_manifest / observe_tree / check_integrity(root)
                                                      NOT wired: startup.py and every route are unchanged (Phase 5)
```

### Recommended Project Structure
```
revit_mcp/
├── trust.py            # NEW pure helper, no pyRevit import, no routes, IronPython 3.4 dialect
├── integrity.py        # NEW read-only file reader/composer, helper (no registrar)
deploy/
├── make_manifest.py    # NEW build tool (CPython): git ls-files -z -> _manifest.json
├── secret_tool.py      # NEW build tool (CPython): ensure / stage / verify the secret pair
├── config.cmd          # EDIT: MCP_SECRET_FILE default
├── build-payload.cmd   # EDIT: stage app\_bridge_secret; pair check
├── publish-extension.cmd  # EDIT: /XF exclusions, stage secret, call make_manifest.py after the revit_mcp robocopy
└── gate.py             # EDIT: optional pair check when MCP_SECRET_FILE is defined and the file exists
scripts/
└── dev_secret.py       # NEW: create revit_mcp/_bridge_secret once on a dev machine, never overwrite, never print the value
bridge.py               # EDIT (additive only): load_secret(), with_envelope(); NOT called from _send
tests/unit/             # NEW test files (see Validation Architecture)
.gitignore              # EDIT (append only): _bridge_secret, _manifest.json
CLAUDE.md               # EDIT: shared pure helpers are textutils.py and trust.py (D-17)
```

### Pattern 1: One pure module, simulated hostile runtime
**What:** `trust.py` reuses the runtime aliases from `textutils.py` (`from .textutils import _TEXT_TYPE, _BYTES_TYPE, parse_request_data`) instead of adding a third alias block, and avoids any 3.5+ syntax.
**When to use:** every function in `trust.py`/`integrity.py`.
**Example:**
```python
# Source: revit_mcp/textutils.py:32-37 and 231-261 (read this session); design is this research's recommendation
if bytes is str:  # IronPython 2.7 / Python 2
    _TEXT_TYPE = unicode  # noqa: F821 - defined only on Python 2
    _BYTES_TYPE = str
else:  # IronPython 3 / CPython 3
    _TEXT_TYPE = str
    _BYTES_TYPE = bytes
```
Quoted signature to reuse: `def parse_request_data(data):` ("Return a route request body as Python data, in either engine"; accepts bytes, str, dict; "Anything else -- None above all ... is returned untouched").

### Pattern 2: Hash-then-XOR compare with no early exit (D-04/D-05)
**What:** both inputs to UTF-8 bytes, SHA-256, `bytearray(digest)` (yields ints on 2.7 and 3.x; iterating a Py2 `str` digest would yield 1-char strings), XOR-accumulate over all 32 bytes, `except Exception` returns without text.
**Example:**
```python
# Source: this research; satisfies D-04/D-05 and the 3.4 language level
def _digest(value):
    """SHA-256 of text/bytes as a bytearray, or None for any other type."""
    if isinstance(value, _TEXT_TYPE):
        value = value.encode("utf-8")
    elif not isinstance(value, _BYTES_TYPE):
        return None
    return bytearray(hashlib.sha256(value).digest())


def _same_digest(left, right):
    """True when equal. Visits every position; no return/break inside the loop."""
    acc = len(left) ^ len(right)
    for a, b in zip(left, right):
        acc |= a ^ b
    return acc == 0


def secret_matches(provided, expected):
    try:
        left = _digest(provided)      # digests only; the secret itself is never a local here
        right = _digest(expected)
        if left is None or right is None:
            return False
        return _same_digest(left, right)
    except Exception:
        return False                  # D-05: no message, no values, no logging


def check_secret(provided, expected):
    """ok | missing | mismatch | server_not_configured (D-05). Server config wins over client state."""
    if _blank(expected):
        return "server_not_configured"
    if _blank(provided):
        return "missing"
    return "ok" if secret_matches(provided, expected) else "mismatch"
```
(`_blank(v)`: `v is None` or empty text/bytes. A non-text, non-None `provided` such as an int or dict is `mismatch`, never an exception.)

### Pattern 3: Envelope split that never raises and never echoes
**What:** `split_envelope(raw) -> (envelope, payload)`; unparseable body returns `({}, None)` so the handler's own parse reports its own error (mirrors `request_document_selector`, `identity.py:616-637`: "Never raises ... the handler's own parse then reports its own error exactly as before"). Build the cleaned payload with `dict((k, v) for k, v in data.items() if k != ENVELOPE_KEY)` — **not** `{**data}` (3.5+; `ast.parse(..., feature_version=(3, 4))` does not flag it, verified this session). A non-dict `_mcp` value yields envelope `{}`. Return the **whole** envelope dict (not just the secret) so Phase 6 `call_id` and Phase 7 approval tokens can ride the same key without a schema change.

### Pattern 4: Three-state integrity with an injected observation
**What:** `evaluate_integrity(manifest, observed)` is a pure function over two plain dicts; the reader builds `observed`.
```python
# Contract proposed by this research (names are Claude's-discretion per CONTEXT)
# manifest: {"schema": 1, "generated_at": str, "commit": str, "files": {"startup.py": "<sha256>", ...}}
# observed: {"hashes": {relpath: sha256}, "present_py": [relpaths of *.py found in scope], "unreadable": [relpaths]}
# result:   {"state": "verified_match" | "verified_mismatch" | "unverifiable",
#            "reason": None | "manifest_missing" | "manifest_unreadable" | "read_error",
#            "modified": [...], "missing": [...], "unexpected": [...]}   # sorted lists
```
Rules: manifest `None` -> `unverifiable/manifest_missing`; wrong shape, `schema != 1`, non-dict `files`, any key that is absolute or contains `..` -> `unverifiable/manifest_unreadable`; any `unreadable` entry -> `unverifiable/read_error` (never mismatch); otherwise `modified` = hash differs, `missing` = manifest path with no hash and not unreadable, `unexpected` = `*.py` present and not in manifest (any prefix, including `_foo.py`; `__init__.py` is tracked and in the manifest). Reader maps `errno.ENOENT` on a listed file to "absent" (-> `missing`), any other `IOError`/`OSError` to `unreadable`. Use `except (IOError, OSError) as exc` and compare `getattr(exc, "errno", None)` (valid on 2.7 and 3.4).

### Pattern 5: Manifest generation from tracked files, hashing the published copies
**What (`deploy/make_manifest.py`):** `git -C <repo> ls-files -z -- startup.py extension.json revit_mcp`, filter to `.py`/`.json`, hash `DEST\<path>` via the shared `hash_normalized`, write `DEST\_manifest.json` (`json.dump(..., sort_keys=True, indent=2)`, injected clock and commit for deterministic tests). Fail the build (non-zero exit, explicit message) when a tracked path is absent from DEST **or** DEST holds a `.py` under `revit_mcp/` that is not tracked: otherwise the extension would publish a file the manifest does not know and Phase 5 would block every mutation fleet-wide as `unexpected`. Refuse `--dest` equal to `--repo` (INTG-08: never write a manifest into the dev working tree). `sys.path.insert(0, repo)` explicitly before `from revit_mcp.integrity import hash_normalized`: pyRevit's embeddable CPython ignores `PYTHONPATH` (`deploy/server.py` header comment).

### Anti-Patterns to Avoid
- **`from utils import ...` / flat sibling imports in `trust.py`/`integrity.py`:** `scripts/conventions.py:42` `LOCAL_MODULES = {"utils", "textutils", "registry", "revit_mcp"}`; use `from .textutils import ...`.
- **`{**a}`, `[*a]`, `bytes.hex()`, `os.scandir`, `subprocess.run`, f-strings, `typing`, `pathlib`, `secrets` in `revit_mcp/`:** IronPython 3.4 language/stdlib level; the repo dialect check catches only f-strings, `async def`, banned imports and flat imports, so add a trust-specific guard (Validation).
- **Importing `trust` from another `revit_mcp/` domain in this phase:** `tests/unit/test_registration.py:256` `helpers = {"utils", "textutils", "registry", "identity"}` would then flag `trust -> ...` unless `trust`/`integrity` are added (do add them now).
- **Merging a client-supplied `_mcp` into the envelope:** `with_envelope` must refuse a `data` dict that already has `_mcp` (a model-controlled key must never pre-seed the envelope).
- **Reading the secret from `data.get("secret")` directly:** go through `split_envelope`; PITFALLS Pitfall 10.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request body parsing | A second JSON/bytes parser for the envelope | `parse_request_data()` (`revit_mcp/textutils.py:231`) | Proven on both runtimes; `scripts/conventions.py check_request_parsing` rejects `json.loads(request.data)`. |
| Secret generation | Custom random token code | `secrets.token_urlsafe(32)` in `deploy/secret_tool.py` (CPython) | CSPRNG, stdlib. |
| Tracked-file enumeration | `os.walk` + exclude patterns | `git ls-files -z` | Pattern lists rot (Pitfall 3); `-z` avoids `core.quotepath` mangling of non-ASCII names. |
| Hash function / line-ending policy | Two separate hash implementations (generator vs runtime) | One `hash_normalized` in `revit_mcp/integrity.py`, imported by `make_manifest.py` | A mismatch between generator and verifier is a fleet-wide false positive. |
| Constant-time compare | `==`, `.Equals`, a per-runtime branch, or a timing benchmark | D-04 hash-then-XOR, structural tests | `==` short-circuits; `FixedTimeEquals` unavailable on net48; wall-clock timing tests are flaky. |
| Status distinct from rollback | New implicit error signal in `format_response` | A distinct HTTP status (401/423) that arrives as `Error: <code> - ...` | `tools/utils.py:150-156` (`_project_response` docstring) "Do not add new implicit error signals here." |
| Atomic secret creation | Check-then-write | `os.open(O_CREAT|O_EXCL)` | Two build scripts may run back to back; never overwrite an existing secret. |

**Key insight:** every trust failure mode in this phase was already paid for once in this repo (the `unicode` alias collapse, the `rolled_back` false success, the `application/json` parse). The cheap defence is to reuse the proven seams (`parse_request_data`, `Error: <code> - <body>` passthrough, tracked-file lists) and to test under simulated hostile conditions rather than invent new mechanisms.

## Common Pitfalls

### Pitfall 1: A developer's secret gets published to the fleet
**What goes wrong:** D-09 puts `revit_mcp/_bridge_secret` in the working tree. `publish-extension.cmd:63-64` runs `robocopy "%REPO%\revit_mcp" "%DEST%\revit_mcp" /E /XJ /XD __pycache__ /XF *.pyc` — robocopy ignores `.gitignore`, so a publish run from a dev machine copies the dev secret (and any dev `_manifest.json`) into `ext\`.
**How to avoid:** add `_bridge_secret _manifest.json` to `/XF`, **and** stage the real secret after the robocopy (overwrite) so order cannot matter; unit-test the command text (the `/XF` list and the order of lines).
**Warning signs:** `dir /b "%DEST%\revit_mcp"` shows `_bridge_secret` before the stage step; two different secrets between share and `MCP_SECRET_FILE`.

### Pitfall 2: The payload cannot import `revit_mcp`
**What goes wrong:** `build-payload.cmd:109-118` copies `main.py`, `bridge.py`, `server.py`, `gate.py`, `warm.py`, `tools\`, `tests\` only. A `from revit_mcp.trust import ...` in `bridge.py` passes every unit test and dies on a workstation with `ModuleNotFoundError`. Also `tests/unit/test_payload_ships_root_modules.py` only checks the root modules `main.py` imports **directly** (`_root_modules_main_imports`), so a new root module imported by `bridge.py` would not be caught.
**How to avoid:** put `load_secret()`/`with_envelope()` in `bridge.py`; duplicate the small loader and pin parity with a test. If a new root module is ever preferred, add its `copy /y` line **and** extend that test to transitive imports.

### Pitfall 3: Mixed line endings and `core.autocrlf`
**What goes wrong:** `git ls-files --eol` shows `deploy/publish-extension.cmd` and `revit_mcp/textutils.py` as `i/lf w/crlf` while `deploy/config.cmd`, `deploy/build-payload.cmd` are `w/lf`; `core.autocrlf` is `true`. Un-normalized hashes differ between machines; `startup.py:57` itself does `.replace("\r\n", "\n")`.
**How to avoid:** hash `data.replace(b"\r\n", b"\n")` in the single shared function; hash raw bytes otherwise (do not strip a BOM: a BOM change is a change). Test table: LF, CRLF, mixed, BOM, empty file.

### Pitfall 4: A secret file written with a BOM, UTF-16 or a trailing newline
**What goes wrong:** PowerShell 5 `>`/`Set-Content` writes UTF-16 or BOM; `cmd echo` appends CRLF. Byte-equality or compare then fails mysteriously ("sometimes mismatch").
**How to avoid:** `load_secret` reads bytes, decodes `utf-8-sig`, strips ASCII whitespace; rejects empty (and recommend a minimum length, for example 16) as `None`; `secret_tool.py` writes ASCII without newline; the byte-equal verify compares the stripped bytes **and** fails on a BOM/UTF-16 artifact. Never create the secret with shell redirection (CLAUDE.md global policy forbids `Set-Content`/here-strings for edits as well).

### Pitfall 5: `unexpected` makes legitimate publishes fatal
**What goes wrong:** D-12 treats any `.py` not in the manifest as a mismatch. An untracked-but-copied file (new domain not yet committed) makes Phase 5 block all mutations on every station.
**How to avoid:** the build-time guard in Pattern 5 (fail the publish, loudly, on untracked `.py` in DEST); runtime reader flags only `.py` (editor artifacts such as `foo.py~`, `.swp`, `.orig`, `.bak` are ignored), skips `__pycache__`.

### Pitfall 6: Dev layout mismatch between halves
**What goes wrong:** `bridge.py` searches beside itself, then `revit_mcp/_bridge_secret` (D-09). A developer running the **installed** payload (has `app\_bridge_secret` from the share) against the **junction** extension (dev secret) gets 401 `mismatch` once Phase 5 lands.
**How to avoid:** document in `deploy/README.md`/CLAUDE.md: on a dev machine run `uv run main.py` from the repo; `scripts/dev_secret.py` creates the one file and never overwrites it.

### Pitfall 7: The `rolled_back`-style pair does not transfer 1:1
**What goes wrong:** copying the `rolled_back` alarm test verbatim would assert the wrong thing: the existing alarm (`tests/unit/test_format_response.py` ~170-190) relies on a dict with **no** `error` key; `auth_failure()`'s dict has one (Conflict C4).
**How to avoid:** three assertions: (1) `format_response('Error: 401 - {"error": ..., "auth": "mismatch"}')` is returned verbatim (string passthrough); (2) `format_response(auth_body)` as a dict **does** render as an error (`"ERROR DETAILS" in out`); (3) alarm: `format_response({"auth": "mismatch"})` is **not** an error, documenting why the 401 code (not the `auth` key) carries the signal. Also keep the rendered text free of the secret (SEC-06) and check 401 differs from 409 and 503 and from Phase 2's refusals (400/404/412/422) and 423.

### Pitfall 8: A CPython-green suite that is red on IronPython
**What goes wrong:** the `unicode` alias incident (CLAUDE.md "Known sharp edges") — pyRevit defines `unicode` as an alias of `str` in its IronPython 3 engine, so a NameError probe reports Python 2. CPython tests stayed green.
**How to avoid:** a test that injects `builtins.unicode = str` (and removes it afterwards), reloads `revit_mcp.trust`/`integrity`, and re-runs the behaviour table; a second pass with a fake `hashlib.sha256` returning `str`-like digests proves `bytearray(...)` normalization; an AST guard for 3.5+ syntax in the two new modules.

### Pitfall 9: `/status/` cost
**What goes wrong:** hashing ~30 files over a UNC share on every `/status/` call (called often) is slow and creates a new hang source (PITFALLS Pitfall 9).
**How to avoid (Phase 5 note, but shapes the Phase 3 API):** `check_integrity(root)` stays a pure-ish function the caller can run once at load and cache; do not bake caching into Phase 3.

### Pitfall 10: Editing files the user has uncommitted changes in
**What goes wrong:** `git status` at session start shows uncommitted user work in `.gitignore` (the GSD block is commented out), `startup.py`, `deploy/publish-extension.cmd`, `deploy/install.cmd`, `deploy/*.md`, `scripts/*.py`. A whole-file rewrite or a commit without a pathspec drags unrelated changes in or reverts them.
**How to avoid:** append-only edits to `.gitignore`; targeted `Edit`s in `publish-extension.cmd` (its working copy is `w/crlf`: preserve CRLF); commit by pathspec (project memory: "pathspec commits on dirty tree"). Do not edit `startup.py` at all in this phase.

## Code Examples

### Client half in `bridge.py` (additive, not wired)
```python
# Source: design for D-08/D-10; bridge._send currently sends json.dumps(data) as text/plain
# (bridge.py:850-855):
#     response = await client.post(
#         endpoint,
#         content=json.dumps(data).encode("utf-8"),
#         headers={"Content-Type": "text/plain; charset=utf-8"},
ENVELOPE_KEY = "_mcp"
SECRET_FILE_NAME = "_bridge_secret"


def load_secret(search_dirs=None):
    """Secret text from the first existing _bridge_secret, or None. Never logs, never raises."""
    ...  # read bytes, utf-8-sig, strip; empty/unreadable -> None; order: beside bridge.py, then revit_mcp/


def with_envelope(data, secret):
    """A copy of data carrying {"_mcp": {"secret": secret}}; data unchanged when secret is None.

    Refuses (ValueError with a fixed message that never includes the body) when data already
    has "_mcp": a model-supplied key must not pre-seed the envelope. Does not mutate data.
    """
    ...
```
Do not call it from `_send` in this phase (D-10: sending is enabled only in Phase 5). A test asserts `_send` still posts exactly `json.dumps(data)` for a representative payload, so the inert guarantee is checked.

### Live gate snippet for D-04 (human checkpoint, `/execute_code/`)
The plan must include a `checkpoint:human-verify` task; the researcher did not run live Revit. Prerequisites from project memory: Revit open with a document, pyRevit Routes enabled, exactly one listener on 48884 (`Get-NetTCPConnection -LocalPort 48884 -State Listen`), user authorizes the call (it goes through the trusted `execute_revit_code` exception, D-15). The snippet touches no document, uses single-argument prints (the route's injected `print` is a one-argument lambda) and no f-strings:
```python
import sys
import hashlib
print("py={}".format(sys.version.split()[0]))
d = hashlib.sha256(u"тест".encode("utf-8")).digest()
print("digest_type={} len={} first4={}".format(type(d).__name__, len(d), list(bytearray(d))[:4]))
print("abc_ok={}".format(hashlib.sha256(b"abc").hexdigest() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))
try:
    import hmac
    print("hmac_compare_digest={}".format(hasattr(hmac, "compare_digest")))
except Exception as exc:
    print("hmac_import_failed={}".format(type(exc).__name__))
try:
    import System
    print("clr_version={}".format(System.Environment.Version))
    print("FixedTimeEquals_type_present={}".format(
        System.Type.GetType("System.Security.Cryptography.CryptographicOperations") is not None))
except Exception as exc:
    print("clr_probe_failed={}".format(type(exc).__name__))
```
**Expected (pass criteria):** `abc_ok=True`; `digest_type=bytes len=32 first4=[227, 79, 109, 236]` (same four bytes as the CPython 3.13 run this session); `hmac_compare_digest` and the `System` lines are informational (record them; on Revit 2024 expect `FixedTimeEquals_type_present=False`, which closes SC2's CLR question empirically). If `abc_ok` is not `True` or `hashlib` import fails, D-04 must be reopened (fallback: a pure-Python SHA-256 is **not** acceptable; switch to `System.Security.Cryptography.SHA256` through `clr` and re-plan). Per the 2026-10-16 note, evidence from earlier phases states the installed live attachment was historically `IPY2712PR` and production IPY342 was not itself established (02-20-SUMMARY), so the checkpoint must record `py=` to confirm the engine; `bytearray(digest)` is chosen so the same code is correct on 2.7 and 3.x. No Revit restart is needed (no `revit_mcp/` file changes in this phase).

### Build-order assertion (unit test over the `.cmd` text)
```python
# Source: pattern of tests/unit/test_payload_ships_root_modules.py (regex over build-payload.cmd)
# publish-extension.cmd must, in this line order:
#   robocopy "%REPO%\revit_mcp" ... /XF *.pyc _bridge_secret _manifest.json
#   < secret staged into %DEST%\revit_mcp\_bridge_secret
#   < make_manifest.py call
#   < robocopy "%~dp0." "%MCP_SHARE_ROOT%\install" ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| STACK.md: `FixedTimeEquals` on every runtime; `hmac.compare_digest` on CPython and `FixedTimeEquals` on IronPython (two code paths) | One shared pure hash-then-XOR (D-04) | This discussion (2026-09-23), confirmed by docs this session | One function, testable under CPython, no CLR dependency |
| Header-based secret (research ARCHITECTURE.md Q1) | Body envelope `_mcp` via `parse_request_data` | STATE.md decision | Avoids an unverified pyRevit header path |
| Extension package imported as `revit_mcp` | Loaded under owned alias `genpro_revit_mcp` (`startup.py`, uncommitted working-tree change, base URL `/genpro_revit_mcp`) | Phase 2 era; present in working tree | Relative imports inside the package are mandatory; `trust.py` must never use `revit_mcp.` absolute paths in production code (the unit suite imports it as `revit_mcp.trust`, which works because `revit_mcp/__init__.py` imports only `logging`) |
| Roadmap "startup.py chokepoint" | Explicit per-handler guard (Phase 2 G1) | Phase 2 | Conflict C2 |

**Deprecated/outdated:** `.planning/research/STACK.md` lines 105-135 (the `CryptographicOperations` claim); 03-CONTEXT.md phase numbering.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `hashlib.sha256(...).digest()` works in pyRevit's IPY342 Routes engine and `bytearray(digest)` yields ints | Standard Stack, Live gate | D-04 falls apart; mitigated by the mandatory human live gate |
| A2 | IronPython 3 does not write `__pycache__`/`.pyc` into the UNC extension directory | Pitfall 5, Pattern 4 | Reader already ignores non-`.py` and `__pycache__`; low risk |
| A3 | pyRevit's `server.server_address[0]` reflects the bind host (an alternative `classify_listeners` input source for Phase 5) | Pattern, Open Questions | Only affects Phase 5 wiring; `GetActiveTcpListeners()` remains the locked source (D-16) |
| A4 | The shared secret on a department-readable share is acceptable under the stated threat model | Conflicts C5 | If the share is broader than the fleet, the "network barrier" is weaker than documented; needs the user's confirmation |
| A5 | A minimum secret length (suggested 16) is acceptable to reject trivially short manual secrets | Pitfall 4 | Rejecting a deliberately short dev secret; Claude's discretion, trivially reversible |
| A6 | `git` is available on whichever machine runs `publish-extension.cmd` and the working copy there is a git checkout (build-payload tolerates a missing `git` for the version stamp, `build-payload.cmd:66-67`) | Pattern 5 | Manifest step must fail loudly rather than skip; if the publisher has no checkout, INTG-01 cannot be met |
| A7 | Running `publish-extension.cmd` against a scratch `MCP_SHARE_ROOT` (config.cmd allows environment overrides) is safe for an optional Windows-only smoke test | Validation | Only a test-design choice; run against `%TEMP%` only |

## Open Questions

1. **Default location of `MCP_SECRET_FILE` (Claude's-discretion value, but it has a security flavour).**
   - What we know: D-07 wants it outside `ext\` and `payload\`; `config.cmd` defaults `MCP_SHARE_ROOT` to `\\srv-dfs\BIM\06_RevitMCP`; both scripts are documented as "RUN ON THE BUILD SERVER".
   - What's unclear: whether the build operator share is more restricted than the fleet-readable share.
   - Recommendation: default to a sibling folder under the share that is not mirrored (for example `%MCP_SHARE_ROOT%\_build\bridge_secret`) with an environment override, and document in `deploy/SETUP-RUNBOOK.md` that the file is readable by whoever can read it, and that anyone who can read `ext\` or the installed payload holds the secret anyway (C5). Ask the user at plan review if a build-server-local path is preferred.

2. **Phase 5 mechanism for D-02 ("handler receives a cleaned payload") given C2.**
   - What we know: handlers re-parse `request.data` themselves; startup wrapper is test-forbidden.
   - What's unclear: whether the guard may rewrite `request.data` on pyRevit's `Request` object.
   - Recommendation: not a Phase 3 task; record in the Phase 5 discuss agenda. Phase 3 keeps `split_envelope` per D-02.

3. **Should the IronPython dialect guard be generalised in `scripts/conventions.py`?**
   - What we know: it misses `{**a}`, `[*a]`, `bytes.hex()`. `scripts/conventions.py` is copied into `contrib-kit/` by `scripts/build_contrib_kit.py` ("Rebuild whenever scripts/conventions.py changes").
   - Recommendation: do **not** touch `conventions.py` in Phase 3 (kit drift); add a trust-specific AST test instead. D-17's "conventions must accept the new files" is already true: `test_conventions.py` enumerates `revit_mcp/*.py` automatically (`REVIT_MCP_FILES`, line 53), and a pure helper with no registrar passes `check_route_registrar`.

4. **Edge: should `unexpected` cover `*.py` in subdirectories of `revit_mcp/`?** Currently none exist (`git ls-files revit_mcp` is flat). Recommendation: top-level listing only plus manifest-listed paths (matches `startup._domain_modules`, which lists only the package directory).

5. **Does Phase 3 need a Phase 7-aware envelope?** 07-CONTEXT.md (staged) says secret/approval must not be model-visible arguments and reuses "Phase 3/5 trust boundary". Recommendation: nothing to change; return the full envelope dict from `split_envelope` and reject client-supplied `_mcp` in `with_envelope`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python via `uv run` | All unit tests, build tools | yes | 3.13.7 (uv 0.11.1; `.python-version` = 3.13) | — |
| pytest | Validation | yes | via dev group; baseline 4054 passed, 3 skipped, 22 s | — |
| git | `make_manifest.py` tests (tmp repo), `git ls-files` | yes | 2.56.0.windows.2 | Tests `skipif(shutil.which("git") is None)`; production step must fail, not skip |
| Windows `cmd`/`robocopy` | optional publish smoke test | yes (win32, Git Bash + PowerShell) | — | Skip off-Windows |
| pyRevit CPython engine on a build server | real `build-payload.cmd`/`publish-extension.cmd` | not probed (build-server only, not needed for unit work) | — | `MCP_PYEXE` override documented in `config.cmd:33-37` |
| Live Revit + pyRevit Routes (IPY342) | D-04 live gate only | not probed by research (human gate) | — | Plan includes a `checkpoint:human-verify` |

**Missing dependencies with no fallback:** none for unit work.
**Missing dependencies with fallback:** build-server interpreter (probe is a deployment concern, not a Phase 3 planning blocker).

## Validation Architecture

> `.planning/config.json` contains only `workflow._auto_chain_active` and `workflow.use_worktrees`; `nyquist_validation` is absent, so it is enabled. `security_enforcement` absent, so the Security Domain is included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8 (dev group; 9.1.1 observed), Python 3.13.7 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options] testpaths = ["tests/unit"]`; shared setup `tests/unit/conftest.py` (autouse fixture that blocks any real Revit via `bridge.py`) |
| Quick run command | `uv run pytest tests/unit/test_trust_secret.py tests/unit/test_trust_envelope.py tests/unit/test_trust_integrity.py tests/unit/test_trust_listeners.py tests/unit/test_integrity_reader.py tests/unit/test_make_manifest.py tests/unit/test_secret_pipeline.py tests/unit/test_bridge_secret_client.py tests/unit/test_trust_dialect.py -q` |
| Full suite command | `uv run pytest tests/unit -q` (baseline 4054 passed, 3 skipped, ~22 s) |

### Phase Requirements -> Test Map
| Req ID / SC | Behavior | Test Type | Automated Command | File Exists? |
|-------------|----------|-----------|-------------------|-------------|
| SC1, SEC-01, SEC-02 | `check_secret` returns ok/missing/mismatch/server_not_configured; wrong, missing, correct, bytes-vs-str equivalence (`b"x"` == `"x"`), non-text input -> mismatch; secret read from `text/plain` body bytes/str/dict via `split_envelope` | unit | `uv run pytest tests/unit/test_trust_envelope.py tests/unit/test_trust_secret.py -q` | Wave 0 |
| SC1 (IronPython-targeted) | Same table with injected `builtins.unicode = str`, reloaded module; fake `hashlib` returning Py2-style digest; `_TEXT_TYPE`/`_BYTES_TYPE` reuse | unit | `uv run pytest tests/unit/test_trust_dialect.py -q` | Wave 0 |
| SC2, SEC-04 | No early exit: counting-sequence test (mismatch at index 0 vs 31 visits the same count) plus AST test (no `return`/`break` in `_same_digest` loop, no `==`/`compare_digest`/`FixedTimeEquals` between secret-derived values); docstring contains the documented fallback reason | unit | `uv run pytest tests/unit/test_trust_secret.py -k constant -q` | Wave 0 |
| SC2 (live) | `hashlib.sha256` under IPY342, plus informational CLR probe | **manual-only** human gate via `/execute_code/` | snippet in "Code Examples" | n/a |
| SC3, SEC-03 | `auth_failure(reason)` returns `(body, 401)`; 401 not in {200, 409, 412, 422, 423, 503}; `Error: 401 - ...` verbatim through `format_response`; the three-assertion pair of Pitfall 7 | unit | `uv run pytest tests/unit/test_format_response.py -k "401 or auth" -q` | extend existing file |
| SC4, SEC-06 | Monkeypatch `hashlib.sha256` to raise an exception whose message contains the secret: result is `mismatch`, `caplog` (DEBUG) has no records, `repr`/`str` of the result and of `auth_failure()` body never contain the secret; `with_envelope` error text never contains the body; AST: no `logging`/`print`/`traceback` use in `trust.py` | unit | `uv run pytest tests/unit/test_trust_secret.py tests/unit/test_bridge_secret_client.py -k "leak or secret_never" -q` | Wave 0 |
| SEC-05 | The gate is method-scoped: a pure `gate_applies(method)` (POST only) or an inventory-style assertion that no GET route is referenced by the helper; `/status/` is a GET | unit | `uv run pytest tests/unit/test_trust_secret.py -k method -q` | Wave 0 |
| SEC-07 | `classify_listeners`: 127.0.0.1 only, `::1` only, `0.0.0.0`, `::`, LAN IP, mixed loopback + wildcard, IPv4-mapped loopback, scope ids, other ports ignored, empty/None/garbage -> unknown | unit | `uv run pytest tests/unit/test_trust_listeners.py -q` | Wave 0 |
| SEC-08, SC7 | `secret_tool`: create-once (`O_EXCL`), never overwrite, stage into both artifact paths, byte-equal verify, rejects BOM/UTF-16/empty; `.cmd` text order (robocopy `/XF` list, secret stage, `make_manifest.py` call, installer robocopy); `config.cmd` defines `MCP_SECRET_FILE`; `build-payload.cmd` stages `app\_bridge_secret` before the final `/MIR` publish; `.gitignore` lists both names | unit | `uv run pytest tests/unit/test_secret_pipeline.py -q` | Wave 0 |
| INTG-01, SC5 | `build_manifest` list equals `git ls-files` set from a tmp git repo; `os.walk`/`glob`/`scandir` monkeypatched to raise; untracked `.py` and `__pycache__/x.pyc` in DEST never become entries; untracked `.py` in DEST raises (build fails); tracked file missing in DEST raises; `--dest` equal to repo refused; deterministic JSON with injected clock/commit; non-ASCII filename survives `-z` | unit | `uv run pytest tests/unit/test_make_manifest.py -q` | Wave 0 |
| INTG-02, INTG-05, INTG-06 | `evaluate_integrity` table: match; modified; missing; unexpected `.py`; CRLF vs LF equal; BOM change is a change; `__pycache__`, `.pyc`, `foo.py~`, `.swp` ignored; sorted deterministic lists | unit | `uv run pytest tests/unit/test_trust_integrity.py -q` | Wave 0 |
| INTG-07, SC6 | Three-state: `manifest_missing`, `manifest_unreadable` (bad JSON, wrong schema, traversal key), `read_error` (non-ENOENT `OSError` such as `EACCES`/network error) never become mismatch; ENOENT on a listed file is `missing`; hypothesis-style loop over error kinds | unit | `uv run pytest tests/unit/test_trust_integrity.py tests/unit/test_integrity_reader.py -k "unverifiable or unreachable" -q` | Wave 0 |
| INTG-03, SC6 | Read-only: `open` write modes, `os.remove/rename/replace/mkdir/utime`, `shutil.*` monkeypatched to raise; tmp tree snapshot (names, bytes, mtimes) equal before/after for every input class; AST scan finds no write call in `revit_mcp/trust.py` and `revit_mcp/integrity.py` | unit | `uv run pytest tests/unit/test_integrity_reader.py -k "never_writes" -q` | Wave 0 |
| INTG-04 | `integrity_failure(files)` returns `(body, 423)` with `integrity` and sorted `files`; 423 distinct from 401/409/412/422/503 | unit | `uv run pytest tests/unit/test_trust_integrity.py -k 423 -q` | Wave 0 |
| INTG-08, SC8 | `check_integrity(REPO_ROOT)` on the real working tree returns `verified_match` or `unverifiable` (never `verified_mismatch`) and, with no `_manifest.json` in the repo, specifically `unverifiable/manifest_missing`; a tmp copy of the layout with a stale manifest is covered as a negative control | unit | `uv run pytest tests/unit/test_integrity_reader.py -k "dev_junction or real_repo" -q` | Wave 0 |
| SEC-02/SEC-08 client half, D-10 | `load_secret` search order, BOM/CRLF/whitespace/empty/unreadable; parity with the Revit-side loader on shared fixtures; `with_envelope` copies, never mutates, refuses a pre-existing `_mcp`; `_send` still posts exactly `json.dumps(data)` (inert guarantee) | unit | `uv run pytest tests/unit/test_bridge_secret_client.py -q` | Wave 0 |
| Registry/conventions regression | `trust`/`integrity` classified as helpers (no routes, no registrar, no domain imports); new files pass `test_conventions.py` parametrized checks automatically | unit | `uv run pytest tests/unit/test_registration.py tests/unit/test_conventions.py tests/unit/test_phase2_inventory.py -q` | existing (edit helper sets at `test_registration.py:238` and `:256`) |

### Sampling Rate
- **Per task commit:** the quick-run command above (all new test files; seconds).
- **Per wave merge:** `uv run pytest tests/unit -q` (about 22 s today; must stay at 0 failures, 3 skipped).
- **Phase gate:** full suite green, plus the recorded D-04 live checkpoint output, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/unit/test_trust_envelope.py`, `test_trust_secret.py`, `test_trust_integrity.py`, `test_trust_listeners.py` — SEC-01..07, INTG-02..07
- [ ] `tests/unit/test_integrity_reader.py` — INTG-03, INTG-07, INTG-08 (includes the real-repo check)
- [ ] `tests/unit/test_make_manifest.py` — INTG-01, SC5
- [ ] `tests/unit/test_secret_pipeline.py` — SEC-08, SC7 (cmd text order, `secret_tool`, `.gitignore`)
- [ ] `tests/unit/test_bridge_secret_client.py` — client half, inert guarantee
- [ ] `tests/unit/test_trust_dialect.py` — IronPython simulation plus 3.5+ syntax guard (`ast.parse(..., feature_version=(3, 4))` plus structural checks for dict/list unpacking, `.hex()`, `os.scandir`, `subprocess.run`)
- [ ] Extensions: `tests/unit/test_format_response.py` (401 pair), `tests/unit/test_registration.py` (helper sets)
- [ ] Framework install: none (already present)
- [ ] Optional Windows-only smoke test running `publish-extension.cmd` against a scratch `MCP_SHARE_ROOT` with `MCP_PYEXE=sys.executable`, `skipif(sys.platform != "win32")`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (shared secret) | Body-carried shared secret, hash-then-XOR compare, fail-closed `server_not_configured`; no per-station secret (Out of Scope) |
| V3 Session Management | no | Stateless per-request secret; no sessions |
| V4 Access Control | yes (method-scoped gate: POST only, reads and `/status/` open) | D-03/SEC-05; enforcement in Phase 5 |
| V5 Input Validation | yes | Envelope parsed only by `parse_request_data`; non-dict `_mcp`, non-text secret, traversal keys in manifest all handled without exceptions or echo |
| V6 Cryptography | yes | stdlib `hashlib.sha256`, `secrets.token_urlsafe(32)`; never a hand-rolled hash; the compare is a documented fixed-length XOR over digests |
| V7 Error Handling and Logging | yes | `trust.py` logs nothing; exceptions swallowed without values (SEC-06); fixed refusal texts |
| V10 Malicious Code / Integrity | yes | Hash manifest from tracked files; detect-only reader (no restore, Out of Scope) |
| V14 Configuration | yes | Secret file outside published trees, `.gitignore`d, `/XF`-excluded from robocopy, byte-equal pair check |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthenticated POST on a LAN-exposed Routes port | Spoofing / Tampering | Shared secret in the body (Phase 5 enforces); `classify_listeners` reports non-loopback bind (SEC-07) |
| Timing side-channel on secret compare | Information disclosure | Hash both sides to 32 bytes, XOR-accumulate with no early exit; structural tests |
| Secret leakage via exception text, traceback, log or `format_response` | Information disclosure | Narrow compare, swallow-without-text, no logging in trust code, fixed refusal strings, strip `_mcp` before handler where feasible (C2) |
| Model-supplied `_mcp` key pre-seeding the envelope | Tampering | `with_envelope` refuses a body that already has `_mcp` |
| Dev secret published to the share | Information disclosure | `/XF` exclusion, secret staged after the robocopy, pair verify |
| False tamper alarm blocking the fleet (hash instability) | Denial of service | Tracked-file manifest, CRLF normalization, three-state model, build-time guard against untracked `.py` in DEST |
| Manifest path traversal / hostile manifest keys | Tampering | Reject absolute and `..` keys as `manifest_unreadable` |
| Integrity check writing under a live Revit engine | Denial of service (crash) | Read-only by construction, proven by test (INTG-03) |

## Project Constraints (from CLAUDE.md)

- **Two-Runtime Rule:** `revit_mcp/` (incl. new `trust.py`, `integrity.py`) is IronPython 3.4 dialect: `"{}".format(x)`, no f-strings, no `async`, no `pathlib`, no `typing`, no `secrets`; CPython side (`bridge.py`, `deploy/`, `scripts/`, `tests/`) is free to use modern Python.
- Encoding cookie on line 1 of every module: `# -*- coding: utf-8 -*-` (checked by `test_encoding_cookie`).
- Route modules/helpers import siblings **relatively** (`from .textutils import ...`); never flat; keep one form.
- Never detect the runtime with `unicode`; use `if bytes is str:` (reuse `textutils` aliases).
- POST bodies are `text/plain` parsed via `parse_request_data()`; never `json.loads(request.data)` (rejected by `scripts/conventions.py` and `tests/unit`).
- Route handlers never raise; mutations in transactions with `suppress_warnings(t)` — not touched in Phase 3 (no route edits).
- `revit_mcp/` files cannot be imported under pyRevit-less CPython **unless** they import nothing from pyRevit — `trust.py`/`integrity.py` must keep that property (like `textutils.py`).
- Do not edit `startup.py` for this phase; do not add a handler wrapper (G1; `tests/unit/test_phase2_inventory.py:597`).
- Adding a tool/route needs a manifest entry; Phase 3 adds neither (tool_manifest.txt stays at its current content).
- `bridge.py` module docstring lines are pinned by `tests/unit/test_serialization_scope_docs.py`; add functions, do not reword the docstring. No `print()` in `bridge.py`/`main.py` (stdio protocol stream).
- Edits under `revit_mcp/` need a full Revit close/reopen before any live test; this phase only adds inert files, but a live check of new modules belongs to Phase 5.
- Run `uv run pytest tests/unit` before every commit; commit by pathspec on the dirty tree; end commits with the attribution line from the session reminder.
- User global policy: no worker with secrets; do not use `Set-Content`/here-string editing for scripts; GSD plan files written by workers need CRLF/LF checks.

## Sources

### Primary (HIGH confidence)
- Repo files opened this session: `03-CONTEXT.md`, `REQUIREMENTS.md`, `STATE.md`, `ROADMAP.md` (Phases 3-7), `CLAUDE.md`, `bridge.py` (1-160, 455-570, 780-1057), `revit_mcp/textutils.py`, `revit_mcp/identity.py` (525-675), `revit_mcp/status.py`, `revit_mcp/registry.py`, `startup.py`, `tools/utils.py` (`format_response`, `_project_response`), `tools/editing_tools.py` (56-71), `tests/unit/test_format_response.py`, `test_conventions.py`, `test_registration.py`, `test_phase2_inventory.py` (595-650), `test_payload_ships_root_modules.py`, `conftest.py`, `scripts/conventions.py`, `scripts/build_contrib_kit.py`, `deploy/config.cmd`, `build-payload.cmd`, `publish-extension.cmd`, `gate.py`, `server.py`, `find-python.cmd`, `.gitignore`, `.planning/research/STACK.md`, `PITFALLS.md` (Pitfalls 3, 4, 9, 10), `ARCHITECTURE.md` (grep), Phase 7 `07-CONTEXT.md`/`07-RESEARCH-NOTES.md` (grep).
- Local probes this session: `uv run pytest tests/unit` -> 4054 passed, 3 skipped (22 s); `git ls-files --eol`; `uv run python` SHA-256 snippet; `ast.parse(feature_version=(3, 4))` behaviour table.
- [CITED: learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.cryptographicoperations.fixedtimeequals] — applies to .NET Core 2.1+, .NET Standard 2.1, .NET 5+ only; `ReadOnlySpan<byte>` parameters.

### Secondary (MEDIUM confidence)
- [CITED: forums.autodesk.com Revit API forum "NET 8 migration"; blog.autodesk.io "Revit 2025 .NET 8 migration"] — Revit 2024 and earlier on .NET Framework 4.8, Revit 2025+ on .NET 8 (web search summary; a McNeel forum claim about .NET 10 in Sept 2026 updates is unverified and irrelevant to the decision).

### Tertiary (LOW confidence)
- IronPython 3.4 `hashlib`/`bytearray` behaviour and the `server_address[0]` bind-host reading are training-knowledge only (`[ASSUMED]`, A1/A3) pending the live gate.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — standard library only; versions probed locally.
- Architecture: HIGH for repo seams and conflicts (all read this session); MEDIUM for Phase 5 wiring shape (deferred).
- Pitfalls: HIGH — each is tied to a file/line read this session or a prior in-repo incident.
- IronPython runtime behaviour: MEDIUM — one live gate (D-04) outstanding.

**Research date:** 2026-10-23
**Valid until:** 2026-11-22 for repo facts (the working tree has uncommitted changes in `startup.py`, `.gitignore` and `deploy/`; re-check those files before executing), 30 days for the Microsoft/Autodesk citations.
