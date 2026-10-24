# Phase 7 — Session Research Inputs

**Status:** передача результатов текущего исследования в будущую фазу, не завершённый GSD research и не verification report.
**Evidence level:** чтение исходников и публичных материалов; live Revit и интеграционный elicitation bench не запускались. При сохранении сессии выполнен `uv run pytest tests/unit`: 790 passed, 3 skipped (6.66s), exit 0, на текущем рабочем дереве с прежними изменениями. Это регрессия существующего кода, не проверка ещё не реализованной защиты фазы 7. Ссылки на строки могут устареть — перепроверить текущие файлы при планировании.

## Architecture Outcome

Исходная идея пользователя: Jev проверяет вызовы revit-mcp-server, перехватывает опасные, объясняет причину и запрашивает подтверждение. После исследования Hermes сначала предлагался harness-owned gate. Пользователь явно отклонил ownership: вся безопасность должна находиться в текущем репозитории. Финальное направление: CPython policy/approval + минимальное enforcement в Revit extension, без правок Hermes.

Jev — typed semantic classifier, не gateway, не механизм авторизации и не человеческий интерфейс. Детерминированная локальная политика обязательна. Первый рабочий контур должен сохранять защиту без Jev; включение внешнего классификатора и конкретная модель требуют отдельного выбора и разрешения на обработку данных.

## Source Observations: This Repository

- `bridge.py`: serialization только в одном MCP-процессе; post-send failure может означать UNKNOWN. Это не authentication, не cross-process lock и не доказательство rollback.
- `revit_mcp/parameters.py`, set_parameter: после LookupParameter экземпляра есть fallback к типу; возможен массовый blast radius. Имена параметров не являются надёжной уникальной идентичностью; существующий get properties dedup по имени недостаточен как окончательный safety preflight.
- `revit_mcp/editing.py`, delete: doc.Delete возвращает каскадные ids после выполнения. Полный preview до удаления не реализован/не доказан. Проверить актуальные commit/outcome paths после Phase 4.
- `revit_mcp/transforms.py`: move/copy/rotate/mirror имеют разные эффекты; нет доказанного универсального безопасного размера смещения. Размер заданных ids не обязательно равен зависимому охвату.
- `tools/family_tools.py`, edit_family: reload обновляет копию семейства в проекте и может повлиять на множество экземпляров. Hidden add_shared в `revit_mcp/placement.py` не опубликован как dedicated create/bind shared-parameter tool.
- `revit_mcp/code_execution.py`: full arbitrary execution с doc/DB/revit/clr/System/builtins; анализ AST/текста и ответ Jev не являются sandbox. Сохраняется Phase 2 D-15.
- `pyproject.toml` / `uv.lock`: во время исследования mcp[cli] / MCP SDK 1.9.0, используется mcp.server.fastmcp.FastMCP. Не предполагать возможности свежего отдельного FastMCP; проверить текущий pin и поддержку server-initiated elicitation.
- Текущие owned namespace/package — genpro_revit_mcp. Старые тексты с /revit_mcp/ или плоскими sibling imports не переносить в новый код.

## Read-only Observations: Unchanged Hermes Fork

**Root:** `C:/Users/Admin/source/repos/MastermindServices/12_GenproAI_HermesFork`

Это сведения об интеграционном клиенте, НЕ список файлов для изменения.

- `tools/mcp_tool.py`, `_make_tool_handler` (~5711): trust gate вызывается до transport; затем session.call_tool(~5795). Политика missing trust по умолчанию full; untrusted + строго readOnlyHint=True пропускает confirmation. Аннотация — подсказка сервера, не доказательство.
- `mcp_prefixed_tool_name` (~6403): mcp__<sanitizedServer>__<sanitizedTool>. Для собственной безопасности не опираться на lossy prefix parsing.
- `hermes_cli/plugins.py`: approve directive вызывает общий request_tool_approval, а не само по себе подтверждает действие. Hook exceptions могут fail open; первый valid directive не равен обязательному deny-overrides.
- `tools/approval.py`, `_run_approval_gate` (~3415): YOLO, cached session/permanent approval и configurable unattended autoapproval означают, что обычный plugin approve не обеспечивает mandatory per-operation consent.
- `hermes_cli/middleware.py`: middleware exception до next_call может продолжить dispatch. Single-use next_call полезен, но не превращает middleware в fail-closed boundary.
- `tools/approval.py`, `request_elicitation_consent` (~5305): существующий MCP consent не проверяет YOLO/allowlist, gateway missing callback/exception -> decline, timeout -> cancel. Но accepts once/session/always; gateway использует общий approval queue. Не выдавать это за уже доказанный strict once contract для нашего сервера.
- `_await_gateway_decision` (~4177): одинаковые concurrent approvals могут coalesce; once предназначен только leader, session/always могут быть adopted followers. Поэтому одноразовость должна гарантироваться нашим enforcement даже при широком ответе клиентского UI.
- `resolve_gateway_approval` (~2634): queue поддерживает FIFO и resolve_all, request_id optional. Нельзя утверждать, что любое нажатие всегда связано с единственной операцией; нужно интеграционно проверить минимально допустимый контракт неизменённого клиента.
- `apps/desktop/src/components/assistant-ui/tool/approval.tsx` (~120–150): choices поддерживаются, request_id отправляется. Это code-reading evidence, не UI acceptance.
- `tools/mcp_tool.py` (~5927–5946, ~4856): reconnect/auth recovery может retry call; session-expired markers включают connection closed/broken pipe. Собственный permit/replay contract должен переживать транспортный повтор, не требуя изменения Hermes, и честно сообщать UNKNOWN.
- `tools/code_execution_tool.py`: вызовы зарегистрированных tools проходят через handle_function_call. Это не ограничивает прямой HTTP/OS доступ произвольного кода.

## Alternatives and Why They Are Not a Required Stack

| Option | Finding / role |
|---|---|
| Local deterministic rules | Минимальная необходимая основа, удобна для unit tests и редактируемой политики |
| Jev | Необязательная typed semantic assessment; не enforcement и не approval service |
| OPA/Rego | Возможный движок сложных политик, но для текущей узкой задачи отдельный сервис не обоснован |
| IBM ContextForge / Lasso MCP Gateway | Отдельные gateways; лишняя граница/развёртывание для принятого repo-owned scope. Нативный нужный HITL не подтверждён исследованием |
| LangGraph/LangChain HITL | Пригодно при владении агентным workflow, но не требуется для нашего MCP-owned контракта |
| Claude Code hooks / Hermes hooks | Клиентские механизмы, не единая серверная граница для разных клиентов |
| NeMo Guardrails | Общий guardrail toolkit; не заменяет Revit preconditions и одноразовое согласие |
| Agent Scan / former mcp-scan | Сканирование MCP не равно подтверждению конкретной мутации |
| Third-party jev-guard | Пример интеграции, не проверенная граница безопасности для Revit |

## Primary Public Sources Consulted

Перед реализацией сверить актуальные версии; сведения ниже не означают договорного разрешения передавать данные.

- https://docs.typesafe.ai/api.md — typed questions: choice, score, noul; state/model/questions.
- https://docs.typesafe.ai/confidence.md — confidence не гарантия безопасной операции.
- https://docs.typesafe.ai/models.md — выбирать фиксированную модель вместо неявного movable latest.
- https://docs.typesafe.ai/legal.md
- https://typesafe.ai/legal/privacy-policy
- https://typesafe.ai/legal/data-processing — отсутствие обучения на input не тождественно zero retention; ZDR/enterprise условия требуют проверки.
- https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation — стандарт, но не доказательство поддержки установленного SDK/client.
- https://www.openpolicyagent.org/docs
- https://github.com/IBM/mcp-context-forge
- https://ibm.github.io/mcp-context-forge/latest/using/plugins/lifecycle/
- https://github.com/lasso-security/mcp-gateway
- https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- https://code.claude.com/docs/en/hooks
- https://docs.nvidia.com/nemo/guardrails/latest/index.html
- https://github.com/invariantlabs-ai/mcp-scan
- https://github.com/leepokai/jev-guard

## Open Research / Decision Gates

1. Elicitation на точной связке SDK + неизменённый Hermes: capability negotiation, schema, user refusal/timeout, headless, параллельность, full code visibility, UI request association. Если нет надёжного пути, не подменять его agent-mediated approval.
2. Минимальный permit protocol: authentication отдельно от approval, bind к process incarnation/document lifetime/final args/policy version, replay state на Revit boundary, atomic consume, crash/retry outcomes. Подпись без single-use registry недостаточна.
3. TOCTOU: точное предусловие для параметра/типа/элемента, revalidation перед эффектом; никакой открытой транзакции во время human wait.
4. Пределы точного impact preview для удаления, type writes и arbitrary code. Если фактов нет — консервативное подтверждение с явным unknown либо запрет по правилу.
5. Общие параметры: разделить создание definition, project binding и family parameter, GUID, instance/type binding и существующие пути; необходимость нового typed tool не считать согласованной автоматически.
6. Deployment: operator-owned policy, управление секретами Phase 3/5, права доступа и отсутствие секретов в model arguments/logs; threat model при одинаковых ОС-правах и trusted execute exceptions.
7. Backlog 999.1: проверить актуальные измерения/фикс перед cross-process guarantee. Не менять автоматически прежние фазы или утверждать, что новый токен устраняет shared-handler cross-wiring.

## Acceptance Evidence To Produce Later

- Revit-free negative tests: invalid/missing policy, reload, Jev timeout/bad result, unsupported consent, spoofed approval, argument/document/policy changes, expiry, restart, duplicate delivery, concurrent permit consumption, direct protected route without auth/permit.
- Regression: all registered tools/routes covered, safe diagnostics remain available per Phase 5 contract, non-ASCII, text/plain, cold start, protocol stdout, honest rollback/partial/unknown and secret-safe audit.
- Отдельно разрешённый live bench на disposable моделях: actual document/type blast radius, один эффект при повторе, отмена без эффекта, неизменённый Hermes, restart-based loading. Unit tests не заменяют live proof.
