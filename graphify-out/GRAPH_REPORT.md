# Graph Report - revit-mcp-server  (2026-11-02)

## Corpus Check
- 639 files · ~1,046,684 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 15 file(s) not represented in the graph (top: .cmd 7, (none) 5, .lock 2)

## Summary
- 12213 nodes · 23203 edges · 708 communities (657 shown, 27 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 822 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e1b50c0f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- cmd
- Revit MCP Server README
- test_audit_entry.py
- test_textutils.py
- 2026-09-07 — пилот раскатки на удалённой станции, миграция на IronPython 3, шесть найденных багов.md
- test_conventions.py
- test_status_target.py
- extension.json
- test_parallel_installation.py
- Supported Tools (49) catalogue
- startup.py
- Revit L2 Floor Plan View Pane (Snowdon Towers sample model)
- textutils.py
- good_g4
- Как сделать свой инструмент для RevitMCP
- list_model_elements Tool Screenshot
- test_runtime_info.py
- test_registration.py
- Инструкция: как сделать свой инструмент для RevitMCP
- RevitMCP — установка и обновление
- parse_request_data
- contrib-kit/conventions.py
- test_document_contracts.py
- scripts/conventions.py
- configure_hermes.py
- Architecture
- test_identity_rendering.py
- intake_package.py
- rvt-mcp_Obsidian/00-home/index.md
- Contributing
- Codebase Concerns
- Coding Conventions
- FakeApplication
- All tool-facing dimensions are millimeters
- Route handlers never raise invariant
- except Exception: pass proliferation (60+ occurrences)
- Bulk routes report success despite per-element skips
- Port 48884 hardcoded sharp edge
- _revit_call single 30s timeout sharp edge
- mcp-server-for-revit
- permits.py
- AGENTS.md — правила для ИИ-ассистента в этом репозитории
- Агент: сборка пакета инструмента Revit MCP
- Набор разработчика инструментов Revit MCP
- Разработка инструментов Revit MCP
- Агент: разработка инструмента Revit MCP
- External Integrations
- Testing Patterns
- AGENTS.md — правила для ИИ-ассистента в этом наборе
- Technology Stack
- Codebase Structure
- Скилл Hermes для разработки инструментов
- new_tool.py
- test_g3_active_identity_uses_equals_even_when_hashes_collide
- 02-01 — selected-status vertical slice
- gate.py
- tools/utils.py
- bridge.py
- tests/test_phase2_preflight.py
- Stack Research
- probe_handler_overlap.py
- unit/test_phase2_preflight.py
- Phase 1 Plan 04: Two-Revit Bench and D-23 Overlap Probe Summary
- worksharing_tools.py
- test_audit_stdio.py
- Pattern Assignments
- Architecture Research: Trust Foundation (v0.1) Integration
- Critical Pitfalls
- documents.py
- Implementation Decisions
- Implications for Roadmap
- AccBench
- parametrize
- build_contrib_kit.py
- server.py
- test_bridge_serialization.py
- conftest.py
- Implementation Decisions
- Implementation Decisions
- mutated
- Pattern Assignments
- Implementation Decisions
- Implementation Decisions
- v1 Requirements
- test_process_tools.py
- Revision 2026-09-30 — interactive discussion with the user
- Phase 2: Live identity, ambiguity refusal, and multi-document addressing — Research
- Feature Research
- test_target_resolution.py
- Phase 1 Plan 06: d27-b Lock Coverage Summary
- Phase 2: Live identity, ambiguity refusal, and multi-document addressing - Discussion Log
- Сессия: MCP Bridge падал из-за прокси Windows
- test_section_basis.py
- Phase 1 Plan 02: Bounded Queue Wait, Honest Failures, Read-Only Allowlist Summary
- Goal Achievement
- Phase Details
- Сессия 2026-09-16
- test_g2_retained_binding_uses_equals_not_diagnostic_hashes
- test_bridge_secret_client.py
- Phase 1 Plan 03: Status Reports Its Target, Payload Ships bridge.py Summary
- Phase 1 Plan 08: Planning record after the 01-04 bench Summary
- Phase 1: Serialization and configurable addressing - Research
- Info
- revit-mcp-server
- test_phase7_tracer.py
- Что сделано
- Сессия 2026-09-11
- test_serialization_scope_docs.py
- Phase 1 Plan 01: Bridge Serialization and REVIT_PORT Summary
- Phase 1 Plan 07: Honest Scope Docs Summary
- Текущие приоритеты
- Хронология находок
- User Constraints (from CONTEXT.md)
- Common Pitfalls
- Common Pitfalls
- Project State
- Добавление возможности требует правок в четырёх местах (историческая: было 4, стало 2)
- Сессия 2026-10-06: Обсуждение фазы 1, перестановка фаз дорожной карты
- Tests
- Phase 3 (was 2): Secret gate and payload integrity (unit-verified) - Discussion Log
- connected
- Деплой — это два локальных процесса на рабочей станции инженера
- Добавление возможности требует правок в четырёх местах.md
- MCP-клиенты подключаются четырьмя транспортами
- 2026-09-08 — семь пользовательских сценариев на живой модели, детач-open, edit_family, фикс section-view и unicode-пробника
- Сессия 2026-09-10
- LLM.txt Context Document
- Phase 1 — Validation Strategy
- Phase 6: Structured audit log of true outcomes - Discussion Log
- Revit MCP Server — карта знаний
- sanitize_string превращает кириллицу в вопросительные знаки
- colors.py
- Файловая система — единственный выход наружу через IFC и импорт
- make_machine
- _dict
- Релизный план milestone v0.1, схема версий и тегов, коммит закрытия фазы 2
- Паттерн регистратора маршрутов
- Debug Session: param-write-rolls-back
- Phase 1 — Security
- Architecture Patterns
- User Constraints (from CONTEXT.md)
- Phase 02 — Validation Strategy
- Phase 4 (was 3): Honest outcomes on every mutating route - Discussion Log
- attribute_response
- test_audit_correlation.py
- unit/test_phase5_live_gate.py
- tests/test_phase5_live_gate.py
- tests/test_phase7_live_bench.py
- RSN-путь с обратными слешами уходил в ветку локальных файлов
- Каждая транзакция глушит модальные диалоги Revit.md
- Открытые вопросы по проекту
- test_inactive_document_reads.py
- install_audited_tools
- audit.py
- status.py
- sanitize_string превращает кириллицу в вопросительные знаки.md
- Порт 48884 захардкожен, настраивается только хост
- test_audit_writer.py
- test_trust_dialect.py
- test_policy_reload.py
- Валидация продукта — сборка Empire State Building в живом Revit 2027.md
- acc_result
- unit/test_phase6_live_audit.py
- format_response
- preflight.py
- unit/test_phase4_live_outcomes.py
- Сессия: откат транзакции больше не выдаётся за успех
- test_export_cannot_return_another_documents_png
- revit_post
- Architecture Patterns
- unit/test_phase2_live_identity.py
- Базы данных нет — состояние живёт в открытом документе Revit
- approval.py
- test_policy_loader.py
- gate_or_response
- sys.stdout может остаться закрытым StringIO до конца сессии Revit
- tests/test_phase4_live_outcomes.py
- test_routes_analysis_color_identity.py
- open_model
- test_routes_mep_parameter_identity.py
- scan_envelope_tolerance.py
- test_trust_secret.py
- test_revit_lookup.py
- test_phase7_preflight_route.py
- test_audit_secret.py
- _BenchProblem
- audit_support.py
- test_audit_tracer.py
- unit/test_phase7_live_bench.py
- mep_call
- read_entries
- test_secret_gate_e2e.py
- tests/test_phase6_live_audit.py
- 48 MCP-инструментов зеркалят 48 маршрутов pyRevit
- CallState
- make_db
- execute_code даёт неаутентифицированное исполнение кода внутри Revit
- test_scan_envelope_tolerance.py
- read_options
- Pattern Assignments
- good_evidence
- Validation Architecture
- Feasibility and Prescriptive Design
- test_permit_protocol.py
- _is_int
- Null document при переключении моделей
- current_document_descriptors
- test_tool_forwarding_model.py
- test_trust_integrity.py
- Plan 05-12 Summary
- _now
- test_phase5_gate_e2e.py
- test_routes_view_code_identity.py
- Выпуск релиза: сборка, пилот, раскатка
- test_probe_ipy_trust.py
- StepGrid
- FakeDB
- LocalStore
- handler_of
- Сессия: сравнение с апстримом revit-mcp-python и подтверждение родословной форка
- test_tool_forwarding_views.py
- line_of
- _reset
- Plan 05-15 Summary: live cleanup stage and phase verdict (PHASE5_GATE_OK, PASS)
- test_trust_listeners.py
- test_integrity_reader.py
- test_tool_forwarding_documents.py
- test_make_manifest.py
- _execute_dual
- test_policy_fop.py
- test_routes_document_interop_identity.py
- rig
- ok_single
- RouteDocument
- tests/test_phase2_live_identity.py
- webbridge MCP падает CONNECTION_CLOSED из-за занятого порта 10086
- inventory_support.py
- split_envelope
- single_argv
- object
- structure_tools.py
- forget_retired_path.py
- 01-01-PLAN.md
- 01-02-PLAN.md
- 01-03-PLAN.md
- 01-04-PLAN.md
- 01-05-PLAN.md
- 01-06-PLAN.md
- 01-07-PLAN.md
- 01-08-PLAN.md
- Code Examples
- Validation Architecture
- Sources
- Phase 2 Plan 02: Production identity recheck Summary
- read
- call
- retention_settings
- Phase 2 Plan 03: Process discovery, unambiguous default and per-incarnation serialization Summary
- good_record
- test_payload_ships_root_modules.py
- Standard Stack
- Sources
- Standard Stack
- 2026-09-14-open-models-and-null-document-fix.md
- Pattern Assignments
- Security Domain
- Code Examples
- Security Domain
- test_local_revit_bridge_ignores_environment_proxies
- .rvt-mcp_Obsidian/текущие приоритеты.md
- good_retained_g2
- values
- _cmd_g4_case
- Implementation Decisions
- Phase 7 — Session Research Inputs
- _Bound
- exception_diagnostics
- test_phase2_inventory.py
- Исследование Jev и серверной защиты, добавлена фаза 7
- Plan 05-13 Summary: live match stage (verdict PHASE5_GATE_OK, PASS)
- parametrize
- 02-20 — measured preflight and human decision
- test_phase5_gate_wiring.py
- FakeBench
- building_tools.py
- World
- Pattern Assignments
- mutate
- test_selected_elements_output.py
- Common Pitfalls
- _reason
- object
- Исполнение фазы 2 до плана 02-18, живая приёмка G3 и G4 нашла ошибку контекста API маршрутов
- document_tools.py
- IronPython Compatibility Notes
- Phase 2 Plan 04: Live document registry, list_documents and the mutation decision contract Summary
- arm
- _route
- 5. Приёмка пилота [Вы]
- check_integrity
- Холодный старт 0.9 с — это пол фреймворка, оптимизировать нечего
- _write
- test_collect_listener_owners_uses_only_bridge_listener_snapshot
- warm.py
- Phase 2 Plan 05: Explicit activation of one already-open saved document Summary
- test_phase5_status_diagnostics.py
- call
- Phase 2 Plan 06: Addressed summary and levels reads Summary
- 2026-10-26 — фаза 7, preflight и ФОП завершены, продолжить с 07-12
- test_current_descriptor_keeps_the_old_values_when_the_document_cannot_be_read
- Phase 2 Plan 19: Process lifecycle under multi-target discovery Summary
- Pattern Assignments
- Phase 5: Live secret gate and integrity enforcement - Context
- listing_uiapp
- describe_broken_path
- secret_tool.py
- World
- World
- Info
- test_phase7_rollout.py
- hash_normalized
- documentation_tools.py
- Определение общих параметров через ExternalDefinition ошибочно на BindingMap
- test_phase7_scope_docs.py
- Достижение цели
- Phase 7 Plan 12 Summary
- view_management_tools.py
- Policy
- probe_ipy_trust.py
- 2026-10-15 — планирование фазы 2, preflight и проверка 20 планов
- object
- arm_family
- RouteDocument
- Phase 4: Honest outcomes on every mutating route - Research
- _preflight_dual
- _cmd_lines
- Phase 2 Plan 07: G3/G4 production recheck Summary
- Phase 2 Plan 14: Explicit document guard on MEP, parameter, room, structure and tag mutations Summary
- Phase 2 Plan 16: Response provenance renderer and per-target Phase-1 regression Summary
- Phase 3 Plan 04: Payload Integrity Slice Summary
- Phase 03 Plan 09: WR-01 share-drop corroboration Summary
- Plan 05-14 Summary: live corrupt stage (verdict PHASE5_GATE_OK, PASS)
- _through_the_bridge
- _share_outage
- test_broken_paths.py
- Common Pitfalls
- Corporate deployment (closed network)
- Phase 2 Plan 12: Explicit document guard on annotation, building, colors and detail mutations Summary
- Phase 2 Plan 13: Explicit document guard on save, documentation, editing, interop and family mutations Summary
- Phase 2 Plan 15: Transform/view guard, process-scoped open_model and the D-15 execute exception Summary
- Phase 2 Plan 17: Exhaustive tool and route regression inventory Summary
- Phase 3 Plan 06: Bind classifier and IronPython 3 proof Summary
- Info
- parametrize
- Первичная настройка и пилотная раскатка
- Phase 3 Plan 01: Secret gate pure logic and request envelope Summary
- Phase 3 Plan 02: Build-side secret tool Summary
- Phase 3 Plan 03: Bridge secret loading and the 401 visibility pair Summary
- Phase 3 Plan 05: Integrity Reader and Generator Hardening Summary
- Phase 3 Plan 07: Secret and Manifest Build Wiring Summary
- Phase 3 Plan 08: Live D-04 Probe and Recorded Result Summary
- Phase 3: Secret gate and payload integrity (unit-verified) - Research
- Phase 2 Plan 08: target/document on analysis, annotation, building, clash and color tools Summary
- Phase 2 Plan 09: target/document on detail, documentation, save, editing and family tools Summary
- Phase 2 Plan 10: target/document on interop, MEP, model, parameter and room tools Summary
- Phase 2 Plan 11: target/document on structure, tag, transform, view and worksharing tools Summary
- make_db
- make_db
- Phase 5 Plan 01: Tracer gate on /create_level/ Summary
- Phase 2 Plan 18: Live acceptance Summary
- Info
- Релизный план milestone v0.1 «Доверенный мост»
- FakeMCP
- Common Pitfalls
- Goal Achievement
- registry.py
- Locked Decisions
- execute_code остаётся аварийным люком для отсутствующих инструментов
- startup_tree
- Phase 6 Plan 04: Correlation and the published schema change Summary
- object
- annotation_tools.py
- Два процесса Revit.exe могут слушать 48884 одновременно без ошибки
- Architecture Patterns
- RouteDocument
- register_everything
- 03-07-PLAN.md
- 03-09-PLAN.md
- Phase 3 — Validation Strategy
- Warnings
- Goal Achievement
- Phase 6 Plan 01: Structured audit log tracer slice Summary
- 03-01-PLAN.md
- 03-02-PLAN.md
- 03-03-PLAN.md
- 03-04-PLAN.md
- _folders
- load
- Bare DB.ElementId(int) в Revit 2027 падает на неоднозначности перегрузок
- 03-05-PLAN.md
- 03-06-PLAN.md
- 03-UAT.md
- Phase 5 Plan 02: Gate and strip across annotation, building, colors, detail, analysis and clash Summary
- Phase 6 Plan 02: Full honest schema 1 and exact call set Summary
- Phase 6 Plan 03: Request side of the entry and secret redaction Summary
- Phase 5 Plan 03: Gate document, documentation, editing, interop and placement Summary
- FList
- 03-08-PLAN.md
- Validation Architecture
- load
- load
- Phase 5 Plan 04: Gate mep, parameters, rooms, structure and tags Summary
- _load
- parametrize
- Phase 6: Structured audit log of true outcomes - Research
- refusal
- Phase 5 Plan 05: Gate transforms, view management, model open, arbitrary code and document activation Summary
- Standard Stack
- Code Examples
- Sources
- Phase 5 Plan 09: D-06 envelope tolerance scanner Summary
- Phase 5: Live secret gate and integrity enforcement - Research
- _FakeHashlib
- Phase 6 Plan 05: Retention, stdio proof and documentation Summary
- call
- Phase 4 Plan 08: D-02 static rule and scaffold/docs update Summary
- Goal Achievement
- Security Domain
- test_save_as_that_lands_elsewhere_never_claims_the_requested_path
- Phase 5 Plan 07: Status diagnostics Summary
- Phase 5 Plan 16: Bridge envelope and startup gate initialization Summary
- Phase 4 Plan 01: Honest outcomes tracer (tag_elements) Summary
- Phase 4 Plan 02: mep, rooms, structure and set_parameter outcomes Summary
- arm_export
- load_record
- Phase 4 Plan 03: building, annotation and detail outcomes Summary
- Phase 4 Plan 04: delete, export, link and save outcomes Summary
- Phase 4 Plan 05: view and code route outcomes Summary
- Phase 4 Plan 06: documentation and placement outcomes Summary
- Phase 4 Plan 07: colour route outcomes Summary
- Phase 4 Plan 10: Live outcome gate instrument Summary
- User Constraints (from CONTEXT.md)
- Phase 4 Plan 09: Outcome docstrings for the mutation tools Summary
- Phase 7 Plan 11 Summary
- policy.py
- call_name
- 2026-10-25 — приёмка фазы 6, UAT 4 из 4, SECURITY.md 38 из 38, фаза закрыта, R4 отложен
- Common Pitfalls
- Phase 4 — Validation Strategy
- Phase 5 Plan 08: Staged publish, rollback and manifest modes Summary
- Architecture Patterns
- test_policy_decisions.py
- 04-01-PLAN.md
- world
- _edit_family
- Докстринг инструмента — это контракт для модели, а не для разработчика
- Machine
- User Constraints (from CONTEXT.md)
- Phase 5: Live secret gate and integrity enforcement - Discussion Log
- User Constraints (from CONTEXT.md)
- Phase 5 — Validation Strategy
- Tests
- Architecture Patterns
- Pilot fixes — offline verification
- Pattern Assignments
- 04-04-PLAN.md
- 04-09-PLAN.md
- 05-01-PLAN.md
- test_deploy_libpaths.py
- test_policy_tool.py
- 04-02-PLAN.md
- 04-03-PLAN.md
- 04-05-PLAN.md
- 04-06-PLAN.md
- 04-07-PLAN.md
- 04-08-PLAN.md
- Validation Architecture
- 05-07-PLAN.md
- 05-08-PLAN.md
- Plan 05-10 Summary
- 05-11-PLAN.md
- 05-13-PLAN.md
- 05-16-PLAN.md
- Validation Architecture
- Phase 05 - Security
- 2026-10-26 — пилот Phase 7, live STOP из-за аудита
- Phase 06 — Validation Strategy
- Многоэкземплярная приёмка — поочерёдный запуск, только stdio, стоп при перехвате чтения
- SegmentHandler
- fixture
- Путь с кириллицей не открывался — виноваты бэкслеши, а не кодировка
- Сессия 2026-10-07: исполнение фазы 1, стенд двух Revit нашёл подмену ответов pyRevit, фаза остановлена на перепланирование
- 2026-10-24 — исполнение фазы 5, три живых стадии PHASE5_GATE_OK, верификация human_needed
- failure
- Сессия: открытие без отсоединения создаёт локальную копию, RSN-путь больше не зависит от журнала
- _read_ast
- 04-10-PLAN.md
- Phase 04 Plan 11: Live outcome gate Summary
- Architecture Patterns
- 05-02-PLAN.md
- 05-03-PLAN.md
- 05-04-PLAN.md
- 05-05-PLAN.md
- 05-06-PLAN.md
- Plan 05-06 Summary
- 05-09-PLAN.md
- 05-10-PLAN.md
- Plan 05-11 Summary
- 05-12-PLAN.md
- 05-14-PLAN.md
- 05-15-PLAN.md
- Code Examples
- mep_tools.py
- 04-11-PLAN.md
- Code Examples
- Sources
- Standard Stack
- Sources
- _load_module
- _swallower_hits
- Standard Stack
- Security Domain
- Security Domain
- permit.py
- FakeWall
- test_secret_pipeline.py
- test_bare_py2_builtin_is_caught_even_inside_a_broad_except
- test_the_compatibility_idioms_are_allowed
- test_clean_module_produces_no_violations
- test_code_execution_rejects_missing_document_before_transaction
- test_the_open_list_mirrors_trust_exactly
- test_intake_runs_the_whole_unit_suite_on_the_scratch_copy
- cmd.exe читает config.cmd в консольной кодовой странице, не в UTF-8 файла
- Исполнение фазы 7 — шесть планов завершены
- mcp 1.11+ импортирует pywin32, а embeddable CPython payload его не находит
- FakeChild
- Гейт холодного старта мерил SMB-задержку шары, а не старт сервера
- pyRevit Reload при включённых Routes валит Revit на первом же запросе
- Phase 7 Plan 08 Summary
- 2026-10-25 — быстрая задача open_model, локальная копия по умолчанию, штамп вместо удаления, запасной набор «Оси и уровни»
- FopError
- 2026-10-23 — исполнение фазы 4, живой шлюз PHASE4_OUTCOMES_OK, фаза закрыта, R2 пропущен
- Общие параметры определяются по префиксу ForgeTypeId, а не по типу Definition
- test_direct_real_permits_five_posts_and_no_secret_or_mac_in_record
- test_read_failure_after_post_persists_stop_and_nonzero_count
- Паттерн регистратора инструментов с инъекцией транспорта
- Открытие центральной без отсоединения шло мимо CreateNewLocal
- Пересекающиеся запросы pyRevit получают чужой ответ, а их код не выполняется
- reply_for
- 06-03-PLAN.md
- 06-05-PLAN.md
- bench
- _Categories
- Machine
- Phase 7 Plan 13 Summary
- register_colors_tools
- Phase 7 Plan 10 Summary
- register_family_tools
- Маршруты pyRevit без аргументов uiapp, uidoc, doc выполняются вне контекста Revit API
- Сессия 2026-09-06 — план и реализация деплоя в контур компании, инструмент запуска Revit
- 2026-09-07 — правка заголовка страницы Confluence через Kiwi Web Bridge, диагностика конфликта порта webbridge
- detail_tools.py
- Сессия: журнал Revit Server закреплён на обязательном UNC-пути
- Продукт — это мост между ИИ-ассистентом и Autodesk Revit
- classify_dual
- record_secret_occurrences
- 06-01-PLAN.md
- 06-02-PLAN.md
- 06-04-PLAN.md
- 06-06-PLAN.md
- Validation Architecture
- test_preflight_fake_client_records_valid_identity
- Регистрация — автообнаружение вместо рукописных списков
- _build_parser
- Goal Achievement
- 06-07-PLAN.md
- Standard Stack
- Sources
- test_permit_concurrency.py
- Common Pitfalls
- _rehearsal_verdict
- Phase 6 Plan 06: The human-run live audit gate Summary
- Security Domain
- Code Examples
- Phase 7 Plan 01: MCP SDK upgrade to 1.30 Summary
- Phase 7: Repository-owned mutation safety and human approval - Research
- Паттерн обработчика маршрута — валидация, транзакция, сериализация.md
- Phase 7 Plan 02: Confirm-class tracer through policy, window, permit and Revit verifier Summary
- Phase 7 Plan 04: Two-layer policy (base + operator) with hot reload and build staging Summary
- Phase 7 Plan 05: Permit protocol hardening Summary
- Phase 07 Plan 07: Permit-ready unit request plumbing Summary
- User Constraints (from CONTEXT.md)
- decide
- _process_token
- scratch_payload_gate.py
- test_process_identity.py
- Info
- Phase 7 Plan 03: Payload pywin32 shim and transport proof Summary
- Сессия 2026-10-06/07: планирование фазы 1 — сериализация и `REVIT_PORT` разбиты на пять планов
- Аудитория — BIM-инженеры на Windows с Revit и pyRevit
- policy_tool.py
- Gate-by-Gate Answers (from the orchestrator's research priorities)
- Phase quick-261025-ld5 Plan 01: open_model defaults to a local copy Summary
- Принят checkpoint 02-20 и реализован selected status 02-01
- fill
- refuses
- Tests
- Architecture Patterns
- Phase 06 — Security
- Phase 7: Repository-owned mutation safety and human approval - Discussion Log
- Phase 7 — Validation Strategy
- Phase 7 Plan 06: Complete policy inventory and decisions Summary
- _send
- Цены нет — проект под лицензией MIT
- 07-02-PLAN.md
- 07-04-PLAN.md
- 07-06-PLAN.md
- 07-12-PLAN.md
- clash_tools.py
- parametrize
- Разработчики инструментов работают без доступа к репозиторию
- initialize_process_identity
- Стек делится на CPython 3.11+ и IronPython 2.7
- room_tools.py
- test_outcome_docstrings.py
- CLAUDE.md Contributor Guide
- Bench фазы 7 — preflight и итог операции имеют общий call_id
- Phase 06 Plan 07: Live audit gate Summary
- 07-01-PLAN.md
- 07-03-PLAN.md
- 07-05-PLAN.md
- 07-07-PLAN.md
- 07-08-PLAN.md
- 07-09-PLAN.md
- 07-10-PLAN.md
- 07-11-PLAN.md
- 07-13-PLAN.md
- 07-14-PLAN.md
- Строки из Revit прогоняются через sanitize_string
- Bench фазы 7 — отсутствие audit и неверный ответ уровней давали ложное доказательство
- Сессия 2026-10-07: перепланирование фазы 1 после d27-b — три gap-плана вместо 01-05
- format_response прячет поля ответа за ключом message
- 2026-09-04 — настройка окружения, восстановление Routes после сбоя, находка бага с кириллицей
- Планирование фазы 7: четырнадцать планов в девять волн, SDK 1.30, требования SAFE-01..21
- Validation Architecture
- 261025-ld5-PLAN.md
- get_revit_process_status различает Revit закрыт от Revit без документа
- Phase 7 Plan 09 Summary
- HermesCallback
- tag_tools.py
- Standard Stack
- Code Examples
- Sources
- operator_path
- open_model по умолчанию создаёт локальную копию, существующую переименовывает со штампом
- 2026-10-26 — 07-13 bench проверен офлайн, продолжить с 07-14
- Деплой в контур — сервер раздаёт файлы, оба процесса живут на станции
- Защита операций Revit принадлежит MCP-репозиторию, не Hermes Fork
- tag_walls_call
- Фаза 7 — preflight закрепляет документ, повторная проверка фактов и ФОП отменяет устаревшее согласие
- _resolve_port
- Revit MCP — индекс
- _FailureSwallower
- netstat на ru-RU Windows печатает заголовки в cp866, строгий парсер возвращал None
- Threat Model and Security Domain (ASVS L1, block on high)
- Общая venv повреждена при обновлении SDK из-за работающих MCP-сессий
- start_revit — единственная пара инструментов без Revit-стороны
- Исполнители фазы 2 идут последовательно в основном дереве, коммиты по путям
- Перепланирование фазы 1 — новые gap-планы вместо переписывания 01-05, d27-c в бэклог
- Под замок все маршруты кроме status, одна общая запись сервера без копий
- Релиз предлагается на границе фазы по RELEASES.md, а не готовится параллельно
- Схема версий — метка сборки с именем релиза, rc-теги и пилотный share
- Живая приёмка фазы 2, 8 из 9 критериев, G6 остался stop, верификация gaps_found
- Планирование фазы 3, восемь планов секрета и целостности, проверка прошла со второго раунда
- Планирование фазы 4, одиннадцать планов честных исходов мутаций, проверка прошла со второго раунда
- Обсуждение фазы 5, шлюз секрета в каждом маршруте, payload раньше ext, откат через ext-previous
- Планирование фазы 5, шестнадцать планов шлюза секрета и целостности, проверка прошла со второго раунда
- 2026-10-25 — исполнение фазы 6, семь планов, живой шлюз PHASE6_AUDIT_OK, верификация human_needed
- Обсуждение фазы 6: журнал всех операций с промптом пользователя, call_id в конверте, 180 дней
- test_post_counts_before_transport_exception_and_strips_exception_text
- Обсуждение фазы 7: подтверждение через elicitation Hermes, одно «Да» на одну операцию, ФОП компании
- Планирование фазы 6: семь планов журнала аудита в семь волн, проверка прошла с первого раунда
- test_batch_config_encoding.py
- _dotnet_listeners

## God Nodes (most connected - your core abstractions)
1. `format_response()` - 231 edges
2. `revit_post()` - 162 edges
3. `gate_or_response()` - 122 edges
4. `call()` - 111 edges
5. `handler_of()` - 110 edges
6. `attribute_response()` - 94 edges
7. `get_element_id_value()` - 82 edges
8. `request_document_selector()` - 80 edges
9. `cmd()` - 79 edges
10. `get_element_name()` - 77 edges

## Surprising Connections (you probably didn't know these)
- `Available Tools (31) - historical tool count` --semantically_similar_to--> `Supported Tools (49) catalogue`  [INFERRED] [semantically similar]
  LLM.txt → README.md
- `Shared parameter ForgeTypeId classification rule` --references--> `_classify_definition()`  [EXTRACTED]
  CLAUDE.md → revit_mcp/parameters.py
- `ElementId cross-version helper invariant` --references--> `get_element_id_value()`  [EXTRACTED]
  CLAUDE.md → revit_mcp/utils.py
- `Revit L2 Floor Plan View Pane (Snowdon Towers sample model)` --references--> `get_view (pyRevit route, revit_mcp/views.py)`  [INFERRED]
  images/get_view_tool.png → revit_mcp/views.py
- `Multi-Version Revit Support (2024-2027)` --references--> `get_element_id_value()`  [EXTRACTED]
  README.md → revit_mcp/utils.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Domain mirroring pattern instantiated by clash detection** — revit_mcp_clash, tools_clash_tools, startup, tools_init, claude_domain_mirroring_pattern [INFERRED 0.85]
- **get_view end-to-end flow: Claude request → MCP tool → pyRevit route → rendered floor plan** — images_get_view_tool_claude_desktop_panel, images_get_view_tool_get_view_tool_call_card, tools_view_tools_get_revit_view, revit_mcp_views_get_view, images_get_view_tool_revit_l2_view_pane [INFERRED 0.85]
- **MCP Tool Invocation and Response Flow (Claude to Revit)** — images_list_model_tool_list_model_elements_tool, images_list_model_tool_snowdon_towers_model, images_list_model_tool_claude_chat_ui, images_list_model_tool_model_analysis_summary [INFERRED 0.85]
- **Two-Runtime architecture (CPython MCP server + IronPython Revit extension)** — main, tools_utils, tests_test_init_latency, startup, revit_mcp_utils, claude_two_runtime_rule [INFERRED 0.85]
- **Three docs describing the same 2/3/4-step tool registration workflow** — claude_adding_capability_workflow, readme_creating_your_own_tools, llm_writing_new_functions_workflow [INFERRED 0.90]

## Communities (708 total, 27 thin omitted)

### Community 0 - "cmd"
Cohesion: 0.08
Nodes (49): capture_flow(), case_argv(), cmd(), g6_write(), load(), mutation_ready(), observe(), The whole engineer procedure through the CLI; returns the raw file path. (+41 more)

### Community 1 - "Revit MCP Server README"
Cohesion: 0.19
Nodes (10): MCP client -> main.py+tools -> startup.py+revit_mcp -> Revit API architecture, FastMCP framework, Prerequisites (Windows, Revit, pyRevit, uv), Revit MCP Server README, Quick Start install steps, Transport Modes (stdio / sse / streamable-http / combined), requirements.txt Dependency Pins, httpx==0.28.1 package (+2 more)

### Community 2 - "test_audit_entry.py"
Cohesion: 0.06
Nodes (79): One JSON line, the secret (raw and JSON-escaped) replaced on the finished text.…, serialize_entry(), args_entry(), block(), build(), code_entry(), doc_body(), meta() (+71 more)

### Community 3 - "test_textutils.py"
Cohesion: 0.04
Nodes (81): _descriptor(), _doubt_refusal(), The refusal for a registry in doubt, or None when the observation is clean., resolve_document over an observation already taken for this request., (title, path) read from ``document`` now; a value that cannot be read keeps its…, _read_title_and_path(), _refusal(), _resolve_observed() (+73 more)

### Community 4 - "2026-09-07 — пилот раскатки на удалённой станции, миграция на IronPython 3, шесть найденных багов.md"
Cohesion: 0.05
Nodes (39): configure_hermes.py писал в файл, которого Hermes на Windows не читает, Обход / исправление, Причина, Связанное, Симптом, Урок, pyRevit определяет unicode как алиас str в IronPython 3, ломая NameError-проверку, Диагностика (+31 more)

### Community 5 - "test_conventions.py"
Cohesion: 0.08
Nodes (20): _commit_hits(), Mechanical enforcement of the conventions in CONTRIBUTING.md. Everything here…, DB.ElementId(<BuiltInCategory>) is a different, valid overload., The idiom that silently produced bytes on IronPython 3., `commit = t.Commit` then `commit()` is the same bypass, one step removed., The same function in any other file is not exempt., A commit in a function merely nested beside the exempt one is caught., test_commit_detector_catches_a_bare_commit() (+12 more)

### Community 6 - "test_status_target.py"
Cohesion: 0.19
Nodes (26): _FakeMCP, _make_get(), _old_permit_line(), object, Collects the functions registered through @mcp.tool()., get_revit_status names the MCP target it is wired to (D-06, IDENT-05). The tool…, _run_status(), _secret_lines() (+18 more)

### Community 7 - "extension.json"
Cohesion: 0.15
Nodes (12): author, author_profile, builtin, default_enabled, dependencies, description, image, name (+4 more)

### Community 8 - "test_parallel_installation.py"
Cohesion: 0.10
Nodes (17): check_config(), main(), Read shared pyRevit Routes settings; never change another extension's host., loader_tree(), load(), route(), fixture, parametrize (+9 more)

### Community 9 - "Supported Tools (49) catalogue"
Cohesion: 0.13
Nodes (15): POST route text to /execute_code/ to test without restart, /execute_code/ unauthenticated escape hatch, Tool docstrings are the API contract, check_clashes tool (README entry), execute_revit_code tool (README entry), get_revit_model_info tool (README entry), save_document tool (README entry), Supported Tools (49) catalogue (+7 more)

### Community 10 - "startup.py"
Cohesion: 0.14
Nodes (19): Adding a capability: 4-place edit workflow, Writing New Functions: 3-part registration process, Creating Your Own Tools (2 files + 2 registration lines), _domain_modules(), _load_package(), Discover and register every route domain with the API. Each domain is…, Revit MCP Extension Startup Discovers and registers all MCP route modules, then…, Load our source tree under an owned name without importing revit_mcp. pyRevit… (+11 more)

### Community 11 - "Revit L2 Floor Plan View Pane (Snowdon Towers sample model)"
Cohesion: 0.39
Nodes (8): Claude Desktop Chat Panel (L2 Floor Plan request), get_view Tool-Call Card (embedded floor plan thumbnail), Project Browser — Area Plans (Rentable) → L2 node selected, Revit L2 Floor Plan View Pane (Snowdon Towers sample model), get_view Tool Screenshot (Claude + Revit), Snowdon Towers Sample Architectural.rvt (demo model), get_view (pyRevit route, revit_mcp/views.py), get_revit_view (MCP tool, tools/view_tools.py)

### Community 12 - "textutils.py"
Cohesion: 0.04
Nodes (85): current_descriptor(), The guard's descriptor with title and path re-read from the resolved Document…, describe_broken_path(), local_backup_dir(), local_copy_stamp(), _normalise_workset_name(), pick_axes_levels_workset(), Pure text helpers for the Revit MCP extension. This module is deliberately free… (+77 more)

### Community 13 - "good_g4"
Cohesion: 0.15
Nodes (14): _case(), good_g4(), test_g4_allowed_case_activated_only_in_command_context_is_stop(), test_g4_allowed_case_that_did_not_activate_the_target_is_stop(), test_g4_allowed_case_that_raised_a_dialog_is_stop(), test_g4_blank_or_missing_api_is_stop(), test_g4_failed_case_must_carry_an_explicit_refusal_policy(), test_g4_missing_case_is_stop() (+6 more)

### Community 14 - "Как сделать свой инструмент для RevitMCP"
Cohesion: 0.06
Nodes (30): 10. Куда смотреть ещё, 1. Общая картина, 2.1. Проверьте, что Revit и RevitMCP работают, 2.2. Найдите Python, 2.3. Распакуйте набор разработчика, 2.4. Установите VS Code и Kilo Code, 2.5. Откройте папку набора в VS Code, 2. Настройка среды (один раз) (+22 more)

### Community 15 - "list_model_elements Tool Screenshot"
Cohesion: 0.60
Nodes (6): list_model_elements Tool Screenshot, Claude Desktop Chat UI Pane, list_model_elements MCP Tool Call, Model Analysis Summary (18 Levels, 54 Rooms), Revit Project Browser Panel (Views Tree), Snowdon Towers Sample Architectural Model

### Community 16 - "test_runtime_info.py"
Cohesion: 0.07
Nodes (33): load_status(), route(), Load revit_mcp/status.py under a synthetic package; security, trust, integrity…, test_dotnet_listeners_adapter_gives_none_without_the_clr(), test_status_block_uninitialized_state_reports_unverifiable_read_error(), test_status_block_with_listener_callable_variants(), Product version and runtime facts in /status/ and get_revit_status. Needs no…, _runtime() (+25 more)

### Community 17 - "test_registration.py"
Cohesion: 0.10
Nodes (26): The guard against a silently dropped tool. Adding or removing a tool is a…, The whole point of discovery-with-isolation. One developer's broken module must…, An exception inside register_*_tools is contained the same way., A route module whose registrar is missing or misspelled is invisible., Both halves must exist, or a route is unreachable from the MCP client. Derived…, Unit tests for convention-based registration on both halves. Registration used…, Helpers must stay helpers -- otherwise discovery would need to load them., The premise that makes alphabetical registration order safe. Every cross-module… (+18 more)

### Community 18 - "Инструкция: как сделать свой инструмент для RevitMCP"
Cohesion: 0.08
Nodes (24): Инструкция: как сделать свой инструмент для RevitMCP, Куда смотреть ещё, Частые ошибки, Часть 1. Что вы вообще делаете, Часть 2. Настройка среды. Один раз, Часть 3. Делаем инструмент, Часть 4. Проверка, Часть 5. Сдача (+16 more)

### Community 19 - "RevitMCP — установка и обновление"
Cohesion: 0.10
Nodes (21): 1. Плагин внутри Revit, 2. Сервер запускается, 3. Гена видит инструменты, RevitMCP — установка и обновление, Если уже установлен другой Revit MCP, Если что-то не работает, Красный индикатор у сервера в Гене, Настройка MCP в Гене (+13 more)

### Community 20 - "parse_request_data"
Cohesion: 0.07
Nodes (38): Add the constant document_scope notice and the process identity to a reply.…, Register code execution routes with the API., register_code_execution_routes(), _execute_code(), _stamp_exception(), _document_handle(), True when two file paths name the same file (case and slash style ignored)., The item an outcome names for a save: `preferred` when given, else the path the… (+30 more)

### Community 21 - "contrib-kit/conventions.py"
Cohesion: 0.11
Nodes (36): _blank_strings_and_comments(), check_element_id(), check_encoding_cookie(), check_ironpython_dialect(), check_package(), check_route_module(), check_route_registrar(), check_tool_module() (+28 more)

### Community 22 - "test_document_contracts.py"
Cohesion: 0.03
Nodes (92): activation_reply(), addressing_registrar(), callee_names(), code_identifiers(), documents_tree(), FakeMCP, function_node(), host_app_trap() (+84 more)

### Community 23 - "scripts/conventions.py"
Cohesion: 0.08
Nodes (47): _blank_strings_and_comments(), _calls_named(), check_commit_goes_through_report(), check_element_id(), check_encoding_cookie(), check_ironpython_dialect(), check_package(), check_request_parsing() (+39 more)

### Community 24 - "configure_hermes.py"
Cohesion: 0.14
Nodes (22): build_block(), detect_indent(), die(), find_mcp_servers(), hermes_config_path(), hermes_is_running(), main(), Parse with ruamel; return an error string, or None if the doc is usable. (+14 more)

### Community 25 - "Architecture"
Cohesion: 0.10
Nodes (19): Anti-Patterns, Architectural Constraints, Architecture, Bare `ElementId(int)` / `.IntegerValue`, Component Responsibilities, Cross-Cutting Concerns, Data Flow, Entry Points (+11 more)

### Community 26 - "test_identity_rendering.py"
Cohesion: 0.05
Nodes (80): doc(), FakeMCP, register(), provenance(), object, parametrize, One provenance renderer for every tool result (02-16, D-05/D-06/D-15,…, What the bridge hands back for a complete reply from a proven process. (+72 more)

### Community 27 - "intake_package.py"
Cohesion: 0.19
Nodes (18): apply_package(), check_collisions(), check_layout(), _fail(), main(), _norm(), Exception, Only the manifest, the two halves, optional tests and notes. (+10 more)

### Community 28 - "rvt-mcp_Obsidian/00-home/index.md"
Cohesion: 0.05
Nodes (24): open_model с overwrite_local удаляет существующую локальную копию вместе с несинхронизированной работой, Живой шлюз с двумя Revit — запуск второго экземпляра и триггер отката, Классификатор требовал Project1, а русский Revit называет первый проект Проект1, Перекрывающиеся записи в один Revit получают чужой ответ и теряют запись, G6 воспроизведён, Раннер живого шлюза фазы 5 слал пустое тело и падал на хвостовой строке моста, Checkpoint 02-20 принят с измеренными ограничениями, production status проверяется отдельно, G3 и G4 production приняты после исправления контекста API, живая приёмка идёт секциями по риску, Живая приёмка 02-18 — секциями по риску (+16 more)

### Community 29 - "Contributing"
Cohesion: 0.15
Nodes (12): Adding a capability: two files, Commits, Contributing, Gate every non-GET route, How discovery finds your module, Non-negotiable invariants, Testing, The two-runtime rule (read this first) (+4 more)

### Community 30 - "Codebase Concerns"
Cohesion: 0.18
Nodes (10): Codebase Concerns, Dependencies at Risk, Fragile Areas, Known Bugs, Missing Critical Features, Performance Bottlenecks, Scaling Limits, Security Considerations (+2 more)

### Community 31 - "Coding Conventions"
Cohesion: 0.18
Nodes (10): Code Style, Coding Conventions, Comments, Error Handling, Function Design, Import Organization, Logging, Module Design (+2 more)

### Community 32 - "FakeApplication"
Cohesion: 0.03
Nodes (32): DuplicatingApplication, FakeApplication, FakeBuiltInCategory, FakeCollector, FakeDocument, FakeInfo, FakeNetType, FlagDocument (+24 more)

### Community 40 - "permits.py"
Cohesion: 0.09
Nodes (27): MCP Module for Revit Integration Contains all MCP route handlers organized by…, _blank(), check_and_consume(), derive_key(), hmac_sha256(), _is_int(), normalize_route(), HMAC-SHA256 digest bytes of ``msg`` under ``key`` (RFC 2104, block size 64). (+19 more)

### Community 41 - "AGENTS.md — правила для ИИ-ассистента в этом репозитории"
Cohesion: 0.20
Nodes (9): AGENTS.md — правила для ИИ-ассистента в этом репозитории, Главное правило: НЕ создавай файлы вручную, Два рантайма — не смешивать, Докстринг инструмента — это контракт для модели, Запреты, Коммиты, Куда смотреть дальше, Обязательный цикл (+1 more)

### Community 42 - "Агент: сборка пакета инструмента Revit MCP"
Cohesion: 0.20
Nodes (9): Агент: сборка пакета инструмента Revit MCP, Если застрял, Чего не делать никогда, Шаг 0. Выяснить задачу до того, как писать код, Шаг 1. Сгенерировать каркас, Шаг 2. Заполнить TODO, Шаг 3. Проверить форму, Шаг 4. Проверить поведение на живой модели (+1 more)

### Community 43 - "Набор разработчика инструментов Revit MCP"
Cohesion: 0.20
Nodes (9): Главное, что ломается, Докстринг — это не документация, Как это выглядит целиком, Набор разработчика инструментов Revit MCP, Не редактируйте `conventions.py`, Чего в пакет не входит, Четыре команды, Что делает `probe` и почему он важен (+1 more)

### Community 44 - "Разработка инструментов Revit MCP"
Cohesion: 0.20
Nodes (9): 1. Назначение, 2. Когда применять и когда нет, 3. Входные данные и грабли, 4. Эталон, 5. Процедура, 6. Выходные данные, 7. Запреты, 8. Приёмка (+1 more)

### Community 45 - "Агент: разработка инструмента Revit MCP"
Cohesion: 0.20
Nodes (9): Агент: разработка инструмента Revit MCP, Если застрял, Чего не делать никогда, Шаг 0. Понять задачу, прежде чем писать, Шаг 1. Проверить, не существует ли это уже, Шаг 2. Сгенерировать каркас, Шаг 3. Заполнить TODO, Шаг 4. Проверить (+1 more)

### Community 46 - "External Integrations"
Cohesion: 0.20
Nodes (9): APIs & External Services, Authentication & Identity, CI/CD & Deployment, Data Storage, Environment Configuration, External Integrations, Integration Risks, Monitoring & Observability (+1 more)

### Community 47 - "Testing Patterns"
Cohesion: 0.20
Nodes (9): Common Patterns, Coverage, Fixtures and Factories, Mocking, Test File Organization, Test Framework, Test Structure, Test Types (+1 more)

### Community 48 - "AGENTS.md — правила для ИИ-ассистента в этом наборе"
Cohesion: 0.25
Nodes (7): AGENTS.md — правила для ИИ-ассистента в этом наборе, Главное правило: НЕ создавай файлы вручную, Два рантайма — не смешивать, Докстринг инструмента — это контракт для модели, Если застрял, Запреты, Обязательный цикл

### Community 49 - "Technology Stack"
Cohesion: 0.25
Nodes (7): Configuration, Frameworks, Key Dependencies, Languages, Platform Requirements, Runtime, Technology Stack

### Community 50 - "Codebase Structure"
Cohesion: 0.25
Nodes (7): Codebase Structure, Directory Layout, Directory Purposes, Key File Locations, Naming Conventions, Special Directories, Where to Add New Code

### Community 51 - "Скилл Hermes для разработки инструментов"
Cohesion: 0.33
Nodes (5): Грабли frontmatter, Куда его класть, Почему копия, а не ссылка, Скилл Hermes для разработки инструментов, Что ещё нужно сделать в том репозитории

### Community 52 - "new_tool.py"
Cohesion: 0.46
Nodes (7): _add_to_manifest(), build_route_source(), _fail(), main(), Scaffold a new capability: both halves plus the manifest entry. uv run python…, Build the Revit-side scaffold for ``domain`` without writing it., _write()

### Community 54 - "02-01 — selected-status vertical slice"
Cohesion: 0.33
Nodes (5): 02-01 — selected-status vertical slice, Boundaries and deviations, Checks, Implemented, Next boundary

### Community 55 - "gate.py"
Cohesion: 0.24
Nodes (10): _base_policy_status(), _expected_tools(), main(), _pywin32_paths(), r"""Acceptance check for a deployed install: spawn server.py over stdio and…, mcp>=1.11 imports pywin32 on Windows; the embeddable CPython ignores…, (status, message) for the staged secret against MCP_SECRET_FILE. status is…, (status, message): the base policy shipped beside ``here`` loads and validates.… (+2 more)

### Community 56 - "tools/utils.py"
Cohesion: 0.09
Nodes (26): revit_mcp/utils.py vs tools/utils.py naming collision, Revit process discovery: one shared entry, an exact selector per call. The…, Register Revit process discovery tools., register_target_tools(), discover_revit_targets(), _unusable_line(), _usable_line(), _blank_document() (+18 more)

### Community 57 - "bridge.py"
Cohesion: 0.04
Nodes (85): _address_of(), _audit(), _check_owner(), _client_of(), _close_state(), _conflict_text(), _dispatch(), _dispatch_core() (+77 more)

### Community 58 - "tests/test_phase2_preflight.py"
Cohesion: 0.10
Nodes (45): classify_all(), classify_g1(), classify_g2(), classify_g3(), classify_g4(), classify_g5(), _classify_retained_g2(), _cmd_classify() (+37 more)

### Community 59 - "Stack Research"
Cohesion: 0.06
Nodes (32): Alternatives Considered, `asyncio.Lock` vs `asyncio.Semaphore(1)` vs queue+worker `[CPython]`, Capability 1 — Shared-secret authentication on mutating routes, Capability 2 — Payload integrity verification with self-restore at startup, Capability 3 — Serializing mutating calls, Capability 4 — Structured local audit log (JSONL), Concurrent-write concerns if two Revit instances run, Configurable port (+24 more)

### Community 60 - "probe_handler_overlap.py"
Cohesion: 0.11
Nodes (25): build_code(), classify_phase(), count_runs(), d27_triggered(), _describe(), main(), marker_for(), _payload() (+17 more)

### Community 61 - "unit/test_phase2_preflight.py"
Cohesion: 0.08
Nodes (15): _direction(), good_g3(), _guarded_nodes(), ids of every node lexically inside the body of an `if CONFIRM_ACTIVATION:`., Unit tests for the Phase 2 preflight classifier (gates G1-G5). The operator…, test_g3_accessor_that_reads_the_active_document_blocks_the_document_only_path(), test_g3_active_document_changed_between_before_and_after_is_stop(), test_g3_code_path_other_than_document_only_is_stop() (+7 more)

### Community 62 - "Phase 1 Plan 04: Two-Revit Bench and D-23 Overlap Probe Summary"
Cohesion: 0.07
Nodes (27): Accomplishments, Auto-fixed Issues, Bench deviations (not code deviations), Bench record, Decisions Made, Deviations from Plan, Environment and deviations from the bench script, Follow-up for re-planning (`/gsd-plan-phase 1 --gaps`) (+19 more)

### Community 63 - "worksharing_tools.py"
Cohesion: 0.10
Nodes (31): parametrize, RSN:// path handling on the CPython side. A complete Revit Server URI must…, test_backslash_path_bypasses_the_journal_too(), test_backslash_spelling_normalises_to_the_slash_form(), test_complete_path_bypasses_the_journal(), explode(), test_complete_paths_are_recognised(), test_incomplete_paths_are_not_recognised() (+23 more)

### Community 64 - "test_audit_stdio.py"
Cohesion: 0.09
Nodes (16): FakeRevitServer, do_GET(), do_POST(), _send(), An in-process fake Revit on a loopback port, for a real subprocess to talk to.…, object, parametrize, skipif (+8 more)

### Community 65 - "Pattern Assignments"
Cohesion: 0.08
Nodes (25): `bridge.py` (transport service, target-aware request-response and keyed serialization), Contract-sweep inventory, Existing Revit mutation route modules (routes, CRUD/request-response), File Classification, Metadata, No Analog Found, Pattern Assignments, Phase 2: Live identity, ambiguity refusal, and multi-document addressing — Pattern Map (+17 more)

### Community 66 - "Architecture Research: Trust Foundation (v0.1) Integration"
Cohesion: 0.08
Nodes (25): Architecture Research: Trust Foundation (v0.1) Integration, Build pipeline: where secret-injection and manifest-generation belong, Confidence flag, Evaluating the options for each of the four concerns, Facts established by reading the code, Hook points in the pyRevit extension lifecycle (verified against pyrevit-master source), Object model for "the set of reachable Revit instances", Question 1 — Structural answer for cross-cutting concerns under "no cross-domain imports" (+17 more)

### Community 67 - "Critical Pitfalls"
Cohesion: 0.08
Nodes (25): Critical Pitfalls, How to read this document, Integration Gotchas, "Looks Done But Isn't" Checklist, Pitfall 10: Timing-unsafe secret comparison, combined with the text/plain contract, is easy to get subtly wrong in IronPython 3, Pitfall 11: The audit log records the route's claimed outcome, not `commit_and_report`'s actual one — reproducing the silent-success problem one layer up, in the very feature meant to catch it, Pitfall 12: Audit log writes from IronPython under concurrent Revit instances (or the async CPython side) corrupt or interleave on Windows, and the file grows without bound, Pitfall 13: The audit log (or its error paths) leaks the secret, full model file paths, or PII-bearing element data — the opposite failure mode from Pitfall 11, equally damaging (+17 more)

### Community 68 - "documents.py"
Cohesion: 0.06
Nodes (47): activation_refusal_reason(), _active_of(), collect_document_levels(), collect_document_summary(), _count_elements(), _db(), _element_id_value(), _file_exists() (+39 more)

### Community 69 - "Implementation Decisions"
Cohesion: 0.08
Nodes (24): Canonical References, Carried over from the 2026-09-23 `--auto` round (still valid), Claude's Discretion, Code, Deferred Ideas, Established Patterns, Existing Code Insights, History (+16 more)

### Community 70 - "Implications for Roadmap"
Cohesion: 0.08
Nodes (23): Architecture Approach, Confidence Assessment, Critical Pitfalls, Executive Summary, Expected Features, Gaps to Address, Implications for Roadmap, Key Findings (+15 more)

### Community 71 - "AccBench"
Cohesion: 0.10
Nodes (47): acc_authorize(), acc_observe(), acc_start(), AccBench, AccProcess, build_acc(), flow_collision(), flow_g2() (+39 more)

### Community 72 - "parametrize"
Cohesion: 0.10
Nodes (26): good_g2(), _only_pair_kind(), parametrize, test_cli_snippet_prints_the_snippet(), test_complete_record_reaches_a_continue_verdict(), test_every_required_field_missing_is_stop(), test_g2_a_measured_negative_for_one_kind_continues_when_the_other_kind_has_a_real_pair(), test_g2_a_missing_pair_needs_a_described_non_reproducible_attempt() (+18 more)

### Community 74 - "server.py"
Cohesion: 0.50
Nodes (3): _pywin32_paths(), r"""Entry point Hermes launches. Ships as <install root>\app\server.py.…, mcp>=1.11 imports pywin32 on Windows; the embeddable CPython ignores…

### Community 75 - "test_bridge_serialization.py"
Cohesion: 0.05
Nodes (64): _get_lock(), _is_locked(), /ai_filter/?x=1" -> "ai_filter": tolerate query strings and slashes., Whether a call must wait its turn in the queue. False only for a GET whose…, _route_key(), anyio_backend(), _Ctx, _FakeMCP (+56 more)

### Community 76 - "conftest.py"
Cohesion: 0.15
Nodes (14): _allow_all_authorizer(), _audit_base_dir(), _isolated_audit_log(), _isolated_permit_registry(), _no_live_revit_from_the_bridge(), refuse(), refusing_client(), fixture (+6 more)

### Community 77 - "Implementation Decisions"
Cohesion: 0.10
Nodes (20): Canonical References, Claude's Discretion, Deferred Ideas, Established Patterns, Existing Code Insights, Implementation Decisions, Integration Points, Phase 3 (was 2): Secret gate and payload integrity (unit-verified) - Context (+12 more)

### Community 78 - "Implementation Decisions"
Cohesion: 0.08
Nodes (23): Canonical References, Claude's Discretion, Deferred Ideas, Established Patterns, Existing Code Insights, Implementation Decisions, Integration Points, Phase 6: Structured audit log of true outcomes - Context (+15 more)

### Community 79 - "mutated"
Cohesion: 0.17
Nodes (21): good_g1(), good_g5(), mutated(), A copy of builder() with the dotted `path` set (or deleted if value is DELETE)., test_g1_boolean_is_not_accepted_as_a_port_or_pid(), test_g1_either_allowed_observation_method_continues(), test_g1_observation_method_must_be_a_disclosed_allowed_value(), test_g1_pid_mismatch_against_the_os_snapshot_is_stop() (+13 more)

### Community 80 - "Pattern Assignments"
Cohesion: 0.10
Nodes (19): `bridge.py` (service, request-response + serialization), `deploy/build-payload.cmd` (MOD), Docs (D-15, D-21, D-26, Pitfall 8, Pitfall 10), Error-string contract, File Classification, `main.py` (wiring), Metadata, No Analog Found (+11 more)

### Community 81 - "Implementation Decisions"
Cohesion: 0.10
Nodes (19): Canonical References, Claude's Discretion, Deferred Ideas, Established Patterns, Existing Code Insights, Implementation Decisions, Integration Points, Phase 4 (was 3): Honest outcomes on every mutating route - Context (+11 more)

### Community 82 - "Implementation Decisions"
Cohesion: 0.08
Nodes (25): Canonical References, Claude's Discretion, Deferred Ideas, Documents and user-visible behavior, Established Patterns, Existing Code Insights, G2 preflight correction — 2026-10-16, G3/G4 preflight measurements — 2026-10-16 (+17 more)

### Community 83 - "v1 Requirements"
Cohesion: 0.11
Nodes (18): Future Requirements, Out of Scope, Requirements: revit-mcp-server — milestone v0.1 «Доверенный мост», Traceability, v1 Requirements, Аудит (AUDIT), Безопасность мутаций (SAFE), Восстановление целостности (RESTORE) (+10 more)

### Community 84 - "test_process_tools.py"
Cohesion: 0.10
Nodes (47): collision(), FakeServer, _fixed_installation(), hung(), ok(), popen(), PopenRecorder, fixture (+39 more)

### Community 85 - "Revision 2026-09-30 — interactive discussion with the user"
Cohesion: 0.12
Nodes (15): Claude's Discretion, Claude's Discretion, Deferred Ideas, Deferred Ideas, Phase 1: Serialization and configurable addressing - Discussion Log, Revision 2026-09-30 — interactive discussion with the user, Roadmap reorder, Бюджет времени (+7 more)

### Community 86 - "Phase 2: Live identity, ambiguity refusal, and multi-document addressing — Research"
Cohesion: 0.12
Nodes (15): Additional Hard Constraints Discovered in Source (не входят в CLAUDE.md), Architectural Responsibility Map, Assumptions Log, Don't Hand-Roll, Environment Availability, Mandatory Decision Gates, Metadata, Open Questions (+7 more)

### Community 87 - "Feature Research"
Cohesion: 0.12
Nodes (15): Add After Validation (v1.x), Anti-Features (Commonly Requested, Often Problematic), Comparable-System Feature Analysis, Dependency Notes, Differentiators (Competitive Advantage), Feature Dependencies, Feature Landscape, Feature Prioritization Matrix (+7 more)

### Community 88 - "test_target_resolution.py"
Cohesion: 0.04
Nodes (89): _candidate_lines(), discover_targets(), _discovery_ports(), _netstat_endpoint_port(), parse_netstat_listener_rows(), parse_target(), unique_keys(), Decode a local incarnation selector, not an authentication credential. (+81 more)

### Community 89 - "Phase 1 Plan 06: d27-b Lock Coverage Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+6 more)

### Community 90 - "Phase 2: Live identity, ambiguity refusal, and multi-document addressing - Discussion Log"
Cohesion: 0.13
Nodes (14): A mutation with no document selector, Boundary changes and discretion, Claude's Discretion, Deferred Ideas (2026-09-23 snapshot), Explicit mutation targeting an inactive document, Interactive revision — 2026-10-14, Phase 2: Live identity, ambiguity refusal, and multi-document addressing - Discussion Log, Reading an inactive document and comparing models (+6 more)

### Community 91 - "Сессия: MCP Bridge падал из-за прокси Windows"
Cohesion: 0.13
Nodes (13): MCP Bridge использовал Windows proxy для localhost, Исправление, Причина, Проверка гипотезы, Проверка после исправления, Симптом, Диагностика, Изменения (+5 more)

### Community 92 - "test_section_basis.py"
Cohesion: 0.19
Nodes (14): _cross(), _determinant(), parametrize, Guard the section view's basis-vector handedness. Revit accepts a section box…, The `elif view_type == "section":` block, up to the next branch., up x direction gives determinant +1; direction x up always gives -1., The ordering Revit accepts. Reversing it breaks every section request., The exact regression: it failed silently, with an empty error message. (+6 more)

### Community 93 - "Phase 1 Plan 02: Bounded Queue Wait, Honest Failures, Read-Only Allowlist Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+5 more)

### Community 94 - "Goal Achievement"
Cohesion: 0.14
Nodes (13): Anti-Patterns Found, Behavioral Spot-Checks, Data-Flow Trace (Level 4), Gaps Summary, Goal Achievement, Human Verification Required, Key Link Verification, Observable Truths (ROADMAP success criteria, as revised by plan 01-08) (+5 more)

### Community 95 - "Phase Details"
Cohesion: 0.13
Nodes (14): Backlog, Overview, Phase 1: Serialization and configurable addressing, Phase 2: Live identity, ambiguity refusal, and multi-document addressing, Phase 3: Secret gate and payload integrity (unit-verified), Phase 4: Honest outcomes on every mutating route, Phase 5: Live secret gate and integrity enforcement, Phase 6: Structured audit log of true outcomes (+6 more)

### Community 96 - "Сессия 2026-09-16"
Cohesion: 0.14
Nodes (14): 1. Диагностика: кодировка исключена, а не предположена, 2. Причина, 3. Фикс — детектор, а не «чинилка», 4. Профилактика в докстрингах, 5. Merge с веткой Гены (6b0cf5a), Изменённые файлы, Информация о сессии, Краткое описание (+6 more)

### Community 97 - "test_g2_retained_binding_uses_equals_not_diagnostic_hashes"
Cohesion: 0.21
Nodes (4): test_g2_retained_binding_uses_equals_not_diagnostic_hashes(), test_os_listener_snapshot_failures_never_fall_back_to_incomplete_cmdlet(), test_os_listener_snapshot_uses_full_netstat_without_shell_or_port_filter(), run()

### Community 98 - "test_bridge_secret_client.py"
Cohesion: 0.08
Nodes (42): load_secret(), Return a copy of a request body that carries the shared secret under…, The secret text held by the bytes of a secret file, or None; never raises.…, The shared secret from the first existing _bridge_secret file, or None.…, The first 8 hex characters of the SHA-256 of a configured secret, else None.…, secret_fingerprint(), _secret_from_bytes(), with_envelope() (+34 more)

### Community 99 - "Phase 1 Plan 03: Status Reports Its Target, Payload Ships bridge.py Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+4 more)

### Community 100 - "Phase 1 Plan 08: Planning record after the 01-04 bench Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Open items carried forward (backstop, not resolved here), Phase 1 Plan 08: Planning record after the 01-04 bench Summary, Requirements status (+4 more)

### Community 101 - "Phase 1: Serialization and configurable addressing - Research"
Cohesion: 0.15
Nodes (12): Architectural Responsibility Map, Assumptions Log, Don't Hand-Roll, Environment Availability, Metadata, Open Questions, Package Legitimacy Audit, Phase 1: Serialization and configurable addressing - Research (+4 more)

### Community 102 - "Info"
Cohesion: 0.15
Nodes (12): IN-01: The module docstring says the lock is never held while waiting for Revit, which is false, IN-02: Wording of the UNKNOWN message is inaccurate for failures that are not timeouts, IN-03: `main.py` catches every `ValueError` raised during `import bridge` as a REVIT_PORT refusal, IN-04: Docs: undocumented third standalone test script, stale runtime row, opaque internal IDs in user-facing docs, IN-05: Test hygiene: brittle doc pins and weak slices, Info, Phase 1: Code Review Report, Summary (+4 more)

### Community 103 - "revit-mcp-server"
Cohesion: 0.15
Nodes (12): Active, Constraints, Context, Core Value, Current Milestone: v0.1 Доверенный мост, Evolution, Key Decisions, Out of Scope (+4 more)

### Community 104 - "test_phase7_tracer.py"
Cohesion: 0.14
Nodes (38): hermes_callback(), A callback that answers the scripted steps in order, then declines., anyio_backend(), machine(), parameter(), anyio, fixture, parametrize (+30 more)

### Community 105 - "Что сделано"
Cohesion: 0.15
Nodes (13): 1. Автообнаружение вместо двух рукописных барреллей, 2026-09-07 — автообнаружение регистрации, тестовый уровень, приёмка инструментов без доступа к репозиторию, 2. Изоляция отказа — осознанное отступление от прежнего решения, 3. Тестовый уровень без Revit — закрыт приоритет №1, 4. Приёмка инструментов без доступа к репозиторию, 5. Исправлена ошибочная формулировка про GenproMCP, 6. Документация стала доступна клонирующему, 7. Схема развёртывания (артефакт) (+5 more)

### Community 106 - "Сессия 2026-09-11"
Cohesion: 0.15
Nodes (13): 1. Раздел «Нет вкладки pyRevit», 2. Раздел «Красный индикатор у сервера в Гене», 3. Ужесточено требование к версии pyRevit, 4. Wiki обновлена, Изменённые файлы, Информация о сессии, Краткое описание, Открытое (+5 more)

### Community 107 - "test_serialization_scope_docs.py"
Cohesion: 0.29
Nodes (12): _bridge_docstring(), Doc pins for the honest scope of serialization (SER-05, d27-b, IDENT-05). The…, Other tests slice bridge.py's source on these markers; the docstring comes…, _read(), test_serialization_scope_deploy_readme_names_bridge_and_port(), test_serialization_scope_docstring_has_no_transport_markers(), test_serialization_scope_no_overclaims(), test_serialization_scope_no_two_entry_user_docs() (+4 more)

### Community 108 - "Phase 1 Plan 01: Bridge Serialization and REVIT_PORT Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Next Phase Readiness, Performance, Phase 1 Plan 01: Bridge Serialization and REVIT_PORT Summary (+3 more)

### Community 109 - "Phase 1 Plan 07: Honest Scope Docs Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 1 Plan 07: Honest Scope Docs Summary, Self-Check: PASSED (+3 more)

### Community 110 - "Текущие приоритеты"
Cohesion: 0.17
Nodes (12): 0. ~~Починить sanitize_string~~ — исправлено (третья сессия), -1. Деплой в контур компании — пилот идёт, движок сменился на IronPython 3, 1. ~~Сделать тестовый уровень, не требующий Revit~~ — закрыто (2026-09-07), 2. ~~Покрыть тестами format_response~~ — закрыто вместе с пунктом 1 (2026-09-07), 3. Закрыть execute_code за флагом, 4. Перестать возвращать traceback наружу, 5. Сделать пакетные ошибки видимыми, 6. Ускорить clash-детект предфильтром по bounding box (+4 more)

### Community 111 - "Хронология находок"
Cohesion: 0.17
Nodes (12): 1. Публикация ушла в дерево-двойник (кодовая страница cmd.exe), 2026-09-07 — пилот раскатки на удалённой станции, миграция на IronPython 3, шесть найденных багов, 2. Гейт холодного старта мерил не то, 3. Hermes-блок писался не в тот файл, 4. Расширение не грузилось: устаревший disabled=true, 5. Миграция на IronPython 3 — самая крупная находка сессии, 6. Ручная вставка Hermes-конфига с универсальными путями, Контекст задачи (+4 more)

### Community 112 - "User Constraints (from CONTEXT.md)"
Cohesion: 0.18
Nodes (11): Carried over from the 2026-09-23 `--auto` round (still valid), Claude's Discretion, Deferred Ideas (OUT OF SCOPE), Honest scope (SER-05), Instance selection model, Live acceptance, Locked Decisions, Roadmap order (+3 more)

### Community 113 - "Common Pitfalls"
Cohesion: 0.18
Nodes (11): Common Pitfalls, Pitfall 10: port-to-instance mapping is by start order and moves, Pitfall 1: Believing "read-only" calls are safe while a mutation is in flight, Pitfall 2: `asyncio.Lock` bound to a dead event loop across tests, Pitfall 3: the default anyio plugin runs every async test on `trio`, Pitfall 4: empty timeout messages and the pre-send/post-send distinction, Pitfall 5: two existing tests read `main.py` source, Pitfall 6: `budget` unbound in the `except TimeoutError` handler (+3 more)

### Community 114 - "Common Pitfalls"
Cohesion: 0.18
Nodes (11): Common Pitfalls, Pitfall 10: Фаза 2 незаметно реализует политику Фазы 5, Pitfall 1: Порт считается идентичностью процесса, Pitfall 2: Коллизия обнаруживается после запроса, Pitfall 3: Один глобальный lock сериализует разные Revit, Pitfall 4: Кэш активного документа переживает смену UI, Pitfall 5: Title/path как уникальный ключ документа, Pitfall 6: Полный `/model_info/` объявлен safe для неактивного документа (+3 more)

### Community 115 - "Project State"
Cohesion: 0.15
Nodes (12): Accumulated Context, Blockers/Concerns, Current Position, Decisions, Deferred Items, Pending Todos, Performance Metrics, Project Reference (+4 more)

### Community 116 - "Добавление возможности требует правок в четырёх местах (историческая: было 4, стало 2)"
Cohesion: 0.18
Nodes (11): 1. Обработчик маршрута — `revit_mcp/<домен>.py`, 2. Регистрация маршрута — `startup.py`, 3. Обёртка инструмента — `tools/<домен>_tools.py`, 4. Регистрация инструмента — `tools/__init__.py`, 5. (плюс) README, Добавление возможности требует правок в четырёх местах (историческая: было 4, стало 2), Куда что кладётся, Почему четыре, а не одно (+3 more)

### Community 117 - "Сессия 2026-10-06: Обсуждение фазы 1, перестановка фаз дорожной карты"
Cohesion: 0.18
Nodes (11): Бюджет времени (D-11..D-14), Модель выбора экземпляра (D-02..D-06), Основные решения (Phase 1 Context D-01..D-18), Открытые вопросы на фазу 2, Перестановка фаз, Приёмка (D-16..D-18), Результат, Сериализация (D-07..D-10) (+3 more)

### Community 118 - "Tests"
Cohesion: 0.20
Nodes (9): 1. Repeat the overlap probe on the fleet's pyRevit 6.5.5 (scripts/probe_handler_overlap.py --port 48884) against one live Revit, 2. Measure GET /model_info/ under overlap with a held mutation on a live Revit, 3. Simultaneous launch of two Revit instances, then Get-NetTCPConnection -LocalPort 48884,48885 -State Listen and /routes/sisters, 4. IDENT-05 / SC5 beyond two Revit 2024.3.30 instances: run tests/test_two_instance_targets.py (--ports 48884,48885) on a cross-version pair and on pyRevit 6.5.5, 5. Read deploy/USER-GUIDE.md (Russian) for over-claims about serialization or two-Revit use, Current Test, Gaps, Summary (+1 more)

### Community 119 - "Phase 3 (was 2): Secret gate and payload integrity (unit-verified) - Discussion Log"
Cohesion: 0.20
Nodes (9): Claude's Discretion, Deferred Ideas, Phase 3 (was 2): Secret gate and payload integrity (unit-verified) - Discussion Log, Бинд не на loopback, Генерация и хранение секрета, Конверт и транспорт секрета, Манифест и состояния целостности, Размещение кода (+1 more)

### Community 120 - "connected"
Cohesion: 0.09
Nodes (39): connected(), Phase 7 test helper: an in-memory MCP client whose elicitation callback answers…, An initialized ClientSession against ``server``; no callback means no…, AcceptingSession, authorization_request(), build_server(), call(), context_for() (+31 more)

### Community 121 - "Деплой — это два локальных процесса на рабочей станции инженера"
Cohesion: 0.20
Nodes (10): Деплой — это два локальных процесса на рабочей станции инженера, Отладка вручную, Предпосылки, Связанное, Чего нет, Шаг 1 — pyRevit и Routes Server, Шаг 2 — установка расширения (Revit-половина), Шаг 3 — проверка связи (+2 more)

### Community 122 - "Добавление возможности требует правок в четырёх местах.md"
Cohesion: 0.04
Nodes (50): Архитектура — это мост между двумя рантаймами Python, Ключевые свойства, Кто за что отвечает, Ограничения, которые нельзя обойти, Путь одного запроса, Связанное, Revit-половина по размеру, Дерево репозитория (+42 more)

### Community 123 - "MCP-клиенты подключаются четырьмя транспортами"
Cohesion: 0.20
Nodes (10): MCP-клиенты подключаются четырьмя транспортами, Инспектор, Как устроен комбинированный режим, Подключение Claude Desktop / Claude Code, Подключение Cursor / Windsurf, Правило stdio, которое нельзя нарушать, Режимы, Связанное (+2 more)

### Community 124 - "2026-09-08 — семь пользовательских сценариев на живой модели, детач-open, edit_family, фикс section-view и unicode-пробника"
Cohesion: 0.20
Nodes (10): 2026-09-08 — семь пользовательских сценариев на живой модели, детач-open, edit_family, фикс section-view и unicode-пробника, Диагностика окружения перед тестами, Добавлены три новых инструмента (51 → 54), Контекст задачи, Найдены и исправлены три реальных бага, Обновлена документация, Открытые вопросы / долг, Прогон всех семи сценариев на реальной модели (+2 more)

### Community 125 - "Сессия 2026-09-10"
Cohesion: 0.20
Nodes (10): 1. HEAD отгружал 19 доменов из 23 — контракт text/plain разрезан пополам, 2. pyRevit ругается `repository not owned by current user` при каждом обновлении, Два независимых дефекта, найденные и исправленные, Информация о сессии, Ключевые файлы, Краткое описание, На следующую сессию, Связанные заметки (+2 more)

### Community 126 - "LLM.txt Context Document"
Cohesion: 0.17
Nodes (12): Directory junction deployment (pyRevit Extensions -> repo), pyRevit Reload-after-edit crash risk, IronPython 2.7, Available Tools (31) - historical tool count, LLM.txt Context Document, LLM.txt Project Architecture (stale nested-extension layout), pyRevit Routes Core API, 'pyRevit' term definition (+4 more)

### Community 127 - "Phase 1 — Validation Strategy"
Cohesion: 0.22
Nodes (8): Manual-Only Verifications, Per-Task Verification Map, Phase 1 — Validation Strategy, Sampling Rate, Test Infrastructure, Validation Audit 2026-10-14, Validation Sign-Off, Wave 0 Requirements

### Community 128 - "Phase 6: Structured audit log of true outcomes - Discussion Log"
Cohesion: 0.22
Nodes (8): call_id до Revit или нет, Claude's Discretion, Deferred Ideas, Phase 6: Structured audit log of true outcomes - Discussion Log, «Кто» и персональные данные, Существующий контекст, Хранение и срок, Что попадает в журнал

### Community 129 - "Revit MCP Server — карта знаний"
Cohesion: 0.22
Nodes (9): Atlas — устройство системы, Revit MCP Server — карта знаний, Бизнес и продукт, Интеграции, Начать отсюда, Отладка — что уже ломалось, Паттерны кода, Решения (+1 more)

### Community 130 - "sanitize_string превращает кириллицу в вопросительные знаки"
Cohesion: 0.22
Nodes (9): sanitize_string превращает кириллицу в вопросительные знаки, Варианты (исторический список на момент первой сессии), Доказательство, что фикс не нужен по существу, Как в итоге исправлено, Почему не было исправлено сразу, Причина, Связанное, Симптом (+1 more)

### Community 131 - "colors.py"
Cohesion: 0.06
Nodes (49): Shared parameter ForgeTypeId classification rule, revit_mcp/colors.py 1246-line size sharp edge, color_splash tool (README entry), modify_element / set_parameter tools (README entry), Modify category (9 tools), check_view_compatibility(), clean_parameter_value_for_json(), clear_element_colors() (+41 more)

### Community 132 - "Файловая система — единственный выход наружу через IFC и импорт"
Cohesion: 0.22
Nodes (9): IFC-экспорт, Загрузка семейств, Картинки видов, Риск, Связанное, Связывание и импорт внешних файлов, Сохранение модели, Файловая система — единственный выход наружу через IFC и импорт (+1 more)

### Community 133 - "make_machine"
Cohesion: 0.11
Nodes (33): make_machine(), Install a fresh Machine behind the real bridge (netstat and HTTP replaced)., release_machine(), minimal_kwargs(), Minimal valid arguments for every tool that the per-module forwarding suites…, machine(), anyio_backend(), build_server() (+25 more)

### Community 134 - "_dict"
Cohesion: 0.09
Nodes (44): _acc_captured(), _activation_counts(), _auth_state(), _check_g3_read(), _count_sends(), _dict(), _engineer(), _find_document() (+36 more)

### Community 135 - "Релизный план milestone v0.1, схема версий и тегов, коммит закрытия фазы 2"
Cohesion: 0.40
Nodes (4): Результаты, Релизный план milestone v0.1, схема версий и тегов, коммит закрытия фазы 2, Решения, Что остаётся

### Community 136 - "Паттерн регистратора маршрутов"
Cohesion: 0.25
Nodes (8): Обязательные элементы, Паттерн регистратора маршрутов, Подключение, Порядок импортов, Приватные хелперы, Связанное, Соглашения об именах эндпоинтов, Форма

### Community 137 - "Debug Session: param-write-rolls-back"
Cohesion: 0.25
Nodes (7): Constraints for this investigation, Current Focus, Debug Session: param-write-rolls-back, Eliminated, Evidence, Resolution, Symptoms

### Community 138 - "Phase 1 — Security"
Cohesion: 0.25
Nodes (7): Accepted Risks Log, Phase 1 — Security, Security Audit 2026-10-14, Security Audit Trail, Sign-Off, Threat Register, Trust Boundaries

### Community 139 - "Architecture Patterns"
Cohesion: 0.25
Nodes (8): Anti-Patterns to Avoid, Architecture Patterns, Component Responsibilities (файл → ответственность), Pattern 1: Identity append после форматирования (уже принятый в проекте), Pattern 2: Отказ до отправки (fail-closed preflight), Pattern 3: Резолв документа на момент запроса, Recommended Project Structure, System Architecture Diagram

### Community 140 - "User Constraints (from CONTEXT.md)"
Cohesion: 0.25
Nodes (8): Claude's Discretion, Deferred Ideas (OUT OF SCOPE), Documents and user-visible behavior, Locked Decisions, Process and document identity, Research and acceptance guardrails, Selecting the Revit process, User Constraints (from CONTEXT.md)

### Community 141 - "Phase 02 — Validation Strategy"
Cohesion: 0.25
Nodes (7): Manual-Only Verifications, Per-Task Verification Map, Phase 02 — Validation Strategy, Preflight and Early-Wave Test Requirements, Sampling Rate, Test Infrastructure, Validation Sign-Off

### Community 142 - "Phase 4 (was 3): Honest outcomes on every mutating route - Discussion Log"
Cohesion: 0.25
Nodes (7): Claude's Discretion, Deferred Ideas, Phase 4 (was 3): Honest outcomes on every mutating route - Discussion Log, Видимость частичного отказа, Единая форма исхода, Охват миграции, Проверка

### Community 143 - "attribute_response"
Cohesion: 0.04
Nodes (162): Transaction + suppress_warnings(t) invariant, Analysis Module for Revit MCP Handles element filtering, room data, material…, Register all analysis routes with the API, register_analysis_routes(), _ai_element_filter_handler(), _analyze_model_statistics_handler(), _export_room_data_handler(), _get_material_quantities_handler() (+154 more)

### Community 144 - "test_audit_correlation.py"
Cohesion: 0.18
Nodes (27): anyio_backend(), audit_id_of(), build_server(), multi_call_probe(), one_post_probe(), route_probe(), two_posts_probe(), call() (+19 more)

### Community 145 - "unit/test_phase5_live_gate.py"
Cohesion: 0.06
Nodes (49): _args(), _auth(), _base(), _Bridge, getting(), cleanup_ok(), _Client, corrupt_ok() (+41 more)

### Community 146 - "tests/test_phase5_live_gate.py"
Cohesion: 0.07
Nodes (65): capture(), _add(), _auth(), _bridge(), classify_phase(), classify_stage(), _cleanup(), _cmd_run() (+57 more)

### Community 147 - "tests/test_phase7_live_bench.py"
Cohesion: 0.10
Nodes (55): _add(), _audit_entries(), _bridge(), classify(), _cmd_classify(), _cmd_direct(), _cmd_ingest(), _cmd_preflight() (+47 more)

### Community 148 - "RSN-путь с обратными слешами уходил в ветку локальных файлов"
Cohesion: 0.25
Nodes (8): 1. Полный RSN-путь всё равно шёл в журнал, 2. Написание с обратными слешами не распознавалось как RSN, RSN-путь с обратными слешами уходил в ветку локальных файлов, Две независимые причины, Проверка, Решение, Симптом, Урок про инструменты

### Community 149 - "Каждая транзакция глушит модальные диалоги Revit.md"
Cohesion: 0.03
Nodes (57): create_view section — direction cross up давал левосторонний базис и пустое исключение, Диагностика, Исправление, Причина, Связанное, Симптом, Урок, suppress_warnings глушит собственный сбой и оставляет транзакцию без защиты (+49 more)

### Community 150 - "Открытые вопросы по проекту"
Cohesion: 0.25
Nodes (8): Безопасность пилота (новое, 2026-09-07), Как пользоваться этой заметкой, Незаписанные вещи из практики, Открытые вопросы по проекту, Пробелы в знании об окружении, Продукт и стратегия, Связанное, Технические решения, требующие выбора

### Community 151 - "test_inactive_document_reads.py"
Cohesion: 0.13
Nodes (15): entry(), invoke(), parametrize, Offline two-document routing: run every real read entry point, never Revit., Compile the production entry point; stub only its existing data provider.…, Response, test_closed_b_token_is_not_replaced_by_a_or_reopened_same_path(), test_each_read_selects_inactive_b_or_explicitly_refuses_ui_state() (+7 more)

### Community 152 - "install_audited_tools"
Cohesion: 0.20
Nodes (14): install_audited_tools(), Wrap every tool registered on this FastMCP from now on; a second call is a no-…, anyio_backend(), anyio, fixture, D-12: the injected user_request parameter on every published tool schema, and…, _recording_server(), _register_all() (+6 more)

### Community 153 - "audit.py"
Cohesion: 0.06
Nodes (57): build_entry(), _changed_entry(), _clip(), _cut(), document_of(), is_mutation(), _outcome(), _outcome_block_missing() (+49 more)

### Community 154 - "status.py"
Cohesion: 0.10
Nodes (28): get_process_identity(), Read the initialized token and actual bound primary RoutesServer port. No…, extension_build(), extension_root(), python_info(), The extension directory for a module file inside revit_mcp/; never raises., Product version and runtime facts for the /status/ route. PRODUCT_VERSION is…, {"implementation", "version"} of the interpreter running this code; never… (+20 more)

### Community 155 - "sanitize_string превращает кириллицу в вопросительные знаки.md"
Cohesion: 0.06
Nodes (30): LLM.txt устарел и описывает структуру на 31 инструмент, Предлагаемое действие, Связанное, Смежная устаревшая метадата, Что в нём неверно, Что в нём ценно и стоит сохранить, Практика работы с форком, Регрессия, приехавшая из этой же линии (+22 more)

### Community 156 - "Порт 48884 захардкожен, настраивается только хост"
Cohesion: 0.25
Nodes (8): Обоснование, Обратная сторона: `REVIT_HOST` — это риск, Полный список захардкоженного, Порт 48884 захардкожен, настраивается только хост, Путь исправления, Решение, Связанное, Что это блокирует

### Community 157 - "test_audit_writer.py"
Cohesion: 0.07
Nodes (53): audit_dir(), flush(), prune(), Wait until every queued entry reached the file; False when the deadline passed…, The local per-user directory for audit files (D-14)., Delete old, then surplus audit files; return the names this call deleted (D-16,…, anyio_backend(), _block() (+45 more)

### Community 158 - "test_trust_dialect.py"
Cohesion: 0.05
Nodes (60): bytes, _build_extension_tree(), _bytes_constant(), _BytesSubclass, _digest(), _find_unsupported(), _imported_modules(), _imports() (+52 more)

### Community 159 - "test_policy_reload.py"
Cohesion: 0.08
Nodes (39): anyio_backend(), broken_base(), build_server(), call(), Clock, _fresh_store(), machine(), make_store() (+31 more)

### Community 160 - "Валидация продукта — сборка Empire State Building в живом Revit 2027.md"
Cohesion: 0.03
Nodes (63): Валидация продукта — сборка Empire State Building в живом Revit 2027, Метод, который стоит повторять, Ограничение метода, Почему это лучшая проверка, чем тесты, Связанное, Что было сделано, Что она же выявила как отсутствующее, create_surface по умолчанию попадал на Foundation Slab вместо перекрытия (+55 more)

### Community 161 - "acc_result"
Cohesion: 0.06
Nodes (38): acc_result(), _copies_of(), _drop(), _drop_copies(), mutate(), _good_acc_json(), good_acc_record(), has_code() (+30 more)

### Community 162 - "unit/test_phase6_live_audit.py"
Cohesion: 0.05
Nodes (11): _args_for(), Unit twin of tests/test_phase6_live_audit.py: the pure classifiers and refusals…, _refusal_cases(), test_a_refused_check_touches_no_file(), test_a_valid_set_of_arguments_is_not_refused(), test_an_empty_existing_audit_directory_is_allowed(), test_refusal_names_the_unsafe_input(), test_script_defines_no_pytest_collectable_name_and_does_nothing_at_import() (+3 more)

### Community 163 - "format_response"
Cohesion: 0.06
Nodes (52): Commit c1231f6: format_response mislabeling fix, Dict-is-error-only-if-truthy-error-key rule, Tool functions always return str via format_response, _partial(), parametrize, New /status/ fields must not vanish -- degraded state has to be visible., _revit_call collapses every non-200 and every exception to a string., Guards the fork's ASCII-mangling regression at the presentation layer. (+44 more)

### Community 164 - "preflight.py"
Cohesion: 0.06
Nodes (61): ElementId cross-version helper invariant, Multi-Version Revit Support (2024-2027), Revit 2027 .NET 10 compatibility note, _db(), find_family_by_name(), parameter_has_value(), Resolve the active pyRevit DB namespace when a helper needs API types., Shared Revit lookup helpers for mutation routes and mutation preflight (D-09).… (+53 more)

### Community 165 - "unit/test_phase4_live_outcomes.py"
Cohesion: 0.06
Nodes (55): _drop(), ExplodingBridge, FakeBridge, install(), load_record(), ok_record(), _outcome(), paths() (+47 more)

### Community 166 - "Сессия: откат транзакции больше не выдаётся за успех"
Cohesion: 0.25
Nodes (8): Изменённые файлы, Коммит, Проверки, Сессия: откат транзакции больше не выдаётся за успех, Суть работы, Чего ждёт администратор MCP, Что не готово, Что я открыл

### Community 167 - "test_export_cannot_return_another_documents_png"
Cohesion: 0.13
Nodes (6): Options, list, parametrize, Run the real export provider with file-backed fakes; no Revit or network., test_export_cannot_return_another_documents_png(), ViewIds

### Community 168 - "revit_post"
Cohesion: 0.09
Nodes (55): anonymous_call(), current_call(), The tool call this task runs inside, or None outside any tool call., The identity of a bridge call made outside any tool call: its own id, no tool., GET one Revit route, on the selected incarnation or the only usable one., POST to one Revit route, on the selected incarnation or the only usable one.…, GET request that returns an Image object. Runs through the same bounded-wait,…, revit_get() (+47 more)

### Community 169 - "Architecture Patterns"
Cohesion: 0.29
Nodes (7): Anti-Patterns to Avoid, Architecture Patterns, Pattern 1: bounded wait, unbounded-by-the-wait send (prototyped, 16/16 passing), Pattern 2: read-only allowlist as a fail-safe set with a drift test, Pattern 3: `host:port` for `get_revit_status` without importing the transport (D-06), Recommended Project Structure, System Architecture Diagram

### Community 170 - "unit/test_phase2_live_identity.py"
Cohesion: 0.03
Nodes (56): _after_close_lists_the_stale_token(), _case_reply(), codes(), _collision(), _collision_add_usable(), _collision_inventory(), mutate(), _doc_list() (+48 more)

### Community 171 - "Базы данных нет — состояние живёт в открытом документе Revit"
Cohesion: 0.29
Nodes (7): Базы данных нет — состояние живёт в открытом документе Revit, Где вообще живёт состояние, Кэширование, Персистентность, Связанное, Файловая система, Что это ограничивает

### Community 172 - "approval.py"
Cohesion: 0.06
Nodes (58): ask_human(), AuthorizationRequest, authorize(), build_message(), _fact(), _fact_lines(), facts_digest(), _fop() (+50 more)

### Community 173 - "test_policy_loader.py"
Cohesion: 0.08
Nodes (23): PolicyError, The policy file is unreadable or invalid; the text names the key path, never a…, a_check_route(), a_get_route(), base_doc(), _check_magic(), _get_confirm(), operator_doc() (+15 more)

### Community 174 - "gate_or_response"
Cohesion: 0.05
Nodes (91): gate_or_response(), initialize(), The pyRevit routes response for a refusal. pyRevit is imported only here., None when the call may proceed, otherwise the routes response that refuses it.…, Compute the load-time state from the extension's own files; returns None.…, _refusal(), clean_body(), gate_failure() (+83 more)

### Community 175 - "sys.stdout может остаться закрытым StringIO до конца сессии Revit"
Cohesion: 0.25
Nodes (8): sys.stdout может остаться закрытым StringIO до конца сессии Revit, Исправление, Обходной путь, Причина, Связанное, Симптом, Триггер, Урок

### Community 176 - "tests/test_phase4_live_outcomes.py"
Cohesion: 0.07
Nodes (57): _bridge(), _build_parser(), classify_outcomes(), _cmd_classify(), _committed_success(), _describe(), _describe_reply(), _dict() (+49 more)

### Community 177 - "test_routes_analysis_color_identity.py"
Cohesion: 0.08
Nodes (37): classify_outcome(), Return (status, http_status) for one finished transaction (D-04). The one place…, colour_call(), detail_call(), is_failure(), levels_answer(), No HOST_APP: the fake pyRevit raises if it is read, and that would be a 503., Wave 0 gap: a route that compares Commit() with DB.TransactionStatus needs both… (+29 more)

### Community 178 - "open_model"
Cohesion: 0.07
Nodes (40): make_existing_local(), open_model(), pin_clock(), A document key is not a selector here: nothing is resolved, nothing is refused., The workset configuration and detach option are applied BEFORE the open call,…, A fake workshared central: workset names, CreateNewLocal that writes b"new",…, test_open_model_backup_folder_rename_failure_restores_the_file(), test_open_model_defaults_to_a_new_local_copy_of_a_workshared_central() (+32 more)

### Community 179 - "test_routes_mep_parameter_identity.py"
Cohesion: 0.11
Nodes (35): assert_refused(), is_failure(), _mismatch_naming(), parametrize, Explicit per-handler document guard on the mutating routes of mep, parameters,…, The route a handler was registered under: pyRevit's request.path is that API-…, pyRevit runs a handler in the Revit API context only if it declares uiapp,…, Neither HOST_APP nor revit.doc: the document is the guard's, the process is the… (+27 more)

### Community 180 - "scan_envelope_tolerance.py"
Cohesion: 0.09
Nodes (33): _binds_parsed_body(), _call_name(), _decode(), _Flow, _in_truth_context(), _is_body_parse(), _is_parser_call(), _is_request_data() (+25 more)

### Community 181 - "test_trust_secret.py"
Cohesion: 0.05
Nodes (49): auth_failure(), gate_applies(), Equality of two byte sequences by XOR-accumulation, visiting every position.…, True only when two secrets are equal, compared in constant time; never raises.…, (body, status) of the HTTP 401 refusal for a failed verdict. A reason outside…, The secret text held by the bytes of a secret file, or None; never raises.…, The secret held by the file at ``path``, or None; never raises, never logs. The…, False for GET and HEAD (any case), True for every other or unknown method.… (+41 more)

### Community 182 - "test_revit_lookup.py"
Cohesion: 0.08
Nodes (25): Collector, collector_for(), Definition, Document, Element, ElementId, Group, lookup() (+17 more)

### Community 183 - "test_phase7_preflight_route.py"
Cohesion: 0.05
Nodes (57): Collector, definition(), Document, Element, ElementType, facts(), collect(), Family (+49 more)

### Community 184 - "test_audit_secret.py"
Cohesion: 0.11
Nodes (36): anyio_backend(), assert_no_secret(), audit_bytes(), build_server(), secret_get_probe(), secret_post_probe(), call(), call_registered() (+28 more)

### Community 185 - "_BenchProblem"
Cohesion: 0.13
Nodes (23): _BenchProblem, build_activation_entry(), build_g3_slot(), build_g4_case(), build_listing_entry(), capture(), capture(), capture() (+15 more)

### Community 186 - "audit_support.py"
Cohesion: 0.10
Nodes (12): Gate, Machine, object, Requested (non-status) routes, as (port, method, path)., (writer stem, segment number): "<stem>.jsonl" is segment 1, "<stem>.0002.jsonl"…, Shared Phase 6 test helpers: fake machine through the real bridge and the…, Stable unknown facts for tests concerned with consent rather than model facts., Listeners, identities, routes and canned replies of a fake machine. (+4 more)

### Community 187 - "test_audit_tracer.py"
Cohesion: 0.20
Nodes (17): anyio_backend(), audit_id_of(), build_server(), audit_read_probe(), audit_tracer_probe(), call(), machine(), anyio (+9 more)

### Community 188 - "unit/test_phase7_live_bench.py"
Cohesion: 0.12
Nodes (14): _audit(), _passing_record(), Offline regression tests for the operator-only Phase 7 bench., test_audit_wrong_tool_or_route_stops(), test_complete_synthetic_record_classifies_ok(), test_duplicate_audit_and_wrong_post_count_stop(), test_fractional_transform_must_show_12_5_mm(), test_identity_must_match_listener_production_contract() (+6 more)

### Community 189 - "mep_call"
Cohesion: 0.09
Nodes (29): create_answers(), make_room(), mep_call(), override_create(), DB.Mechanical.Duct.Create / DB.Plumbing.Pipe.Create answer ``created``., An element with one connector that belongs to no system yet., The element already belongs to system 901, whose name parameter is…, A parameter a secondary step writes: read-only or raising on demand (D-12). (+21 more)

### Community 190 - "read_entries"
Cohesion: 0.17
Nodes (33): Flush the writer, then return every audit entry in the directory, oldest file…, read_entries(), anyio_backend(), block(), machine(), post(), anyio, fixture (+25 more)

### Community 191 - "test_secret_gate_e2e.py"
Cohesion: 0.18
Nodes (18): anyio_backend(), _ironpython3_json(), _IronPython3Json, _post(), anyio, fixture, object, Tracer: the shared-secret gate end to end, across both halves. The real,… (+10 more)

### Community 192 - "tests/test_phase6_live_audit.py"
Cohesion: 0.15
Nodes (27): _child_record_path(), _cmd_classify(), evidence_template(), _ex_text(), _finish(), _flush(), _load_record(), _now() (+19 more)

### Community 193 - "48 MCP-инструментов зеркалят 48 маршрутов pyRevit"
Cohesion: 0.20
Nodes (10): 48 MCP-инструментов зеркалят 48 маршрутов pyRevit, Анализ (5), Документация (3), Изменение (9), Обмен и персистентность (4), Продвинутое (1), Распределение по модулям, Связанное (+2 more)

### Community 194 - "CallState"
Cohesion: 0.15
Nodes (13): CallState, audited_tool(), decorator(), _json_text(), new_call(), Any, What one tool call is: its id, name, arguments and the reported user request., A fresh call state; the MCP context object is dropped (checked by name, no mcp… (+5 more)

### Community 195 - "make_db"
Cohesion: 0.14
Nodes (5): make_db(), __getattr__(), _items(), __iter__(), XYZ

### Community 196 - "execute_code даёт неаутентифицированное исполнение кода внутри Revit"
Cohesion: 0.12
Nodes (16): execute_code даёт неаутентифицированное исполнение кода внутри Revit, Ещё одна проблема того же файла, Почему он вообще существует, Рекомендации, Связанное, Смежная проблема — traceback наружу, Что защищает, Что именно происходит (+8 more)

### Community 197 - "test_scan_envelope_tolerance.py"
Cohesion: 0.09
Nodes (24): handler(), fixture, needs_git, parametrize, D-06 static check: an extension tree tolerates the _mcp envelope. Needs no…, A route handler that parses its body into `data`, then runs `body`., raw_source(), scanner() (+16 more)

### Community 198 - "read_options"
Cohesion: 0.07
Nodes (36): Register analysis tools with the MCP server., Analysis tools — element filtering, rooms, materials, and statistics, Transport keyword for the per-call process selector; absent when not given., register_analysis_tools(), ai_element_filter(), analyze_model_statistics(), export_room_data(), get_material_quantities() (+28 more)

### Community 199 - "Pattern Assignments"
Cohesion: 0.08
Nodes (24): `audit.py` (NEW; service/utility, event-driven), `bridge.py` hook seams (service, request-response), `deploy/build-payload.cmd` (config, batch), File Classification, Lazy imports and cold start, `main.py` (config, request-response), Metadata, Never break a tool call, never write stdout (+16 more)

### Community 200 - "good_evidence"
Cohesion: 0.33
Nodes (7): good_evidence(), test_cli_classify_complete_evidence_is_eligible_but_not_approved(), test_cli_classify_stopping_evidence_is_exit_1_with_reasons(), test_overall_is_eligible_only_when_all_five_gates_continue_and_never_approved(), test_overall_one_missing_gate_is_stop(), test_overall_one_stopping_gate_stops_the_whole_preflight(), _write()

### Community 201 - "Validation Architecture"
Cohesion: 0.33
Nodes (6): Live bench (criterion 5, D-16, D-17, D-23) — procedure, to be written into the plan as a `checkpoint:human-verify`, Phase Requirements → Test Map, Sampling Rate, Test Framework, Validation Architecture, Wave 0 Gaps

### Community 202 - "Feasibility and Prescriptive Design"
Cohesion: 0.33
Nodes (6): 1. Process selector: incarnation-qualified opaque string, 2. Refactor bridge ownership before touching tools, 3. Document identity — живой реестр, не `Title` и не кэш, 4. Safe reads — только узкие новые маршруты, 5. Mutation guard и прокат контракта инструментов, Feasibility and Prescriptive Design

### Community 203 - "test_permit_protocol.py"
Cohesion: 0.14
Nodes (41): check(), _fresh_registry(), mint(), fixture, parametrize, Phase 7 (07-05): the one-time permit protocol, proven on both runtimes. The…, (argument text, permit dict) for one fresh permit., The exact request bytes the bridge would send. (+33 more)

### Community 204 - "_is_int"
Cohesion: 0.18
Nodes (25): _audit_entries(), audit_id_of(), _by_call_id(), _describe(), _dict(), _expect(), _file_label(), _file_pid() (+17 more)

### Community 205 - "Null document при переключении моделей"
Cohesion: 0.33
Nodes (5): Null document при переключении моделей, Причина, Проверка, Решение, Симптом

### Community 206 - "current_document_descriptors"
Cohesion: 0.05
Nodes (80): current_document_descriptors(), decide_mutation_document(), DocumentRegistry, get_document_registry(), _new_generation(), Opaque tokens bound to document lifetimes for one process incarnation., What a selector is, without looking at Revit: invalid, stale, closed, live or…, The one registry of this process incarnation, kept in an owned slot. A slot… (+72 more)

### Community 207 - "test_tool_forwarding_model.py"
Cohesion: 0.07
Nodes (43): FakeMCP, module_source(), object, parametrize, Register one module on a recording fake transport; returns (tools, calls)., Plan 02-10: per-call process (target) and mutation-document (document)…, A blank selector must never decay into the one-document default., The bridge hands a non-200 reply over as an 'Error: 409 - ...' string (D-07).… (+35 more)

### Community 208 - "test_trust_integrity.py"
Cohesion: 0.10
Nodes (58): evaluate_integrity(), integrity_failure(), _manifest_files(), mismatch_files(), True only for a relative, '/'-separated path that stays inside the extension.…, True for text of exactly 64 lowercase hexadecimal characters., The files map of a well-formed manifest, or None when anything is off., The three-state verdict for a parsed manifest and what was observed; never… (+50 more)

### Community 209 - "Plan 05-12 Summary"
Cohesion: 0.40
Nodes (4): Completed, Plan 05-12 Summary, Safety boundary, Verification

### Community 210 - "_now"
Cohesion: 0.16
Nodes (43): _acc_enter(), _acc_options(), _acc_pending(), _acc_run(), _acc_save(), _acc_stop(), _acc_usage(), _cmd_collision_after() (+35 more)

### Community 211 - "test_phase5_gate_e2e.py"
Cohesion: 0.11
Nodes (22): Forget the memoized secret so the next POST reads the file again., reset_secret_cache(), anyio_backend(), _handler(), _harness(), _install(), _IronPython3Json, _posts() (+14 more)

### Community 212 - "test_routes_view_code_identity.py"
Cohesion: 0.08
Nodes (41): assert_exception_labelled(), execute_tool(), _gate_body(), is_failure(), _mismatch_naming(), With a valid envelope the gate passes, so the route's own parse failure is…, Document guard on the transform and view mutations, process-scoped open_model,…, The route a handler was registered under: pyRevit's request.path is that API-… (+33 more)

### Community 213 - "Выпуск релиза: сборка, пилот, раскатка"
Cohesion: 0.08
Nodes (24): 0. Что должно быть готово до начала, 10. Фиксация после выпуска [Вы], 1.1. Тег-кандидат и push [Вы], 1.2. Пилотный share [Вы], 1. Подготовка, 2. Сборка в пилотный share [Вы, на сборочном сервере], 3.1. Кого брать, 3.2. Снять старый путь, если машина уже была установлена [Вы] (+16 more)

### Community 214 - "test_probe_ipy_trust.py"
Cohesion: 0.10
Nodes (32): _good_fields(), _ok_exec(), parametrize, Offline tests of the live D-04 probe (scripts/probe_ipy_trust.py). The probe…, _run_main(), _run_snippet(), _status(), _status_fields() (+24 more)

### Community 215 - "StepGrid"
Cohesion: 0.29
Nodes (9): grid_answers(), setter, A grid whose Name setter can be made to raise, like a duplicate grid name., StepGrid, structure_call(), test_create_grid_rolled_back_is_a_409_with_nothing_succeeded(), test_create_grid_whose_name_cannot_be_set_is_a_partial_but_keeps_the_created_grid(), test_create_grid_with_one_valid_and_one_zero_length_grid_is_a_partial_naming_the_index() (+1 more)

### Community 216 - "FakeDB"
Cohesion: 0.10
Nodes (43): FakeDB, FakeRequest, levels_handlers(), only_from(), What pyRevit hands a handler: the body in ``data`` and the route it addressed…, The DB namespace: records the Document every collector is built on., OTHER (3 elements, 1 level) is active; COORD (10 elements, 2 levels) is open,…, read_handlers() (+35 more)

### Community 217 - "LocalStore"
Cohesion: 0.08
Nodes (16): _AppDomainStore, _bind(), _default_store(), _is_linked(), LocalStore, Observation, object, A process-local key/value slot, used where there is no AppDomain (CPython… (+8 more)

### Community 218 - "handler_of"
Cohesion: 0.10
Nodes (57): arm(), armed_items(), assert_refused(), call(), handler_of(), _named(), only_document(), parametrize (+49 more)

### Community 219 - "Сессия: сравнение с апстримом revit-mcp-python и подтверждение родословной форка"
Cohesion: 0.25
Nodes (8): Внешние метрики апстрима (сняты 2026-09-04, через `api.github.com`), Вывод, отданный пользователю, Задача, Метод, Находка: это не конкурент, а предок этого же кода, Не сделано, Связанное, Сессия: сравнение с апстримом revit-mcp-python и подтверждение родословной форка

### Community 220 - "test_tool_forwarding_views.py"
Cohesion: 0.07
Nodes (51): FakeMCP, module_source(), normalized(), object, parametrize, Register one module on a recording fake transport; returns (tools, calls)., Plan 02-11: per-call process (target) and mutation-document (document)…, A blank selector must never decay into the one-document default. (+43 more)

### Community 221 - "line_of"
Cohesion: 0.13
Nodes (24): _aligned_hybrid_line(), _dual_other_revit(), dual_parts(), _dual_secret(), entry(), file_name(), start(), line_of() (+16 more)

### Community 222 - "_reset"
Cohesion: 0.31
Nodes (8): Forget the writer, the warn-once flag and the cached Windows user. For tests…, DOMAIN\\user of this process (D-10), computed once; never raises. USERDOMAIN…, _reset(), windows_user(), test_windows_user_falls_back_to_getpass(), test_windows_user_is_computed_once_per_process(), test_windows_user_is_domain_backslash_user(), test_windows_user_is_unknown_when_nothing_answers()

### Community 223 - "Plan 05-15 Summary: live cleanup stage and phase verdict (PHASE5_GATE_OK, PASS)"
Cohesion: 0.09
Nodes (22): 05-VALIDATION.md, Classify, `classify --stage cleanup C:/Temp/phase5/S3-cleanup.json` (exit 0), classify-phase, `classify-phase C:/Temp/phase5/S1-match-3.json C:/Temp/phase5/S2-corrupt.json C:/Temp/phase5/S3-cleanup.json` (exit 0), Console output (verbatim), Developer junction state, Deviations from Plan, `git status --porcelain -- revit_mcp startup.py extension.json _manifest.json` after the run, Known Stubs (+14 more)

### Community 224 - "test_trust_listeners.py"
Cohesion: 0.12
Nodes (15): _as_port(), classify_listeners(), _is_loopback_host(), _is_loopback_ipv4(), An int port for an int (never a bool) or digit-only text, else None., True only for a dotted quad of four plain decimal parts (0-255) starting with…, True only for a literal loopback address; text that is not one is False.…, BIND_LOOPBACK_ONLY, BIND_EXPOSED or BIND_UNKNOWN for the listeners on ``port``;… (+7 more)

### Community 225 - "test_integrity_reader.py"
Cohesion: 0.09
Nodes (48): _break_manifest(), _build_tree(), _check(), _copy_layout(), _manifest_for(), _network_enoent(), _normalized(), parametrize (+40 more)

### Community 226 - "test_tool_forwarding_documents.py"
Cohesion: 0.08
Nodes (37): FakeMCP, module_source(), object, parametrize, Register one module on a recording fake transport; returns (tools, calls)., Plan 02-09: per-call process (target) and mutation-document (document)…, A blank selector must never decay into the one-document default., The inventory and the source agree: one forwarding site per mutation, none for… (+29 more)

### Community 227 - "test_make_manifest.py"
Cohesion: 0.07
Nodes (47): _git(), _ignored_repo(), _init_repo(), make_manifest(), _no_walkers(), fixture, needs_git, Hardening of deploy/make_manifest.py: the file list comes only from git ls-… (+39 more)

### Community 228 - "_execute_dual"
Cohesion: 0.11
Nodes (23): _bridge(), _child_argv(), _execute_dual(), _execute_rehearse(), _execute_single(), _issue_calls(), _main_module(), _merge_child() (+15 more)

### Community 229 - "test_policy_fop.py"
Cohesion: 0.14
Nodes (14): anyio_backend(), clear_cache(), anyio, fixture, parametrize, Company FOP parsing and matching; fixtures are local, never the corporate share., test_cache_avoids_reread_and_invalidates_on_size_change(), reader() (+6 more)

### Community 230 - "test_routes_document_interop_identity.py"
Cohesion: 0.07
Nodes (61): arm(), arm_placement(), arm_schedule(), arm_sheet(), db_of(), events_after_commit(), handler_of(), A title block in the collector and a ViewSheet.Create that hands back a tracked… (+53 more)

### Community 231 - "rig"
Cohesion: 0.07
Nodes (50): Activate the document named by ``selector`` if, and only if, it is eligible.…, run_activation(), activate(), activate_handlers(), activate_request(), exists_everywhere(), failing_read_after(), _mismatch_naming() (+42 more)

### Community 232 - "ok_single"
Cohesion: 0.13
Nodes (21): ok_dual(), ok_single(), reasons_text(), _replace_each_node(), test_a_classifier_internal_error_reads_as_stop(), test_a_step_that_was_not_recorded_is_a_stop(), test_classifiers_never_raise_when_any_single_node_is_replaced(), test_classify_command_judges_a_dual_record_by_its_stage() (+13 more)

### Community 233 - "RouteDocument"
Cohesion: 0.09
Nodes (9): InjectedDocument, _Lifetime, Anything whose use the event log records under its label., A wrapper over one open lifetime. Anything the guard does not read is recorded…, The ``doc`` pyRevit injects. A handler that ignores the guard and uses it shows…, RouteApplication, RouteDocument, RouteUIApp (+1 more)

### Community 234 - "tests/test_phase2_live_identity.py"
Cohesion: 0.05
Nodes (70): _acc_blank_result(), acc_report(), _acc_result(), acc_summary_lines(), acceptance_template(), _answering_identity(), build_mutation_entry(), build_read_entry() (+62 more)

### Community 235 - "webbridge MCP падает CONNECTION_CLOSED из-за занятого порта 10086"
Cohesion: 0.29
Nodes (7): webbridge MCP падает CONNECTION_CLOSED из-за занятого порта 10086, Диагностика, Настоящее исправление, Обходной путь, Причина, Связанное, Симптом

### Community 236 - "inventory_support.py"
Cohesion: 0.08
Nodes (27): FakeMCP, _literal_path(), manifest_names(), object, Shared discovery and classification for the Phase 2 exhaustive inventory…, The literal prefix of the first argument of a transport call., {tool name: [(transport, route key)]} read from every tools/*_tools.py source., One @api.route handler found in revit_mcp/<module>.py. (+19 more)

### Community 237 - "split_envelope"
Cohesion: 0.10
Nodes (31): _blank(), check_secret(), _configured(), envelope_secret(), Return (envelope, payload) for one request body; never raises, never mutates.…, The secret carried by an envelope, or None when there is none., True for None and for text or bytes that are empty once stripped., True only for text or bytes of at least MIN_SECRET_LENGTH once stripped. (+23 more)

### Community 238 - "single_argv"
Cohesion: 0.12
Nodes (20): docs_reply(), one_revit(), posts_of(), props_reply(), fixture, One fake Revit (port A) with one document, a writable wall parameter and canned…, Two fake Revit instances (ports A and B), one document each, the parameter…, rehearse_argv() (+12 more)

### Community 239 - "object"
Cohesion: 0.07
Nodes (17): _a_second_activation(), _AccGet, _AccPost, AccSession, _append_call(), mutate(), FakeSession, _good_g34_json() (+9 more)

### Community 240 - "structure_tools.py"
Cohesion: 0.29
Nodes (9): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, Structure tools — grids and structural framing, Register structure tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_structure_tools(), create_grid(), create_structural_framing() (+1 more)

### Community 241 - "forget_retired_path.py"
Cohesion: 0.50
Nodes (4): main(), r"""Unregister a retired pyRevit extension search path. Usage:…, Every registered search path whose text contains marker., retired_paths()

### Community 242 - "01-01-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Flagged assumptions (edge probe — unresolved, never silently dropped), STRIDE Threat Register, Trust Boundaries

### Community 243 - "01-02-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Flagged assumptions (edge probe — unresolved, never silently dropped), STRIDE Threat Register, Trust Boundaries

### Community 244 - "01-03-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Flagged assumptions (edge probe), STRIDE Threat Register, Trust Boundaries

### Community 245 - "01-04-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Flagged assumptions (edge probe), STRIDE Threat Register, Trust Boundaries

### Community 246 - "01-05-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Flagged assumptions (edge probe — unresolved, never silently dropped), STRIDE Threat Register, Trust Boundaries

### Community 247 - "01-06-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Flagged assumptions (edge probe and evidence gaps; never silently dropped), STRIDE Threat Register, Trust Boundaries

### Community 248 - "01-07-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Flagged assumptions (edge probe and evidence gaps; never silently dropped), STRIDE Threat Register, Trust Boundaries

### Community 249 - "01-08-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Flagged assumptions (edge probe and evidence gaps; never silently dropped), STRIDE Threat Register, Trust Boundaries

### Community 250 - "Code Examples"
Cohesion: 0.40
Nodes (5): Code Examples, Контракт резолва документа, Обязательства докстринга мутирующего инструмента, Последовательность валидации target (CPython), Существующий паттерн видимой identity

### Community 251 - "Validation Architecture"
Cohesion: 0.40
Nodes (5): Phase Requirements → Test Map, Sampling Rate, Test Framework, Validation Architecture, Wave 0 Gaps

### Community 252 - "Sources"
Cohesion: 0.40
Nodes (5): Primary (HIGH confidence), Repository evidence (HIGH for the quoted file facts — каждый файл прочитан в этой сессии), Secondary (MEDIUM confidence), Sources, Tertiary (LOW confidence)

### Community 253 - "Phase 2 Plan 02: Production identity recheck Summary"
Cohesion: 0.12
Nodes (15): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Issues Encountered, Known Stubs, Live evidence (Task 2, engineer-controlled, human choice: observed, 2026-10-22), Next Phase Readiness (+7 more)

### Community 254 - "read"
Cohesion: 0.15
Nodes (19): read(), write(), One stdio MCP server process whose legacy target is the given Routes port., _server(), check_mode(), count_tools_sse(), count_tools_streamable_http(), free_port() (+11 more)

### Community 255 - "call"
Cohesion: 0.13
Nodes (41): arm(), call(), handler_of(), _named(), parameter_world(), doc.ActiveView must be read from the guard's document, never the injected one., The phase tracer: route handler -> outcome helpers -> reply -> format_response., D-14: a call that raised after Commit() really did change the model. (+33 more)

### Community 256 - "retention_settings"
Cohesion: 0.25
Nodes (8): _positive_int_env(), The environment variable as a whole number above zero, else ``default``. Never…, (max_age_seconds, max_total_bytes) from the environment; MB means MiB (1024 *…, retention_settings(), parametrize, test_settings_come_from_the_environment_in_seconds_and_mebibytes(), test_settings_default_when_unset(), test_settings_fall_back_on_a_bad_value_without_raising()

### Community 257 - "Phase 2 Plan 03: Process discovery, unambiguous default and per-incarnation serialization Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Performance, Phase 2 Plan 03: Process discovery, unambiguous default and per-incarnation serialization Summary (+4 more)

### Community 258 - "good_record"
Cohesion: 0.11
Nodes (24): acc_attach(), good_record(), listener(), reply(), test_active_replies_with_separate_no_document_reply_are_observed(), test_attach_embeds_a_prior_record_and_refuses_the_wrong_schema_or_a_second_attach(), test_classifier_internal_error_reads_as_stop(), boom() (+16 more)

### Community 259 - "test_payload_ships_root_modules.py"
Cohesion: 0.27
Nodes (9): _copied_from_repo_root(), Every repo-root module reachable from main.py must be copied into the payload.…, Top-level names of the repo-root modules one file imports (absolute imports…, Repo-root modules main.py imports, and those they import in turn (each file…, The base policy is data the payload reads beside policy.py; the .py-only walk…, _root_imports_of(), _root_modules_reached_from_main(), test_payload_copies_every_root_module_reachable_from_main() (+1 more)

### Community 260 - "Standard Stack"
Cohesion: 0.50
Nodes (4): Alternatives Considered, Core, Standard Stack, Supporting

### Community 261 - "Sources"
Cohesion: 0.50
Nodes (4): Primary (HIGH confidence), Secondary (MEDIUM confidence), Sources, Tertiary (LOW confidence)

### Community 262 - "Standard Stack"
Cohesion: 0.50
Nodes (4): Alternatives Considered, Core, Standard Stack, Supporting

### Community 263 - "2026-09-14-open-models-and-null-document-fix.md"
Cohesion: 0.50
Nodes (3): Информация о сессии, Проверка кода, Результат

### Community 264 - "Pattern Assignments"
Cohesion: 0.08
Nodes (24): 34 gated handlers (route handler, request-response), `bridge.py` (transport, request-response), `deploy/make_manifest.py` (opt-in repo dest), `deploy/publish-extension.cmd` (staged swap) and `deploy/rollback-extension.cmd`, Explicit list + guard test (closed by default), File Classification, Gate-first, never-raise handler contract, Initialization-failure isolation (+16 more)

### Community 265 - "Security Domain"
Cohesion: 0.67
Nodes (3): Applicable ASVS Categories, Known Threat Patterns for this stack, Security Domain

### Community 266 - "Code Examples"
Cohesion: 0.67
Nodes (3): Code Examples, Concurrency test skeleton (prototype, passes), Strict port parsing (prototyped; all cases below verified)

### Community 267 - "Security Domain"
Cohesion: 0.67
Nodes (3): Applicable ASVS Categories, Known Threat Patterns for this stack, Security Domain

### Community 270 - "good_retained_g2"
Cohesion: 0.25
Nodes (9): good_retained_g2(), _leaf_paths(), Offline fixture, not evidence of a live run or production token registry., test_g2_retained_branch_accepts_unique_semantic_binding_not_wrapper_identity(), test_g2_retained_branch_incomplete_or_contradictory_capture_stops(), test_g2_retained_branch_keeps_preamble_indices_and_token_design_fail_closed(), test_g2_retained_eligibility_does_not_approve_or_pass_other_gates(), test_retained_template_is_unset_and_covers_new_branch() (+1 more)

### Community 293 - "_cmd_g4_case"
Cohesion: 0.10
Nodes (43): _acc_load(), apply_authorization(), apply_observation(), _cmd_classify(), _cmd_first(), _cmd_g34_classify(), _cmd_g34_observe(), _cmd_g34_start() (+35 more)

### Community 294 - "Implementation Decisions"
Cohesion: 0.07
Nodes (27): Canonical References, Claude's Discretion, Confirmed User Constraints (2026-10-16), Deferred Ideas, Established Patterns, Existing Code Insights — перепроверить перед реализацией, Existing Decisions That Remain Binding, Implementation Decisions (+19 more)

### Community 295 - "Phase 7 — Session Research Inputs"
Cohesion: 0.22
Nodes (8): Acceptance Evidence To Produce Later, Alternatives and Why They Are Not a Required Stack, Architecture Outcome, Open Research / Decision Gates, Phase 7 — Session Research Inputs, Primary Public Sources Consulted, Read-only Observations: Unchanged Hermes Fork, Source Observations: This Repository

### Community 296 - "_Bound"
Cohesion: 0.07
Nodes (32): acc_sent_call_entry(), _Bound, _bridge(), checked_selector(), collect_listener_owners(), _collision_inventory(), describe_old_selector_retry(), _Free (+24 more)

### Community 297 - "exception_diagnostics"
Cohesion: 0.09
Nodes (27): _diag_inner_chain(), _diag_net_exception(), _diag_net_type_name(), _diag_read(), _diag_stack_trace(), _diag_text(), exception_diagnostics(), getattr that returns None instead of raising (a hostile wrapper may raise… (+19 more)

### Community 298 - "test_phase2_inventory.py"
Cohesion: 0.07
Nodes (37): Names called by a handler or by any same-module function it can reach by name., reachable_calls(), _body(), _params(), parametrize, Phase 2 exhaustive regression inventory (plan 02-17). Every registered tool and…, A document cannot be expressed on them: a TypeError before any dispatch., pyRevit runs a handler in the Revit API context only if it declares one of them… (+29 more)

### Community 299 - "Исследование Jev и серверной защиты, добавлена фаза 7"
Cohesion: 0.25
Nodes (8): Добавленная фаза, Запрос, Исследование Jev и серверной защиты, добавлена фаза 7, Проверки при сохранении, Результаты исследования, Решение пользователя, Следующий шаг, Ссылки

### Community 300 - "Plan 05-13 Summary: live match stage (verdict PHASE5_GATE_OK, PASS)"
Cohesion: 0.10
Nodes (19): Attempt 2: the two runner defects (fixed in `9aa9876`), Classify, `classify --stage match C:/Temp/phase5/S1-match-3.json` (exit 0), Console output of attempt 3 (verbatim), Deviations from Plan, History of the three attempts, Known Stubs, Listener and document checks (before attempt 3, run by the executor), Manifest regeneration (+11 more)

### Community 301 - "parametrize"
Cohesion: 0.09
Nodes (21): parametrize, Yield copies of `value` with each node replaced by `junk`, one at a time., test_classifier_never_raises_on_malformed_records(), test_collect_listener_owners_unknown_inventory_is_never_empty_or_single(), test_commands_refuse_an_input_path_inside_the_repository_before_any_live_call(), test_commands_without_a_capture_are_stop_not_a_live_call(), test_g34_classifiers_never_raise_on_malformed_records(), test_live_commands_refuse_an_input_path_inside_the_repository() (+13 more)

### Community 302 - "02-20 — measured preflight and human decision"
Cohesion: 0.29
Nodes (6): 02-20 — measured preflight and human decision, Completed checks, Decision, Evidence boundaries, Handoff, Selected mechanisms and local evidence

### Community 303 - "test_phase5_gate_wiring.py"
Cohesion: 0.15
Nodes (18): _body(), _calls_by_name(), _gate_statements(), _imports_security_module_by_other_means(), parametrize, Closed by default (Phase 5, D-01): every non-GET route opens with the shared-…, (assignment, if-return) of the gated preamble, asserting its exact shape., _security_imports() (+10 more)

### Community 304 - "FakeBench"
Cohesion: 0.11
Nodes (19): FakeBench, The Revit routes as plain data, behind the REAL document tools. Faults the…, Render an arbitrary route reply through the real tool., render(), render_payload(), test_parse_activation_text_activated_and_already_active(), test_parse_activation_text_refusal_carries_status_reason_and_observed_active(), test_parse_levels_text_counts_skipped_levels_and_reads_an_empty_list() (+11 more)

### Community 305 - "building_tools.py"
Cohesion: 0.29
Nodes (10): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, Building creation tools — walls, floors, roofs, ceilings, and levels, Register building creation tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_building_tools(), create_level(), create_line_based_element() (+2 more)

### Community 306 - "World"
Cohesion: 0.12
Nodes (10): FakeResponse, HostAppTrap, fixture, pyRevit's Response: a mutable status and data pair., One fake Revit process: documents, the injected uiapp/doc, and an event log., Selectors of the open documents, in enumeration order (issues them on first…, pyRevit's process-global HOST_APP. A handler must use the injected uiapp., A fake Revit process with the route modules imported against a fake pyRevit.… (+2 more)

### Community 307 - "Pattern Assignments"
Cohesion: 0.07
Nodes (26): `bridge.py` (additive: `load_secret`, `with_envelope`), `CLAUDE.md` (edit), `deploy/build-payload.cmd` (edit), `deploy/config.cmd` (edit), `deploy/gate.py` (edit), `deploy/publish-extension.cmd` (edit; file is `w/crlf`, preserve CRLF; user has uncommitted edits, use targeted Edit only), `deploy/secret_tool.py`, `deploy/make_manifest.py`, `scripts/dev_secret.py` (CPython build tools), Dirty tree discipline (+18 more)

### Community 308 - "mutate"
Cohesion: 0.10
Nodes (11): _args(), _document(), _drop_entry(), _dual_drop(), _dual_entry(), _duplicate_entry(), _entry(), mutate() (+3 more)

### Community 309 - "test_selected_elements_output.py"
Cohesion: 0.12
Nodes (21): ProvenanceDict, dict, A received reply body; provenance is an attribute, so equality and JSON are…, invoke(), tool(), parametrize, Selection payloads must survive the tool's summary projection., test_empty_selection_remains_success_with_explicit_count_and_list() (+13 more)

### Community 310 - "Common Pitfalls"
Cohesion: 0.11
Nodes (19): Common Pitfalls, Pitfall 10: `outcome.status` does not exist, Pitfall 11: `/activate_document/` is a mutation with no `outcome` block, Pitfall 12: A 500 with an `outcome` block is not "just an error", Pitfall 13: `audit.py` missing from the payload, Pitfall 14: Unit tests writing into the developer's real audit directory, Pitfall 15: `with_envelope(data, None)` adds no envelope, Pitfall 16: Token cost of the injected parameter (+11 more)

### Community 311 - "_reason"
Cohesion: 0.08
Nodes (32): _acc_evaluate(), _check_incarnation(), add(), _check_not_run(), _check_old_selector(), _check_routes(), _check_sent_calls(), classify_g3_production() (+24 more)

### Community 312 - "object"
Cohesion: 0.04
Nodes (26): _coloured(), ColourElement, FakeResponse, HostAppTrap, InjectedDocument, _Lifetime, Start(), fixture (+18 more)

### Community 313 - "Исполнение фазы 2 до плана 02-18, живая приёмка G3 и G4 нашла ошибку контекста API маршрутов"
Cohesion: 0.33
Nodes (6): Исполнение фазы 2 до плана 02-18, живая приёмка G3 и G4 нашла ошибку контекста API маршрутов, Команды для следующей сессии (S0–S2), Нерешённое и находки, Результаты, Решения, Что остаётся (02-18, задача 2)

### Community 314 - "document_tools.py"
Cohesion: 0.10
Nodes (27): _activation_exception_lines(), _active_token_text(), _blank_document(), _describe(), _diagnostic_line(), _failure_body(), _identity_line(), Readable lines for the exception diagnostics of an activation-failed reply, or… (+19 more)

### Community 315 - "IronPython Compatibility Notes"
Cohesion: 0.50
Nodes (4): find_family_symbol_safely(), get_element_name_safe(), get_family_name_safe(), IronPython Compatibility Notes

### Community 316 - "Phase 2 Plan 04: Live document registry, list_documents and the mutation decision contract Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Decision table (locked by tests), Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed (+6 more)

### Community 317 - "arm"
Cohesion: 0.16
Nodes (9): arm(), Created, DetailCurve, DimensionCreated, FakeView, setter, An element a fake Create call answers., A created detail curve whose LineStyle assignment can be made to fail. (+1 more)

### Community 318 - "_route"
Cohesion: 0.15
Nodes (23): _gate_hits(), A route module with one handler whose body is ``body``., _route(), test_a_call_before_the_preamble_is_a_violation(), test_a_flat_import_of_a_security_sibling_is_reported_by_the_dialect_check(), test_a_flat_or_absolute_import_of_security_is_a_violation(), test_a_gate_called_with_another_argument_is_a_violation(), test_a_gated_post_route_is_clean() (+15 more)

### Community 319 - "5. Приёмка пилота [Вы]"
Cohesion: 0.25
Nodes (8): 5.1. Один слушатель и состояние расширения, 5.2. Сервер и Гена, 5.3. Установка и обновления, 5.4. Дополнительно для R3: secret gate и staged publish, 5.5. Что записать в отчёт пилота, 5.6. Срок и критерий «можно выкатывать на всех» [Вы называете], 5.7. Если приёмка не пройдена, 5. Приёмка пилота [Вы]

### Community 320 - "check_integrity"
Cohesion: 0.08
Nodes (34): check_integrity(), _list_names(), observe_tree(), What is on disk: {"hashes", "present_py", "unreadable", "absent"} for the given…, The sorted subset of ``absent`` whose absence could not be confirmed. WR-01: on…, The integrity verdict for the extension tree at ``root``; never raises. Returns…, Read-only reader for the payload integrity manifest. deploy/make_manifest.py…, (status, data): ("ok", bytes), ("absent", None) for ENOENT, ("error", None)… (+26 more)

### Community 321 - "Холодный старт 0.9 с — это пол фреймворка, оптимизировать нечего"
Cohesion: 0.12
Nodes (16): Вывод, Из чего складывается, Измерение, Оговорка, Почему порог именно 2.0 с, Связанное, Холодный старт 0.9 с — это пол фреймворка, оптимизировать нечего, Что всё-таки сделано для старта (+8 more)

### Community 322 - "_write"
Cohesion: 0.09
Nodes (29): parametrize, Another build creates the file between the exists check and O_EXCL., _read(), test_dev_secret_creates_once_and_never_prints(), test_dev_secret_invalid_existing_fails_and_keeps_file(), test_ensure_creates_token_once(), test_ensure_keeps_valid_existing(), test_ensure_race_file_appears_first() (+21 more)

### Community 324 - "warm.py"
Cohesion: 0.50
Nodes (3): _pywin32_paths(), mcp>=1.11 imports pywin32 on Windows; the embeddable CPython ignores…, r"""Pre-import the heavy dependencies so the first real launch is not cold. Run…

### Community 325 - "Phase 2 Plan 05: Explicit activation of one already-open saved document Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed, Performance (+5 more)

### Community 326 - "test_phase5_status_diagnostics.py"
Cohesion: 0.09
Nodes (33): The first 8 hex characters of the SHA-256 of a configured secret, else None;…, Plain sentences about what is wrong in a /status/ security block; [] when…, secret_fingerprint(), security_alerts(), test_fingerprint_seam_returns_only_the_fingerprint(), _clean_modules(), _FakeMCP, _get_with() (+25 more)

### Community 327 - "call"
Cohesion: 0.10
Nodes (54): _assert_gate_refusal(), _assert_open(), assert_refused(), call(), dimensions_call(), handler_of(), _one_open_document(), override_create() (+46 more)

### Community 328 - "Phase 2 Plan 06: Addressed summary and levels reads Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed, Performance, Phase 2 Plan 06: Addressed summary and levels reads Summary (+4 more)

### Community 329 - "2026-10-26 — фаза 7, preflight и ФОП завершены, продолжить с 07-12"
Cohesion: 0.22
Nodes (9): 07-10 — read-only preflight, 07-11 — факты, ФОП и подтверждение, 2026-10-26 — фаза 7, preflight и ФОП завершены, продолжить с 07-12, Информация о сессии, Ограничения и следующий шаг, Окружение и диагностика, Результаты, Связанное (+1 more)

### Community 331 - "Phase 2 Plan 19: Process lifecycle under multi-target discovery Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Performance, Phase 2 Plan 19: Process lifecycle under multi-target discovery Summary, Self-Check: PASSED (+3 more)

### Community 332 - "Pattern Assignments"
Cohesion: 0.10
Nodes (20): Error-dict rule on the MCP side, Every transacting route module (the migration shape), File Classification, Four route-test worlds (`tests/unit/test_routes_*_identity.py`), Guarded handler wrapper, Metadata, No Analog Found, Outcome schema (D-03) and `item` meaning (+12 more)

### Community 333 - "Phase 5: Live secret gate and integrity enforcement - Context"
Cohesion: 0.11
Nodes (18): Canonical References, Claude's Discretion, Deferred Ideas, Established Patterns, Existing Code Insights, Implementation Decisions, Integration Points, Phase 5: Live secret gate and integrity enforcement - Context (+10 more)

### Community 334 - "listing_uiapp"
Cohesion: 0.17
Nodes (9): route(), register(), listing_uiapp(), load_documents_route(), route(), Import revit_mcp/documents.py against a fake pyrevit and capture its handler., An injected UIApplication double with nothing open (FakeUIApp is defined…, test_documents_route_answers_an_empty_list_with_identity_and_status_200() (+1 more)

### Community 335 - "describe_broken_path"
Cohesion: 0.11
Nodes (30): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, Interop tools — IFC export and external file linking, Register interop tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_interop_tools(), export_ifc(), link_file() (+22 more)

### Community 336 - "secret_tool.py"
Cohesion: 0.17
Nodes (18): _build_parser(), _ensure_parent(), ensure_secret(), main(), Exception, Both files must exist, be well formed and be byte-for-byte equal., Ensure the secret exists, copy its bytes to ``dest`` and verify the copy., r"""Build-time shared-secret tool: create once, stage byte-for-byte, verify the… (+10 more)

### Community 337 - "World"
Cohesion: 0.07
Nodes (15): FakeResponse, HostAppTrap, make_db(), __getattr__(), __iter__(), fixture, pyRevit's Response: a mutable status and data pair., One fake Revit process: documents, the injected uiapp/doc, and an event log. (+7 more)

### Community 338 - "World"
Cohesion: 0.08
Nodes (16): FakeResponse, HostAppTrap, _Lifetime, local_target(), model_file(), fixture, object, pyRevit's Response: a mutable status and data pair. (+8 more)

### Community 339 - "Info"
Cohesion: 0.11
Nodes (18): CR-01: 25 mutation handlers discard `Transaction.Commit()` status and report success after a silent rollback, Critical Issues, IN-01: Three colour tools return raw error strings instead of `format_response(...)`, IN-02: `listener_snapshot` reads IPv4 listeners only, but `parse_target` accepts `::1`, IN-03: `get_revit_status` still prints "MCP target: localhost:48884", IN-04: Dead variable and unsafe boolean parsing in `save_document`, IN-05: `startup.py` docstring is stale, and the registry import is not isolated, IN-06: `_project_response` can raise on a non-string `status` or `health` (+10 more)

### Community 340 - "test_phase7_rollout.py"
Cohesion: 0.13
Nodes (17): fake_pyrevit(), _MCP, fixture, object, skipif, Phase 7 rollout signals: old extension tolerance and current status…, _response(), _status_text() (+9 more)

### Community 341 - "hash_normalized"
Cohesion: 0.14
Nodes (21): build_manifest(), check_tree(), current_commit(), _hashing(), main(), ManifestError, Exception, Refuse a destination that is, or lies inside, the git working tree. With… (+13 more)

### Community 342 - "documentation_tools.py"
Cohesion: 0.29
Nodes (10): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, Documentation tools — sheets, schedules, and document export, Register documentation tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_documentation_tools(), create_schedule(), create_sheet() (+2 more)

### Community 343 - "Определение общих параметров через ExternalDefinition ошибочно на BindingMap"
Cohesion: 0.12
Nodes (15): Как найден правильный способ, Определение общих параметров через ExternalDefinition ошибочно на BindingMap, Причина ошибки, Проверка на живой модели, Связанное, Симптом, Урок, Что построено в результате (+7 more)

### Community 344 - "test_phase7_scope_docs.py"
Cohesion: 0.36
Nodes (8): parametrize, Verbatim documentation pins for the Phase 7 authorization limits., _read(), test_approval_docstring_pins_each_phase7_limit(), test_claude_md_pins_each_phase7_limit(), test_r5_runbook_names_operator_policy(), test_user_guide_explains_unconfirmed_refusal(), test_user_guide_pins_russian_phase7_limit()

### Community 345 - "Достижение цели"
Cohesion: 0.11
Nodes (17): Override применён (2026-10-23T07:32:13Z), Phase 2: Live identity, ambiguity refusal, and multi-document addressing — отчёт верификации, Анти-паттерны, Артефакты, Достижение цели, Исходное предложение override, Итог, Ключевые связи (+9 more)

### Community 346 - "Phase 7 Plan 12 Summary"
Cohesion: 0.25
Nodes (7): Changes, Commits, Deviations and remaining evidence, Next, Outcome, Phase 7 Plan 12 Summary, Verification

### Community 347 - "view_management_tools.py"
Cohesion: 0.29
Nodes (9): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, View management tools — create views and set active view, Register view management tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_view_management_tools(), create_view(), set_active_view() (+1 more)

### Community 348 - "Policy"
Cohesion: 0.09
Nodes (23): build_policy(), current(), load_base(), _normalized(), parse_policy_bytes(), Policy, policy_hash(), PolicyStore (+15 more)

### Community 349 - "probe_ipy_trust.py"
Cohesion: 0.16
Nodes (16): build_body(), d04_verdict(), exit_code(), _json_or_none(), main(), modules_verdict(), _one_line(), parse_output() (+8 more)

### Community 350 - "2026-10-15 — планирование фазы 2, preflight и проверка 20 планов"
Cohesion: 0.29
Nodes (7): 2026-10-15 — планирование фазы 2, preflight и проверка 20 планов, Запрос и результат, Коммит сессии, Проверки и границы доказательства, Точка продолжения, Условия остановки, Что исправлено проверками

### Community 351 - "object"
Cohesion: 0.05
Nodes (20): get_element(), FakeElement, FakeFamilyManager, FakeFamParam, FakeField, FakeParam, FakeSchedule, object (+12 more)

### Community 352 - "arm_family"
Cohesion: 0.20
Nodes (17): arm_family(), family_entry(), _family_item(), project_entry(), test_edit_family_in_which_no_parameter_applies_is_a_422_that_never_reloads(), test_edit_family_reload_failure_is_a_500_that_says_the_project_did_not_change(), test_edit_family_reload_failure_is_still_a_500_and_carries_the_family_transaction_status(), test_edit_family_reports_the_project_and_the_family_document_it_changed() (+9 more)

### Community 353 - "RouteDocument"
Cohesion: 0.06
Nodes (13): FamilyDoc, InjectedDocument, _Lifetime, Start(), Anything whose use the event log records under its label., A wrapper over one open lifetime. Anything the guard does not read is recorded…, The family document EditFamily opens: not an open project, never in the…, The ``doc`` pyRevit injects. A handler that ignores the guard and uses it shows… (+5 more)

### Community 354 - "Phase 4: Honest outcomes on every mutating route - Research"
Cohesion: 0.12
Nodes (16): Architectural Responsibility Map, Assumptions Log, Current shape of the key contracts (verbatim), Don't Hand-Roll, Environment Availability, Metadata, Mutating-Route Inventory, Open Questions (+8 more)

### Community 355 - "_preflight_dual"
Cohesion: 0.16
Nodes (19): _describe_reply(), _documents_of(), _list(), _parameter_entry(), _preflight_dual(), _preflight_single(), _preflight_target(), One allowed GET: (reply, None) or (None, exception text). (+11 more)

### Community 356 - "_cmd_lines"
Cohesion: 0.16
Nodes (23): _cmd_lines(), _code_lines(), _find(), _logical(), (index, line) of every line that is not a rem comment or blank., The line at ``index`` joined with its ^ continuation lines., test_build_payload_order_stage_arguments_and_failure(), test_build_payload_order_stage_between_app_copy_and_gate() (+15 more)

### Community 357 - "Phase 2 Plan 07: G3/G4 production recheck Summary"
Cohesion: 0.12
Nodes (15): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Live Evidence (authoritative run: g34-production-3.json) (+7 more)

### Community 358 - "Phase 2 Plan 14: Explicit document guard on MEP, parameter, room, structure and tag mutations Summary"
Cohesion: 0.12
Nodes (15): Accomplishments, Auto-fixed Issues, Deviations from Plan, Handler signatures touched, Interface choices, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness (+7 more)

### Community 359 - "Phase 2 Plan 16: Response provenance renderer and per-target Phase-1 regression Summary"
Cohesion: 0.12
Nodes (15): Auto-fixed Issues, Commits, Deviations from Plan, Interface choices, Issues Encountered / Surprises, Known exceptions for the 02-17 inventory, Known Stubs, Next Phase Readiness (+7 more)

### Community 360 - "Phase 3 Plan 04: Payload Integrity Slice Summary"
Cohesion: 0.12
Nodes (15): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness (+7 more)

### Community 361 - "Phase 03 Plan 09: WR-01 share-drop corroboration Summary"
Cohesion: 0.12
Nodes (15): Accomplishments, Baseline, red and final output, Decisions Made, Deviations from Plan, Issues Encountered, Known Stubs, New symbols and tests, Performance (+7 more)

### Community 362 - "Plan 05-14 Summary: live corrupt stage (verdict PHASE5_GATE_OK, PASS)"
Cohesion: 0.11
Nodes (17): Classify, `classify --stage corrupt C:/Temp/phase5/S2-corrupt.json` (exit 0), Console output (verbatim), Deviations from Plan, INTG-03: the extension wrote nothing while loaded, Known Stubs, Listener and document checks (before the run, by the executor), MCP read after the script (orchestrator, read only, verbatim), Plan 05-14 Summary: live corrupt stage (verdict PHASE5_GATE_OK, PASS) (+9 more)

### Community 363 - "_through_the_bridge"
Cohesion: 0.21
Nodes (14): _IronPython3Json, _mismatch_naming(), json as IronPython 3 ships it: loads() refuses bytes (see test_secret_gate_e2e)., LEVEL_BODY as the bridge sends it after Phase 7: envelope first, with a real…, POST ``body`` to the real /create_level/ handler through the unchanged…, _refusal_case(), test_create_level_refusals_happen_before_any_document_access(), test_create_level_through_the_real_bridge_send_path_reaches_the_handler_without_the_envelope() (+6 more)

### Community 364 - "_share_outage"
Cohesion: 0.18
Nodes (11): _forbidden(), _guards(), guarded_open(), The guard itself works: a write attempt inside it fails loudly., The write guards plus an outage: open() and os.listdir fail from a chosen call…, Write guards plus an optional failing open(). fail maps a path suffix to the…, _share_outage(), outage_listdir() (+3 more)

### Community 365 - "test_broken_paths.py"
Cohesion: 0.18
Nodes (16): BOTH, Broken-Windows-path detection, in both runtimes' copies of the helper. The bug…, The reported path, correctly escaped, must pass untouched., An escaped 1 collapses to U+0008 -- the exact reported failure., A filename starting with n is the classic case., The two copies are duplicated by the Two-Runtime Rule; keep them in step., test_backspace_from_escaped_one_is_detected(), test_both_runtimes_agree() (+8 more)

### Community 366 - "Common Pitfalls"
Cohesion: 0.12
Nodes (16): Common Pitfalls, Pitfall 10: Mixed versions - new extension with old bridge, and payload rollback, Pitfall 11: Refusal hint texts are pinned by tests and must match D-07, Pitfall 12: The gate must run before `_stamp_exception` on `/execute_code/` and still refuse, Pitfall 13: `/status/` payload rendering, Pitfall 14: Live gate prerequisites on the dev machine, Pitfall 15: Two helpers lists in tests must learn the new module, Pitfall 1: The gate is added and ~hundreds of existing handler tests go red (+8 more)

### Community 367 - "Corporate deployment (closed network)"
Cohesion: 0.17
Nodes (12): Coexistence with another MCP, Corporate deployment (closed network), Diagnosing a broken workstation, First-time install (per user), Layout, Releasing, Rollback, Starting Revit from the MCP server (+4 more)

### Community 368 - "Phase 2 Plan 12: Explicit document guard on annotation, building, colors and detail mutations Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Deviations from Plan, Handler signatures touched, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed (+6 more)

### Community 369 - "Phase 2 Plan 13: Explicit document guard on save, documentation, editing, interop and family mutations Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Deviations from Plan, Handler signatures touched, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed (+6 more)

### Community 370 - "Phase 2 Plan 15: Transform/view guard, process-scoped open_model and the D-15 execute exception Summary"
Cohesion: 0.13
Nodes (14): Auto-fixed Issues, Commits, Deviations from Plan, Handler signatures touched, Interface choices, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness (+6 more)

### Community 371 - "Phase 2 Plan 17: Exhaustive tool and route regression inventory Summary"
Cohesion: 0.13
Nodes (14): Auto-fixed Issues, Commits, Deviations from Plan, Interface choices, Known Stubs, Named exceptions (exact sets, cannot grow silently), Observations (not fixed; nothing here was in scope or wrong enough to change), Phase 2 Plan 17: Exhaustive tool and route regression inventory Summary (+6 more)

### Community 372 - "Phase 3 Plan 06: Bind classifier and IronPython 3 proof Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+6 more)

### Community 373 - "Info"
Cohesion: 0.11
Nodes (17): IN-01: Dead production code: `trust.gate_applies` and `UNGATED_METHODS`, IN-02: Live-gate runner's direct HTTP client ignores the proxy hazard the bridge documents, IN-03: `scripts/new_tool.py` docstring contradicts the project rule, and scaffolding can leave an orphan route file, IN-04: Weak or inert assertions in the Phase 5 tests, IN-05: Duplicate initialization in `status.py`, IN-06: `get_revit_status` can claim "this MCP server loaded none" when the transport simply has no fingerprint seam, IN-07: Integrity scope is narrower than the loaded code, IN-08: `scan_envelope_tolerance.py` cannot see a body parse that goes through `getattr` or an alias (+9 more)

### Community 374 - "parametrize"
Cohesion: 0.35
Nodes (16): parametrize, The docstring is the API contract the model sees before calling., f-strings, async and Python-3-only imports break extension load., _read(), _rel(), _report(), test_commits_go_through_commit_and_report(), test_element_id_helpers_are_used() (+8 more)

### Community 375 - "Первичная настройка и пилотная раскатка"
Cohesion: 0.14
Nodes (14): 0. Переезд шары (только один раз, 2026-09-09), 10. Если что-то не так, 11. Решить до раскатки шире пилота, 1. Как папки выглядят сейчас и как должны, 2. Права доступа. Запрос в ИТ, 3. Что должно быть на машине, с которой публикуете, 4. Публикация Revit-половины, 5. Сборка CPython-половины (+6 more)

### Community 376 - "Phase 3 Plan 01: Secret gate pure logic and request envelope Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Auto-fixed Issues, Decisions for review at plan check, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+5 more)

### Community 377 - "Phase 3 Plan 02: Build-side secret tool Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+5 more)

### Community 378 - "Phase 3 Plan 03: Bridge secret loading and the 401 visibility pair Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+5 more)

### Community 379 - "Phase 3 Plan 05: Integrity Reader and Generator Hardening Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+5 more)

### Community 380 - "Phase 3 Plan 07: Secret and Manifest Build Wiring Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+5 more)

### Community 381 - "Phase 3 Plan 08: Live D-04 Probe and Recorded Result Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Next Phase Readiness, Performance, Phase 3 Plan 08: Live D-04 Probe and Recorded Result Summary (+5 more)

### Community 382 - "Phase 3: Secret gate and payload integrity (unit-verified) - Research"
Cohesion: 0.14
Nodes (13): Architectural Responsibility Map, Assumptions Log, Conflicts between locked decisions and shipped code (planner/user must acknowledge), Don't Hand-Roll, Environment Availability, Metadata, Open Questions (RESOLVED), Package Legitimacy Audit (+5 more)

### Community 383 - "Phase 2 Plan 08: target/document on analysis, annotation, building, clash and color tools Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed, Performance, Phase 2 Plan 08: target/document on analysis, annotation, building, clash and color tools Summary (+4 more)

### Community 384 - "Phase 2 Plan 09: target/document on detail, documentation, save, editing and family tools Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed, Performance, Phase 2 Plan 09: target/document on detail, documentation, save, editing and family tools Summary (+4 more)

### Community 385 - "Phase 2 Plan 10: target/document on interop, MEP, model, parameter and room tools Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed, Performance, Phase 2 Plan 10: target/document on interop, MEP, model, parameter and room tools Summary (+4 more)

### Community 386 - "Phase 2 Plan 11: target/document on structure, tag, transform, view and worksharing tools Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Deviations from Plan, Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Not run / not claimed, Performance, Phase 2 Plan 11: target/document on structure, tag, transform, view and worksharing tools Summary (+4 more)

### Community 387 - "make_db"
Cohesion: 0.11
Nodes (12): _Elements, make_db(), __getattr__(), __getitem__(), _items(), __iter__(), __len__(), _narrow() (+4 more)

### Community 388 - "make_db"
Cohesion: 0.12
Nodes (8): _Elements, make_db(), __getattr__(), _items(), __iter__(), Start(), list, What ToElements answers: a list that also has the .NET collection's Count.

### Community 389 - "Phase 5 Plan 01: Tracer gate on /create_level/ Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, D-06 findings, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance (+6 more)

### Community 390 - "Phase 2 Plan 18: Live acceptance Summary"
Cohesion: 0.17
Nodes (11): Authorizations (recorded with the user's own words, 2026-10-22 21:20 UTC), Deviations from Plan, G6 evidence (not an approval), Issues Encountered / Surprises, Known Stubs, Next Phase Readiness, Per-criterion result, Phase 2 Plan 18: Live acceptance Summary (+3 more)

### Community 391 - "Info"
Cohesion: 0.17
Nodes (11): IN-01: Secret creation can be observed half-written by a concurrent build, IN-02: Whitespace definitions differ between the file reader and the configured check, IN-03: Integrity scope has gaps that a reader of "unexpected" would not expect, IN-04: gate.py runs unchecked when MCP_SECRET_FILE is unset, and uses `assert`, IN-05: make_manifest mutates sys.path and imports at module import time, Info, Phase 3: Code Review Report, Summary (+3 more)

### Community 392 - "Релизный план milestone v0.1 «Доверенный мост»"
Cohesion: 0.15
Nodes (12): A. Входные условия (проверяет Claude, до любых сборок), B. Сборка и проверка — решает пользователь, C. Фиксация (после выпуска), Ledger, R3 — решено при планировании фазы 5 (2026-10-24), Выпуск (общая процедура), Особенности отдельных релизов, Открытые вопросы (закрывает пользователь, не Claude) (+4 more)

### Community 393 - "FakeMCP"
Cohesion: 0.17
Nodes (9): FakeMCP, load(), route(), register(), The tool's target reaches bridge.revit_post: an unprovable incarnation is…, Register one module through its real registrar; returns {(route, method):…, test_every_registered_route_is_classified(), test_execute_code_stays_registered_and_takes_no_selector_guard_or_412() (+1 more)

### Community 394 - "Common Pitfalls"
Cohesion: 0.18
Nodes (11): Common Pitfalls, Pitfall 10: Editing files the user has uncommitted changes in, Pitfall 1: A developer's secret gets published to the fleet, Pitfall 2: The payload cannot import `revit_mcp`, Pitfall 3: Mixed line endings and `core.autocrlf`, Pitfall 4: A secret file written with a BOM, UTF-16 or a trailing newline, Pitfall 5: `unexpected` makes legitimate publishes fatal, Pitfall 6: Dev layout mismatch between halves (+3 more)

### Community 395 - "Goal Achievement"
Cohesion: 0.18
Nodes (10): Anti-Patterns, Dialect guards, Gaps Summary, Goal Achievement, Inertness (re-checked), Known residuals (stated honestly; none is a success-criterion gap), Observable Truths (ROADMAP success criteria), Phase 3: Secret gate and payload integrity (unit-verified) Verification Report (+2 more)

### Community 396 - "registry.py"
Cohesion: 0.25
Nodes (7): is_degraded(), Registration registry for the Revit MCP extension. startup.py writes the…, Clear all three collections in place, keeping the same objects., Return a JSON-serializable view for the /status/ route. The default is…, True when at least one domain failed to register., reset(), snapshot()

### Community 397 - "Locked Decisions"
Cohesion: 0.20
Nodes (10): Claude's Discretion, Deferred Ideas (OUT OF SCOPE), Locked Decisions, User Constraints (from CONTEXT.md), Бинд не на loopback (SEC-07), Генерация и хранение секрета, Конверт запроса и секрет в теле, Манифест целостности (+2 more)

### Community 398 - "execute_code остаётся аварийным люком для отсутствующих инструментов"
Cohesion: 0.25
Nodes (8): execute_code остаётся аварийным люком для отсутствующих инструментов, Известные технические дефекты этого файла, Обоснование, Обратная сторона — и это настоящая проблема, Полезная деталь реализации, Предложенное решение, Решение, Связанное

### Community 399 - "startup_tree"
Cohesion: 0.15
Nodes (13): fake_pyrevit(), make_response(), fixture, pyRevit reduced to routes.make_response, and a state that starts uninitialized., The real startup.py run under CPython from a temporary extension tree., startup_tree(), build(), load() (+5 more)

### Community 400 - "Phase 6 Plan 04: Correlation and the published schema change Summary"
Cohesion: 0.12
Nodes (15): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Limitations (+7 more)

### Community 401 - "object"
Cohesion: 0.09
Nodes (14): get_element(), FakeElement, FakeParam, _Item, _OddParam, object, A parameter whose StorageType is none of String, Integer, Double or ElementId., A writable string parameter that records what it was set to. (+6 more)

### Community 402 - "annotation_tools.py"
Cohesion: 0.29
Nodes (9): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, Annotation tools — dimensions and wall tags, Register annotation tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_annotation_tools(), create_dimensions(), tag_walls() (+1 more)

### Community 403 - "Два процесса Revit.exe могут слушать 48884 одновременно без ошибки"
Cohesion: 0.22
Nodes (8): Два процесса Revit.exe могут слушать 48884 одновременно без ошибки, Диагностика, Обход, Причина, Связанное, Симптом, Урок, Уточнение причины (2026-10-07, research фазы 1)

### Community 404 - "Architecture Patterns"
Cohesion: 0.22
Nodes (9): Anti-Patterns to Avoid, Architecture Patterns, Pattern 1: One pure module, simulated hostile runtime, Pattern 2: Hash-then-XOR compare with no early exit (D-04/D-05), Pattern 3: Envelope split that never raises and never echoes, Pattern 4: Three-state integrity with an injected observation, Pattern 5: Manifest generation from tracked files, hashing the published copies, Recommended Project Structure (+1 more)

### Community 405 - "RouteDocument"
Cohesion: 0.06
Nodes (14): FakeUIDocument, InjectedDocument, Start(), setter, Anything whose use the event log records under its label., A wrapper over one open lifetime. Anything the guard does not read is recorded…, The ``doc`` pyRevit injects. A handler that ignores the guard and uses it shows…, The UI side of one open lifetime; assigning ActiveView is the recorded side… (+6 more)

### Community 406 - "register_everything"
Cohesion: 0.26
Nodes (11): Run the real discovery against a recording transport. Returns (tools by name,…, register_everything(), answer(), revit_get(), revit_image(), revit_post(), test_tool_discovery_registers_every_domain_and_only_utils_is_a_helper(), Phase 7 model-facing confirmation contract on the risky tool surface. (+3 more)

### Community 407 - "03-07-PLAN.md"
Cohesion: 0.25
Nodes (7): Artifacts this phase produces (this plan), Decision reconciliations and assumptions (for review at plan approval), Dirty-tree commit protocol (Task 1: `deploy/publish-extension.cmd` carries the user's uncommitted edit), Edge-probe assumptions flagged for review (no silent drops), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 408 - "03-09-PLAN.md"
Cohesion: 0.25
Nodes (7): Artifacts this phase produces (this plan), Notes the executor needs, Residuals recorded, not closed (must appear in the integrity.py docstring and the SUMMARY), Source coverage audit, STRIDE Threat Register, Trust Boundaries, Why this fix, and not the two options the reviewer sketched

### Community 409 - "Phase 3 — Validation Strategy"
Cohesion: 0.25
Nodes (7): Manual-Only Verifications, Per-Task Verification Map, Phase 3 — Validation Strategy, Sampling Rate, Test Infrastructure, Validation Sign-Off, Wave 0 Requirements

### Community 410 - "Warnings"
Cohesion: 0.14
Nodes (13): IN-01: Contributor templates tell the contributor to call `exception_outcome` but do not import it, and show `t` declared inside the `try`, IN-02: Live-gate classifier never reads `preflight.tag_element_found`, IN-03: colors routes lose the real status when an exception unwinds the `with DB.Transaction(...)`, IN-04: `_set_step` is duplicated between rooms.py and mep.py, Info, Phase 4: Code Review Report, Summary, Warnings (+5 more)

### Community 411 - "Goal Achievement"
Cohesion: 0.13
Nodes (14): Anti-Patterns Found, Behavioral Spot-Checks, Data-Flow Trace (Level 4), Gaps Summary, Goal Achievement, Human Verification Required, Key Link Verification, Live-evidence provenance (+6 more)

### Community 412 - "Phase 6 Plan 01: Structured audit log tracer slice Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness (+6 more)

### Community 413 - "03-01-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Decision reconciliations (adopted from 03-RESEARCH.md; CONTEXT.md is not rewritten), Edge-probe assumptions flagged for review (no silent drops), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 414 - "03-02-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Decision reconciliations (adopted from 03-RESEARCH.md), Dirty-tree commit protocol (Task 2 only: `.gitignore` carries the user's uncommitted edits), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 415 - "03-03-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Decision reconciliations (adopted from 03-RESEARCH.md), Edge-probe assumptions flagged for review (no silent drops), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 416 - "03-04-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Edge-probe assumptions flagged for review (no silent drops), Execution rules for every task in this plan, Notes the executor needs, STRIDE Threat Register, Trust Boundaries

### Community 417 - "_folders"
Cohesion: 0.21
Nodes (23): needs_windows_publish, _assert_scratch(), _folders(), _publish(), Fail (never skip) unless every path the publish writes is under tmp_path., Run a deploy script on the scratch share and never let it print the secret., (live, stage, prev, rejected) folders of the scratch share., {relative path: sha256 of the bytes} for every file under root (bytes, not… (+15 more)

### Community 418 - "load"
Cohesion: 0.29
Nodes (6): load(), route(), Register one module through its real registrar; returns {(route, method):…, analysis.py only reads (ai_filter and material_quantities travel as POST):…, test_analysis_has_no_mutating_route(), test_every_registered_route_is_classified()

### Community 419 - "Bare DB.ElementId(int) в Revit 2027 падает на неоднозначности перегрузок"
Cohesion: 0.25
Nodes (8): Bare DB.ElementId(int) в Revit 2027 падает на неоднозначности перегрузок, Обход, Почему это отдельно важно для execute_code, Причина, Связанное, Симптом, Смежная разница версий, Урок

### Community 420 - "03-05-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Edge-probe assumptions flagged for review (no silent drops), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 421 - "03-06-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Edge-probe assumptions flagged for review (no silent drops), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 422 - "03-UAT.md"
Cohesion: 0.33
Nodes (5): 1. Decision on WR-01 (dropped network share mid-scan reads as verified_mismatch), Current Test, Gaps, Summary, Tests

### Community 423 - "Phase 5 Plan 02: Gate and strip across annotation, building, colors, detail, analysis and clash Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, D-06 findings, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 5 Plan 02: Gate and strip across annotation, building, colors, detail, analysis and clash Summary (+5 more)

### Community 424 - "Phase 6 Plan 02: Full honest schema 1 and exact call set Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness (+6 more)

### Community 425 - "Phase 6 Plan 03: Request side of the entry and secret redaction Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness (+6 more)

### Community 426 - "Phase 5 Plan 03: Gate document, documentation, editing, interop and placement Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, D-06 findings, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 5 Plan 03: Gate document, documentation, editing, interop and placement Summary (+5 more)

### Community 427 - "FList"
Cohesion: 0.40
Nodes (3): FList, list, System.Collections.Generic.List: Add and Count.

### Community 428 - "03-08-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Notes the executor needs, STRIDE Threat Register, Trust Boundaries

### Community 429 - "Validation Architecture"
Cohesion: 0.40
Nodes (5): Phase Requirements -> Test Map, Sampling Rate, Test Framework, Validation Architecture, Wave 0 Gaps

### Community 430 - "load"
Cohesion: 0.40
Nodes (4): load(), route(), Register one module through its real registrar; returns {(route, method):…, test_every_registered_route_is_classified()

### Community 431 - "load"
Cohesion: 0.40
Nodes (4): load(), route(), Register one module through its real registrar; returns {(route, method):…, test_every_registered_route_is_classified()

### Community 432 - "Phase 5 Plan 04: Gate mep, parameters, rooms, structure and tags Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, D-06 findings, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 5 Plan 04: Gate mep, parameters, rooms, structure and tags Summary (+5 more)

### Community 433 - "_load"
Cohesion: 0.60
Nodes (5): dev_secret(), gate(), _load(), fixture, secret_tool()

### Community 434 - "parametrize"
Cohesion: 0.15
Nodes (15): child_argv(), _explode(), parametrize, test_a_missing_option_is_a_usage_error_that_sends_nothing(), test_an_audit_dir_with_files_is_refused_before_the_bridge_is_touched(), test_an_existing_out_record_is_refused_untouched_before_the_bridge_is_touched(), test_child_issues_its_calls_flushes_and_writes_its_record(), test_child_refuses_a_token_that_differs_from_the_environment() (+7 more)

### Community 435 - "Phase 6: Structured audit log of true outcomes - Research"
Cohesion: 0.14
Nodes (13): Architectural Responsibility Map, Assumptions Log, Don't Hand-Roll, Environment Availability, Metadata, Open Questions, Package Legitimacy Audit, Phase 6: Structured audit log of true outcomes - Research (+5 more)

### Community 436 - "refusal"
Cohesion: 0.21
Nodes (13): _child_refusal(), _cmd_child(), _cmd_rehearse(), _cmd_run_dual(), _cmd_run_single(), main(), _outside_repo(), Why the child may not run, or None; it shares the runner's audit directory, so… (+5 more)

### Community 437 - "Phase 5 Plan 05: Gate transforms, view management, model open, arbitrary code and document activation Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, D-06 findings, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 5 Plan 05: Gate transforms, view management, model open, arbitrary code and document activation Summary (+5 more)

### Community 438 - "Standard Stack"
Cohesion: 0.50
Nodes (4): Alternatives Considered, Core, Standard Stack, Supporting

### Community 439 - "Code Examples"
Cohesion: 0.50
Nodes (4): Build-order assertion (unit test over the `.cmd` text), Client half in `bridge.py` (additive, not wired), Code Examples, Live gate snippet for D-04 (human checkpoint, `/execute_code/`)

### Community 440 - "Sources"
Cohesion: 0.50
Nodes (4): Primary (HIGH confidence), Secondary (MEDIUM confidence), Sources, Tertiary (LOW confidence)

### Community 441 - "Phase 5 Plan 09: D-06 envelope tolerance scanner Summary"
Cohesion: 0.14
Nodes (13): Accomplishments, Auto-fixed Issues, Command for the administrator, Deviations from Plan, Issues Encountered, Known limitations of the static scan (why it is only half the proof), Known Stubs, Next Phase Readiness (+5 more)

### Community 442 - "Phase 5: Live secret gate and integrity enforcement - Research"
Cohesion: 0.14
Nodes (13): Architectural Responsibility Map, Assumptions Log, Don't Hand-Roll, Environment Availability, Metadata, Open Questions, Package Legitimacy Audit, Phase 5: Live secret gate and integrity enforcement - Research (+5 more)

### Community 443 - "_FakeHashlib"
Cohesion: 0.17
Nodes (9): _digest(), 32 SHA-256 bytes of a text or bytes value as a bytearray, else None. Text is…, _FakeHashlib, _FakeSha, object, Guard the guard: the fake hashlib returns the type the test claims., test_digest_types_do_not_change_the_verdicts(), test_digest_types_fake_really_is_used() (+1 more)

### Community 444 - "Phase 6 Plan 05: Retention, stdio proof and documentation Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 6 Plan 05: Retention, stdio proof and documentation Summary (+4 more)

### Community 445 - "call"
Cohesion: 0.11
Nodes (40): assert_refused(), body_of(), call(), is_failure(), parametrize, Two documents open, one explicitly selected: the other is neither read nor…, The route a handler was registered under: pyRevit's request.path is that API-…, Invoke a handler the way pyRevit does: injected arguments by name. ``request``… (+32 more)

### Community 446 - "Phase 4 Plan 08: D-02 static rule and scaffold/docs update Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 4 Plan 08: D-02 static rule and scaffold/docs update Summary (+4 more)

### Community 447 - "Goal Achievement"
Cohesion: 0.15
Nodes (12): Anti-Patterns Found, Behavioral Spot-Checks, Data-Flow Trace (Level 4), Gaps Summary, Goal Achievement, Human Verification Required, Key Link Verification, Observable Truths (ROADMAP success criteria) (+4 more)

### Community 448 - "Security Domain"
Cohesion: 0.67
Nodes (3): Applicable ASVS Categories, Known Threat Patterns for this stack, Security Domain

### Community 449 - "test_save_as_that_lands_elsewhere_never_claims_the_requested_path"
Cohesion: 0.40
Nodes (4): Prohibition: do not report a save as affecting the requested path when the…, test_a_save_as_reports_the_path_the_document_has_after_it(), lands_elsewhere(), test_save_as_that_lands_elsewhere_never_claims_the_requested_path()

### Community 450 - "Phase 5 Plan 07: Status diagnostics Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Performance, Phase 5 Plan 07: Status diagnostics Summary, Self-Check: PASSED (+4 more)

### Community 451 - "Phase 5 Plan 16: Bridge envelope and startup gate initialization Summary"
Cohesion: 0.15
Nodes (12): Accomplishments, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 5 Plan 16: Bridge envelope and startup gate initialization Summary, Self-Check: PASSED (+4 more)

### Community 452 - "Phase 4 Plan 01: Honest outcomes tracer (tag_elements) Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 4 Plan 01: Honest outcomes tracer (tag_elements) Summary (+3 more)

### Community 453 - "Phase 4 Plan 02: mep, rooms, structure and set_parameter outcomes Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 4 Plan 02: mep, rooms, structure and set_parameter outcomes Summary (+3 more)

### Community 454 - "arm_export"
Cohesion: 0.18
Nodes (16): arm_export(), export_dir_of(), export_path(), test_a_dwg_export_that_raises_rolls_back_and_carries_the_outcome_on_its_500(), test_a_dwg_export_that_returns_false_is_a_422_naming_the_output_path(), test_a_dwg_export_that_returns_true_reports_the_path_as_succeeded(), test_a_pdf_export_that_raises_rolls_back_and_carries_the_outcome_on_its_500(), test_a_pdf_export_that_returns_false_is_a_422_and_no_longer_a_rolled_back_500() (+8 more)

### Community 455 - "load_record"
Cohesion: 0.27
Nodes (12): dual_argv(), install_fake_child(), load_record(), A stand-in for the second server process: leaves its record and its audit file…, test_run_dual_end_to_end_with_a_second_server_process_is_ok(), test_run_dual_gives_the_lowest_port_the_first_wall(), test_run_dual_kills_a_child_that_never_finishes_and_reports_an_unknown_count(), test_run_dual_stops_when_the_child_leaves_no_audit_file() (+4 more)

### Community 456 - "Phase 4 Plan 03: building, annotation and detail outcomes Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 4 Plan 03: building, annotation and detail outcomes Summary (+3 more)

### Community 458 - "Phase 4 Plan 04: delete, export, link and save outcomes Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 4 Plan 04: delete, export, link and save outcomes Summary (+3 more)

### Community 459 - "Phase 4 Plan 05: view and code route outcomes Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 4 Plan 05: view and code route outcomes Summary (+3 more)

### Community 460 - "Phase 4 Plan 06: documentation and placement outcomes Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 4 Plan 06: documentation and placement outcomes Summary (+3 more)

### Community 461 - "Phase 4 Plan 07: colour route outcomes Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Performance, Phase 4 Plan 07: colour route outcomes Summary (+3 more)

### Community 462 - "Phase 4 Plan 10: Live outcome gate instrument Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Notes for plan 04-11, Performance, Phase 4 Plan 10: Live outcome gate instrument Summary (+3 more)

### Community 463 - "User Constraints (from CONTEXT.md)"
Cohesion: 0.17
Nodes (12): Claude's Discretion, Deferred Ideas (OUT OF SCOPE), Locked Decisions, User Constraints (from CONTEXT.md), Источник записи и место записи, Корреляция вызова инструмента, Модель, «кто», содержимое запроса и персональные данные, Проверка (+4 more)

### Community 464 - "Phase 4 Plan 09: Outcome docstrings for the mutation tools Summary"
Cohesion: 0.18
Nodes (10): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Phase 4 Plan 09: Outcome docstrings for the mutation tools Summary, Self-Check: PASSED (+2 more)

### Community 465 - "Phase 7 Plan 11 Summary"
Cohesion: 0.29
Nodes (6): Changes, Deviations and remaining evidence, Next, Outcome, Phase 7 Plan 11 Summary, Verification

### Community 466 - "policy.py"
Cohesion: 0.15
Nodes (28): _check_keys(), _check_route(), _check_schema(), _check_settings(), _fail(), merge(), _overlay(), Any (+20 more)

### Community 467 - "call_name"
Cohesion: 0.19
Nodes (17): call_name(), module_registrars(), parse_revit_module(), Module names startup.py's _domain_modules() would scan., revit_mcp_modules(), _enclosing_function_names(), Print the true current counts; CLAUDE.md still says 54 tools / 51 routes / 23…, G4: the single activation call site is documents.run_activation; open_model is… (+9 more)

### Community 468 - "2026-10-25 — приёмка фазы 6, UAT 4 из 4, SECURITY.md 38 из 38, фаза закрыта, R4 отложен"
Cohesion: 0.29
Nodes (6): 2026-10-25 — приёмка фазы 6, UAT 4 из 4, SECURITY.md 38 из 38, фаза закрыта, R4 отложен, Дальше, Коммиты, Оговорка по T-06-08, Открытое, Что сделано

### Community 469 - "Common Pitfalls"
Cohesion: 0.20
Nodes (10): Common Pitfalls, Pitfall 1: `suppress_warnings(t)` result discarded, Pitfall 2: reading model state after a rolled-back commit, Pitfall 3: pinned key sets and source text, Pitfall 4: a committed route that then raises, Pitfall 5: statuses other than Committed/RolledBack, Pitfall 6: exports report success without checking what the export call returned, Pitfall 7: `already tagged` and other no-op items (+2 more)

### Community 470 - "Phase 4 — Validation Strategy"
Cohesion: 0.20
Nodes (9): Live gate result (plan 04-11, recorded 2026-10-23), Manual-Only Verifications, Per-task map (filled by the planner, 2026-10-23), Per-Task Verification Map, Phase 4 — Validation Strategy, Sampling Rate, Test Infrastructure, Validation Sign-Off (+1 more)

### Community 471 - "Phase 5 Plan 08: Staged publish, rollback and manifest modes Summary"
Cohesion: 0.20
Nodes (9): Commits, Deviations from Plan, Execution note, Known Stubs, Open item for 05-10, Phase 5 Plan 08: Staged publish, rollback and manifest modes Summary, Self-Check: PASSED, Threat Flags (+1 more)

### Community 472 - "Architecture Patterns"
Cohesion: 0.20
Nodes (10): Anti-Patterns to Avoid, Architecture Patterns, Pattern 1: Two-statement gate preamble, gate before the document guard, Pattern 2: `security.py` as a load-time state holder (mirrors `identity.initialize_process_identity`), Pattern 3: AST sentinel for "closed by default" (the D-01 guard), Pattern 4: Strip without refusing on the 7 open POST reads, Pattern 5: `/status/` block built from module state; bind from .NET at request time, Pattern 6: Envelope in `revit_post`, not in `_send` (+2 more)

### Community 473 - "test_policy_decisions.py"
Cohesion: 0.17
Nodes (27): anyio_backend(), decision(), merged_rule(), parameter_facts(), fixture, parametrize, Pure decision-table tests for the Phase 7 mutation-safety policy., rule() (+19 more)

### Community 474 - "04-01-PLAN.md"
Cohesion: 0.22
Nodes (8): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less edge probe, not silently dropped), Item convention (Claude's discretion, recorded in CONTEXT; applies to every plan), Route pattern every migration follows (later plans copy it), STRIDE Threat Register, The outcome contract (defined here, imported by every later plan), Trust Boundaries

### Community 475 - "world"
Cohesion: 0.15
Nodes (14): fixture, world(), create_3d(), _family(), _Item, A ViewFamilyType of the given DB.ViewFamily member., The view the fake creation call returns. Every public read is logged as a…, A collector result: a named element with the few members the routes read. (+6 more)

### Community 476 - "_edit_family"
Cohesion: 0.18
Nodes (9): _attach_documents_changed(), _documents_changed(), _family_param_value(), _FamilyReloadOptions, Every document one edit_family call worked on, each with what actually changed.…, Add ``documents_changed`` to a dict reply, whatever its outcome. Never raises., Answer Revit's "this family is already loaded" prompts without a dialog.…, Convert a tool-facing family parameter value to Revit's internal units. Tool-… (+1 more)

### Community 477 - "Докстринг инструмента — это контракт для модели, а не для разработчика"
Cohesion: 0.25
Nodes (8): Docstring — часть исправления бага, Докстринг инструмента — это контракт для модели, а не для разработчика, На Revit-стороне тоже, Почему это буквально так, Правила, Связанное, Структура, которую он задаёт, Эталон — `check_clashes` в `tools/clash_tools.py`

### Community 478 - "Machine"
Cohesion: 0.29
Nodes (3): Machine, fixture, Fake listener table and fake Routes servers for two Revit processes.

### Community 479 - "User Constraints (from CONTEXT.md)"
Cohesion: 0.25
Nodes (8): Claude's Discretion, Deferred Ideas (OUT OF SCOPE), Locked Decisions, User Constraints (from CONTEXT.md), Видимость частичного отказа для модели, Единая форма исхода, Охват миграции, Проверка

### Community 480 - "Phase 5: Live secret gate and integrity enforcement - Discussion Log"
Cohesion: 0.25
Nodes (7): Claude's Discretion, Deferred Ideas, Phase 5: Live secret gate and integrity enforcement - Discussion Log, Живая приёмка на стенде, Откат Revit-половины, Порядок выкладки и смешанные версии, Что закрывает секрет

### Community 481 - "User Constraints (from CONTEXT.md)"
Cohesion: 0.25
Nodes (8): Claude's Discretion, Deferred Ideas (OUT OF SCOPE), Locked Decisions, User Constraints (from CONTEXT.md), Живая приёмка, Откат Revit-половины, Порядок выкладки и смешанные версии (R3), Что закрывает секрет

### Community 482 - "Phase 5 — Validation Strategy"
Cohesion: 0.20
Nodes (9): Gaps and history, Live gate phase verdict (recorded 2026-10-24), Manual-Only Verifications, Per-Task Verification Map, Phase 5 — Validation Strategy, Sampling Rate, Test Infrastructure, Validation Sign-Off (+1 more)

### Community 483 - "Tests"
Cohesion: 0.20
Nodes (9): 1. R3 pilot-first rollout (D-06 rehearsal on the pilot share), 2. D-10 second-publish probe with Revit open (on the pilot), 3. First fleet machine after publish to the main share, 4. R3 release checkpoint decision, 5. WR-01 decision: /model_worksets/ open read takes a caller-supplied file_path, Current Test, Gaps, Summary (+1 more)

### Community 484 - "Architecture Patterns"
Cohesion: 0.22
Nodes (9): Anti-Patterns to Avoid, Architecture Patterns, Entry construction (pure function), Hook seams (exact), Pattern 1: Tool wrapper installed from main.py (verified prototype), Pattern 2: Roll-forward file handler (verified prototype, Python 3.13.7 and 3.14.2), Pattern 3: In-process fake Revit through the real bridge (verified), Recommended Project Structure (+1 more)

### Community 485 - "Pilot fixes — offline verification"
Cohesion: 0.29
Nodes (6): Automated checks, Failures investigated, not hidden, Implemented, Next authorization, Pilot fixes — offline verification, Real evidence — not reclassified

### Community 486 - "Pattern Assignments"
Cohesion: 0.07
Nodes (26): `audit.py` (MOD), `bridge.py` (MOD, middleware, request-response), `deploy/build-payload.cmd` (MOD), `deploy/config.cmd` (MOD), Deploy: `deploy/server.py`, `gate.py`, `warm.py` (pywin32 shim), Envelope (`_mcp`) handling, File Classification, Honest outcomes (+18 more)

### Community 487 - "04-04-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less edge probe, TRUTH-02 unclassified edge), Interface from 04-01 (import from `.utils`; do not edit utils.py or textutils.py here), STRIDE Threat Register, Trust Boundaries

### Community 488 - "04-09-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Scope note (file count): why 15 files in one plan is safe, STRIDE Threat Register, The four paragraphs (paste verbatim, as its own paragraph immediately before `Args:`), Trust Boundaries

### Community 489 - "05-01-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less edge probe, 17 items, none dropped), STRIDE Threat Register, The gate contract (defined here; every later plan relies on it), Trust Boundaries

### Community 490 - "test_deploy_libpaths.py"
Cohesion: 0.15
Nodes (24): _calls_shim(), _fake_libs(), _first_sdk_use(), _function_node(), _is_libs_insert(), _load_function(), fixture, parametrize (+16 more)

### Community 491 - "test_policy_tool.py"
Cohesion: 0.15
Nodes (19): cmd_lines(), gate(), fixture, Phase 7 build-time policy tooling (07-04 task 3): stage the operator path,…, read(), run_tool(), test_build_payload_stages_the_path_then_checks_before_the_gate_and_keeps_lf(), test_check_of_a_missing_file_is_absent_and_exits_0() (+11 more)

### Community 492 - "04-02-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Interface from 04-01 (import from `.utils`; do not edit utils.py or textutils.py here), STRIDE Threat Register, Trust Boundaries

### Community 493 - "04-03-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Interface from 04-01 (import from `.utils`; do not edit utils.py or textutils.py here), STRIDE Threat Register, Trust Boundaries

### Community 494 - "04-05-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Interface from 04-01 (import from `.utils`; do not edit utils.py or textutils.py here), STRIDE Threat Register, Trust Boundaries

### Community 495 - "04-06-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Interface from 04-01 (import from `.utils`; do not edit utils.py or textutils.py here), STRIDE Threat Register, Trust Boundaries

### Community 496 - "04-07-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Interface from 04-01 (import from `.utils`; do not edit utils.py or textutils.py here), STRIDE Threat Register, Trust Boundaries

### Community 497 - "04-08-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Dirty-tree commit protocol (Task 2 only), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 498 - "Validation Architecture"
Cohesion: 0.33
Nodes (6): Live gate (human-run, once, after full Revit restart), Phase Requirements -> Test Map, Sampling Rate, Test Framework, Validation Architecture, Wave 0 Gaps

### Community 499 - "05-07-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, The status contract (defined here; the live runner 05-11/05-12 reads these names), Trust Boundaries

### Community 500 - "05-08-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Share layout after this plan, STRIDE Threat Register, Trust Boundaries

### Community 501 - "Plan 05-10 Summary"
Cohesion: 0.33
Nodes (5): Delivered, Outcome, Plan 05-10 Summary, Release authority, Verification

### Community 502 - "05-11-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, The record contract (05-12 writes it; this plan judges it), Trust Boundaries

### Community 503 - "05-13-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Live rules (this plan, 05-14 and 05-15), Research assumptions this stage settles on the dev pyRevit, STRIDE Threat Register, Trust Boundaries

### Community 504 - "05-16-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries, What 05-01 left in place (read, do not change)

### Community 505 - "Validation Architecture"
Cohesion: 0.33
Nodes (6): Live acceptance procedure (restart-per-iteration, one-shot writes), Phase Requirements -> Test Map, Sampling Rate, Test Framework, Validation Architecture, Wave 0 Gaps

### Community 506 - "Phase 05 - Security"
Cohesion: 0.25
Nodes (7): Accepted Risks Log, Phase 05 - Security, Security Audit Trail, Sign-Off, Threat Register, Trust Boundaries, Unregistered Flags and Advisories (non-blocking, not counted in threats_open)

### Community 507 - "2026-10-26 — пилот Phase 7, live STOP из-за аудита"
Cohesion: 0.17
Nodes (12): 2026-10-26 — пилот Phase 7, live STOP из-за аудита, Live — выполнено пользователем на другом рабочем ПК, Где доказательства (НЕ на этом dev-ПК), Задание следующей сессии, Информация о сессии, Найденные замечания, Ограничения продолжения, Проверки при сохранении (+4 more)

### Community 508 - "Phase 06 — Validation Strategy"
Cohesion: 0.20
Nodes (9): Live gate results (plan 06-07, run 2026-10-25, Revit 2024), Manual-Only Verifications, Per-Task Verification Map, Phase 06 — Validation Strategy, Sampling Rate, Test Infrastructure, Validation Audit 2026-10-25, Validation Sign-Off (+1 more)

### Community 509 - "Многоэкземплярная приёмка — поочерёдный запуск, только stdio, стоп при перехвате чтения"
Cohesion: 0.18
Nodes (10): D-25. Стенд принимается по поочерёдному запуску, D-26. Две записи (`revit-a` / `revit-b`) — только через stdio, D-27. Если чтение перехватит мутацию — стоп и решение пользователя, Многоэкземплярная приёмка — поочерёдный запуск, только stdio, стоп при перехвате чтения, Связанное, Следствие для формулировок, Итог фазы 1, Обсуждение фазы 2 (+2 more)

### Community 511 - "fixture"
Cohesion: 0.18
Nodes (10): app(), close_then_replace(), fake_routes(), fixture, Two unsaved documents with the same presentation fields (Revit numbers new…, A/SAME.rvt and B/SAME.rvt: same file name and title, different folders., Close one of two same-title documents, then open a replacement with the…, registry() (+2 more)

### Community 512 - "Путь с кириллицей не открывался — виноваты бэкслеши, а не кодировка"
Cohesion: 0.22
Nodes (9): Доказательство, что кодировка ни при чём, Как исправлено, Причина — коллизия бэкслеша, а не юникод, Путь с кириллицей не открывался — виноваты бэкслеши, а не кодировка, Рабочие формы пути, Связанное, Симптом, Тот же класс бага уже кусал нас в инструментах (+1 more)

### Community 513 - "Сессия 2026-10-07: исполнение фазы 1, стенд двух Revit нашёл подмену ответов pyRevit, фаза остановлена на перепланирование"
Cohesion: 0.22
Nodes (9): Инструкция для проверяющего, Как исполнялось, Решения пользователя, Сессия 2026-10-07: исполнение фазы 1, стенд двух Revit нашёл подмену ответов pyRevit, фаза остановлена на перепланирование, Следующий шаг, Стенд (два Revit 2024.3.30, pyRevit 6.5.3), Хвосты, Цель (+1 more)

### Community 514 - "2026-10-24 — исполнение фазы 5, три живых стадии PHASE5_GATE_OK, верификация human_needed"
Cohesion: 0.16
Nodes (10): 2026-10-24 — исполнение фазы 5, три живых стадии PHASE5_GATE_OK, верификация human_needed, Как шло исполнение, Состояние после сессии, Хвост фазы, Что нашла живая проверка, 2026-10-25 — приёмка фазы 5, пять пунктов UAT пройдены, SECURITY.md 65 из 65, фаза закрыта, R3 пропущен, Дальше, Коммиты (+2 more)

### Community 515 - "failure"
Cohesion: 0.25
Nodes (8): failure(), (body, status) of the HTTP 403 answer for a refused permit; fixed text, never…, test_a_missing_permit_hint_names_the_update_in_both_languages(), test_a_replayed_permit_hint_asks_for_a_new_confirmation_window(), test_an_unknown_verdict_is_reported_as_malformed(), test_every_refusal_has_the_same_closed_body_and_says_nothing_was_changed(), test_not_configured_says_to_reinstall_and_restart_revit(), respond()

### Community 516 - "Сессия: открытие без отсоединения создаёт локальную копию, RSN-путь больше не зависит от журнала"
Cohesion: 0.25
Nodes (8): Изменённые файлы, Коммит, Проверки, Сессия: открытие без отсоединения создаёт локальную копию, RSN-путь больше не зависит от журнала, Суть работы, Что не готово, Что сделано, Что я открыл

### Community 517 - "_read_ast"
Cohesion: 0.25
Nodes (8): The scan is not vacuous: each banned shape is reported., Every open() in the two modules is rb, and there is at least one of each., _read_ast(), test_determinism_integrity_has_no_global_or_nonlocal_statement(), test_never_writes_ast_scan_detects_a_planted_violation(), test_never_writes_ast_scan_finds_no_write_call(), test_never_writes_open_modes_are_literal_rb(), _violations()

### Community 518 - "04-10-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 519 - "Phase 04 Plan 11: Live outcome gate Summary"
Cohesion: 0.40
Nodes (4): Deviations, Follow-ups for the operator, Observed, Phase 04 Plan 11: Live outcome gate Summary

### Community 520 - "Architecture Patterns"
Cohesion: 0.40
Nodes (5): Anti-Patterns to Avoid, Architecture Patterns, Pattern 1: migration shape (IronPython-3.4-safe, no f-strings), Recommended Project Structure, System Architecture Diagram

### Community 521 - "05-02-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Fan-out rules (same in 05-02..05-05), STRIDE Threat Register, Trust Boundaries

### Community 522 - "05-03-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Fan-out rules (same in 05-02..05-05), STRIDE Threat Register, Trust Boundaries

### Community 523 - "05-04-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Fan-out rules (same in 05-02..05-05), STRIDE Threat Register, Trust Boundaries

### Community 524 - "05-05-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Fan-out rules (same in 05-02..05-05), STRIDE Threat Register, Trust Boundaries

### Community 525 - "05-06-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 526 - "Plan 05-06 Summary"
Cohesion: 0.40
Nodes (4): Completed, Notes, Plan 05-06 Summary, Verification

### Community 527 - "05-09-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 528 - "05-10-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 529 - "Plan 05-11 Summary"
Cohesion: 0.40
Nodes (4): Completed, Notes, Plan 05-11 Summary, Verification

### Community 530 - "05-12-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 531 - "05-14-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Live rules, STRIDE Threat Register, Trust Boundaries

### Community 532 - "05-15-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Live rules, STRIDE Threat Register, Trust Boundaries

### Community 533 - "Code Examples"
Cohesion: 0.40
Nodes (5): Code Examples, Envelope in the bridge (before `_dispatch`), `security.py` core (gate and strip), Sentinel skeleton (extends `inventory_support`), Staged publish skeleton (CRLF, ASCII only in the real file)

### Community 534 - "mep_tools.py"
Cohesion: 0.29
Nodes (10): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, MEP tools — ducts, pipes, and mechanical/plumbing systems, Register MEP tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_mep_tools(), create_duct(), create_mep_system() (+2 more)

### Community 535 - "04-11-PLAN.md"
Cohesion: 0.50
Nodes (3): Artifacts this phase produces (this plan), STRIDE Threat Register, Trust Boundaries

### Community 536 - "Code Examples"
Cohesion: 0.50
Nodes (4): Code Examples, format_response partial branch (tools/utils.py, inside `_project_response`, before the success `message` pick), Pure helpers (textutils.py; no f-strings; 3.4-level syntax), Static check (scripts/conventions.py, D-02)

### Community 537 - "Sources"
Cohesion: 0.50
Nodes (4): Primary (HIGH confidence) - read this session, Secondary (MEDIUM confidence), Sources, Tertiary (LOW confidence)

### Community 538 - "Standard Stack"
Cohesion: 0.50
Nodes (4): Alternatives Considered, Core, Standard Stack, Supporting

### Community 539 - "Sources"
Cohesion: 0.50
Nodes (4): Primary (HIGH confidence) - read this session, Secondary (MEDIUM/LOW confidence), Sources, Tertiary (LOW confidence)

### Community 540 - "_load_module"
Cohesion: 0.50
Nodes (4): _load_module(), test_contributor_kit_scaffold_is_convention_clean(), test_new_tool_get_scaffold_is_ungated_and_convention_clean(), test_new_tool_post_scaffold_is_gated_and_convention_clean()

### Community 541 - "_swallower_hits"
Cohesion: 0.50
Nodes (4): _swallower_hits(), test_swallower_detector_catches_a_commit_without_a_swallower(), test_swallower_detector_catches_a_discarded_suppress_warnings(), test_swallower_detector_ignores_the_good_forms_and_mentions()

### Community 542 - "Standard Stack"
Cohesion: 0.67
Nodes (3): Alternatives Considered, Core, Standard Stack

### Community 543 - "Security Domain"
Cohesion: 0.67
Nodes (3): Applicable ASVS Categories, Known Threat Patterns, Security Domain

### Community 544 - "Security Domain"
Cohesion: 0.67
Nodes (3): Applicable ASVS Categories, Known Threat Patterns for this stack, Security Domain

### Community 545 - "permit.py"
Cohesion: 0.12
Nodes (22): args_hash(), args_text(), derive_key(), mac_message(), mint(), One-time permits for confirmed and allowed mutations, and the envelope-first…, The exact JSON object text of a request body (compact, pure ASCII), refusing…, SHA-256 hex of the argument text (ASCII by construction). (+14 more)

### Community 546 - "FakeWall"
Cohesion: 0.17
Nodes (5): get_element(), FakeCurve, FakeWall, An element GetElement or a collector answers for the annotation routes: a wall…, XYZ

### Community 547 - "test_secret_pipeline.py"
Cohesion: 0.10
Nodes (14): _assert_py38_clean(), _claude_md(), _gate_ast(), _gitignore_lines(), skipif, Build-side secret tooling: deploy/secret_tool.py, scripts/dev_secret.py, ignore…, test_claude_md_documents_the_secret_and_manifest_pipeline(), test_claude_md_names_both_shared_helpers() (+6 more)

### Community 554 - "cmd.exe читает config.cmd в консольной кодовой странице, не в UTF-8 файла"
Cohesion: 0.29
Nodes (7): cmd.exe читает config.cmd в консольной кодовой странице, не в UTF-8 файла, Дополнение 2026-10-26 — CP65001 и LF в локальных scratch-тестах, Обход, Причина, Связанное, Симптом, Урок

### Community 556 - "Исполнение фазы 7 — шесть планов завершены"
Cohesion: 0.29
Nodes (7): Исполнение фазы 7 — шесть планов завершены, Окружение — важно перед любым uv, Проверки, Рабочее дерево и сохранение, Связи, Точка продолжения, Что сделано

### Community 557 - "mcp 1.11+ импортирует pywin32, а embeddable CPython payload его не находит"
Cohesion: 0.33
Nodes (5): mcp 1.11+ импортирует pywin32, а embeddable CPython payload его не находит, Обход, Причина, Симптом, Урок

### Community 558 - "FakeChild"
Cohesion: 0.25
Nodes (4): ExplodingBridge, FakeChild, object, Any use at all fails the test: a refusal must come before the bridge is touched.

### Community 559 - "Гейт холодного старта мерил SMB-задержку шары, а не старт сервера"
Cohesion: 0.33
Nodes (6): Гейт холодного старта мерил SMB-задержку шары, а не старт сервера, Обход / исправление, Причина, Связанное, Симптом, Урок

### Community 560 - "pyRevit Reload при включённых Routes валит Revit на первом же запросе"
Cohesion: 0.33
Nodes (6): pyRevit Reload при включённых Routes валит Revit на первом же запросе, Обход, Причина, Связанное, Симптом, Урок

### Community 561 - "Phase 7 Plan 08 Summary"
Cohesion: 0.29
Nodes (6): Changes, Constraints observed, Follow-up, Outcome, Phase 7 Plan 08 Summary, Verification

### Community 562 - "2026-10-25 — быстрая задача open_model, локальная копия по умолчанию, штамп вместо удаления, запасной набор «Оси и уровни»"
Cohesion: 0.29
Nodes (7): 2026-10-25 — быстрая задача open_model, локальная копия по умолчанию, штамп вместо удаления, запасной набор «Оси и уровни», Дальше, Коммиты, Оговорки, Проверено, Связано, Что сделано

### Community 563 - "FopError"
Cohesion: 0.21
Nodes (13): fop_for(), FopError, FopIndex, match_shared(), parse_fop_bytes(), ValueError, The company shared-parameter source could not be established., Strict BOM-based decoding and tab-separated Revit PARAM records; no guessed… (+5 more)

### Community 564 - "2026-10-23 — исполнение фазы 4, живой шлюз PHASE4_OUTCOMES_OK, фаза закрыта, R2 пропущен"
Cohesion: 0.33
Nodes (6): 2026-10-23 — исполнение фазы 4, живой шлюз PHASE4_OUTCOMES_OK, фаза закрыта, R2 пропущен, Живой шлюз (04-11), Как шло исполнение, Открытое, Решения и уроки процесса, Хвост фазы

### Community 565 - "Общие параметры определяются по префиксу ForgeTypeId, а не по типу Definition"
Cohesion: 0.29
Nodes (7): Как проверено, Общие параметры определяются по префиксу ForgeTypeId, а не по типу Definition, Ограничения (задокументированы в докстринге инструмента), Почему не так, как казалось очевидным, Решение, Связанное, Форма ответа инструмента

### Community 568 - "Паттерн регистратора инструментов с инъекцией транспорта"
Cohesion: 0.29
Nodes (7): Асимметрия сигнатур, Логирование через контекст, Обязательные элементы, Параметры инструмента, Паттерн регистратора инструментов с инъекцией транспорта, Связанное, Форма

### Community 569 - "Открытие центральной без отсоединения шло мимо CreateNewLocal"
Cohesion: 0.33
Nodes (6): Механизм, Открытие центральной без отсоединения шло мимо CreateNewLocal, Почему не заметили раньше, Проверка, Решение, Симптом

### Community 570 - "Пересекающиеся запросы pyRevit получают чужой ответ, а их код не выполняется"
Cohesion: 0.33
Nodes (6): Как измерено, Пересекающиеся запросы pyRevit получают чужой ответ, а их код не выполняется, Причина, Связанное, Симптом, Чем опасно

### Community 571 - "reply_for"
Cohesion: 0.33
Nodes (7): reply_for(), test_audit_id_of_reads_the_last_line_id_or_none(), test_run_single_calls_each_write_once_in_order_even_when_the_second_raises(), callable_for(), call(), test_tool_step_stores_the_reply_text_of_a_successful_call(), call()

### Community 572 - "06-03-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumption (edge probe, unresolved), STRIDE Threat Register, Trust Boundaries

### Community 573 - "06-05-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (carried, not dropped), STRIDE Threat Register, Trust Boundaries

### Community 574 - "bench"
Cohesion: 0.25
Nodes (8): acc_dir(), bench(), fixture, test_classify_cli_uses_only_synthetic_secret(), test_local_policy_store_uses_only_scratch_files(), test_network_operator_pointer_is_refused_before_target_open(), test_offline_report_is_versioned_immutable_and_never_uses_transport(), test_offline_report_without_configured_secret_is_stop()

### Community 575 - "_Categories"
Cohesion: 0.20
Nodes (5): _Categories, line_styles(), doc.Settings.Categories: get_Item answers the Lines category; iterating yields…, doc.Settings.Categories answers an Lines category with the given sub-categories., _SubCategory

### Community 576 - "Machine"
Cohesion: 0.12
Nodes (10): anyio_backend(), counting_machine(), CountingMachine, Gate, Machine, fixture, object, Requested (non-status) routes, as (port, method, path). (+2 more)

### Community 577 - "Phase 7 Plan 13 Summary"
Cohesion: 0.29
Nodes (6): Changes, Deviations and evidence limits, Next, Outcome, Phase 7 Plan 13 Summary, Verification

### Community 578 - "register_colors_tools"
Cohesion: 0.31
Nodes (9): _blank_document(), Transport keyword for the per-call process selector; absent when not given., True for a document selector that was given but is not a usable string. A blank…, Register color tools with the MCP server., register_colors_tools(), clear_colors(), color_splash(), list_category_parameters() (+1 more)

### Community 579 - "Phase 7 Plan 10 Summary"
Cohesion: 0.25
Nodes (7): Changes, Commits, Deviations and remaining evidence, Next, Outcome, Phase 7 Plan 10 Summary, Verification

### Community 580 - "register_family_tools"
Cohesion: 0.24
Nodes (12): _blank_document(), Transport keyword for the per-call process selector; absent when not given., True for a document selector that was given but is not a usable string. A blank…, Family and placement tools, Register family-related tools, register_family_tools(), edit_family(), list_families() (+4 more)

### Community 581 - "Маршруты pyRevit без аргументов uiapp, uidoc, doc выполняются вне контекста Revit API"
Cohesion: 0.33
Nodes (6): Исправление, Маршруты pyRevit без аргументов uiapp, uidoc, doc выполняются вне контекста Revit API, Правило, Причина, Симптом, Что не помогло

### Community 582 - "Сессия 2026-09-06 — план и реализация деплоя в контур компании, инструмент запуска Revit"
Cohesion: 0.33
Nodes (6): Запрос, Изменённые файлы (эта сессия), Не сделано / открыто, Проверено вживую, Сессия 2026-09-06 — план и реализация деплоя в контур компании, инструмент запуска Revit, Что сделано

### Community 583 - "2026-09-07 — правка заголовка страницы Confluence через Kiwi Web Bridge, диагностика конфликта порта webbridge"
Cohesion: 0.33
Nodes (6): 2026-09-07 — правка заголовка страницы Confluence через Kiwi Web Bridge, диагностика конфликта порта webbridge, Контекст задачи, Не закрыто, Результат, Связанное, Что пошло не так и как обошли

### Community 584 - "detail_tools.py"
Cohesion: 0.28
Nodes (8): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, Detail tools — detail lines for view-specific annotation, Register detail tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_detail_tools(), create_detail_line(), _target_options()

### Community 585 - "Сессия: журнал Revit Server закреплён на обязательном UNC-пути"
Cohesion: 0.33
Nodes (6): Важно, Изменённые файлы, Информация о сессии, Проверка, Результаты, Сессия: журнал Revit Server закреплён на обязательном UNC-пути

### Community 586 - "Продукт — это мост между ИИ-ассистентом и Autodesk Revit"
Cohesion: 0.25
Nodes (8): Границы продукта, Продукт — это мост между ИИ-ассистентом и Autodesk Revit, Связанное, Флагманская возможность, Ценностное предложение, Что делает это реальным продуктом, а не демо, Что продаётся (точнее — раздаётся), Что честно назвать незрелым

### Community 587 - "classify_dual"
Cohesion: 0.40
Nodes (6): _classify(), classify_dual(), classify_single(), Judge a run-single record (ROADMAP criteria 1, 2 and 7): {"verdict":…, Judge a run-dual record (ROADMAP criterion 5): {"verdict": "ok"|"stop",…, _verdict_of()

### Community 588 - "record_secret_occurrences"
Cohesion: 0.33
Nodes (6): How often the secret shows in ``data`` (bytes): whole, JSON-escaped, or as a…, Everything the gate keeps or prints for a record: audit lines, replies and the…, The occurrence count the classifiers and the report use; 0 when it cannot be…, _record_bytes(), record_secret_occurrences(), secret_occurrences()

### Community 589 - "06-01-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 590 - "06-02-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 591 - "06-04-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 592 - "06-06-PLAN.md"
Cohesion: 0.40
Nodes (4): Artifacts this phase produces (this plan), Execution rules for every task in this plan, STRIDE Threat Register, Trust Boundaries

### Community 593 - "Validation Architecture"
Cohesion: 0.40
Nodes (5): Phase Requirements -> Test Map, Sampling Rate, Test Framework, Validation Architecture, Wave 0 Gaps

### Community 595 - "Регистрация — автообнаружение вместо рукописных списков"
Cohesion: 0.33
Nodes (6): Побочный эффект, Почему это стало безопасно сделать, Регистрация — автообнаружение вместо рукописных списков, Решение, Связанное, Что это даёт при нескольких разработчиках

### Community 596 - "_build_parser"
Cohesion: 0.40
Nodes (4): _build_parser(), _Parser, Exception, _UsageError

### Community 597 - "Goal Achievement"
Cohesion: 0.11
Nodes (17): 1. Criterion 3 on offline evidence, 2. AUDIT-05 and AUDIT-06 edge probes, 3. user_request compliance by the model, 4. Accept or fix WR-01 to WR-03 before the R4 release checkpoint, Anti-Patterns Found, Behavioral Spot-Checks, Data-Flow Trace (Level 4), Gaps Summary (+9 more)

### Community 598 - "06-07-PLAN.md"
Cohesion: 0.50
Nodes (3): Artifacts this phase produces (this plan), STRIDE Threat Register, Trust Boundaries

### Community 599 - "Standard Stack"
Cohesion: 0.50
Nodes (4): Alternatives Considered, Core, Standard Stack, Supporting

### Community 600 - "Sources"
Cohesion: 0.50
Nodes (4): Primary (HIGH confidence), Secondary (MEDIUM confidence), Sources, Tertiary (LOW confidence)

### Community 601 - "test_permit_concurrency.py"
Cohesion: 0.24
Nodes (17): check(), _fresh_registry(), mint(), fixture, race(), one(), Phase 7 (07-05): a permit is consumed exactly once, however many callers race…, Run one check per entry of ``raws`` on its own thread, all released together. (+9 more)

### Community 602 - "Common Pitfalls"
Cohesion: 0.12
Nodes (17): Common Pitfalls, Pitfall 10: `secrets` module does not exist in IronPython, Pitfall 11: Existing tests build requests without a path or permit, Pitfall 12: A permit is burned by a later document refusal, Pitfall 13: `set_parameter` writes raw internal units, Pitfall 14: Hermes shows `message` through secret redaction, Pitfall 15: Operator file edited in place is read half-written, Pitfall 16: Window text spoofing by model-controlled strings (+9 more)

### Community 603 - "_rehearsal_verdict"
Cohesion: 0.50
Nodes (4): parse_audit_files(), ("ROLLED_BACK" | "COMMITTED" | "OTHER", the audit entry of the call or None)., (entries, bad_lines, crlf_files) of {file name: [raw lines]}. entries are (file…, _rehearsal_verdict()

### Community 604 - "Phase 6 Plan 06: The human-run live audit gate Summary"
Cohesion: 0.12
Nodes (15): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Limitations (+7 more)

### Community 605 - "Security Domain"
Cohesion: 0.67
Nodes (3): Applicable ASVS Categories, Known Threat Patterns for this stack, Security Domain

### Community 606 - "Code Examples"
Cohesion: 0.67
Nodes (3): Code Examples, Fake Revit server (verified harness skeleton), Provenance -> `Audit:` line

### Community 607 - "Phase 7 Plan 01: MCP SDK upgrade to 1.30 Summary"
Cohesion: 0.12
Nodes (15): Accomplishments, Auto-fixed Issues, Checkpoint record (Task 2, blocking-human), Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs (+7 more)

### Community 608 - "Phase 7: Repository-owned mutation safety and human approval - Research"
Cohesion: 0.12
Nodes (15): Architectural Responsibility Map, Assumptions Log, Don't Hand-Roll, Environment Availability, Metadata, Open Questions, Package Legitimacy Audit, Phase 7: Repository-owned mutation safety and human approval - Research (+7 more)

### Community 609 - "Паттерн обработчика маршрута — валидация, транзакция, сериализация.md"
Cohesion: 0.03
Nodes (78): get_revit_model_info показывал данные под ложным заголовком ошибки, Исправление, Причина, Регрессионный тест, Связанное, Симптом, Урок, tag_walls молча пропускал стены и возвращал отмечено 0 (+70 more)

### Community 610 - "Phase 7 Plan 02: Confirm-class tracer through policy, window, permit and Revit verifier Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness (+6 more)

### Community 611 - "Phase 7 Plan 04: Two-layer policy (base + operator) with hot reload and build staging Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness (+6 more)

### Community 612 - "Phase 7 Plan 05: Permit protocol hardening Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness (+6 more)

### Community 613 - "Phase 07 Plan 07: Permit-ready unit request plumbing Summary"
Cohesion: 0.13
Nodes (14): Accomplishments, Auto-fixed Issues, Decisions Made, Deviations from Plan, Files Created/Modified, Issues Encountered, Known Stubs, Next Phase Readiness (+6 more)

### Community 614 - "User Constraints (from CONTEXT.md)"
Cohesion: 0.15
Nodes (13): Claude's Discretion, Confirmed User Constraints (2026-10-16), Deferred Ideas (OUT OF SCOPE), Existing Decisions That Remain Binding, Locked Decisions, Not Authorized / Out of Scope, Revit-сторона и выкладка (2026-10-25), User Constraints (from CONTEXT.md) (+5 more)

### Community 615 - "decide"
Cohesion: 0.23
Nodes (12): decide(), Decision, _deduplicated(), _family_edit_decision(), _parameter_write_decision(), The rule of a route key such as "/delete_elements/", or None when it is…, Words in their input order, without repeats., D-10: permit only a single empty instance parameter write on a safe element. (+4 more)

### Community 616 - "_process_token"
Cohesion: 0.50
Nodes (5): process_token(), The initialized process token as text, or None when it cannot be read; never…, _process_token(), The current Revit process token for permit verification, or None; never raises., test_process_token_is_none_under_cpython_and_security_delegates()

### Community 617 - "scratch_payload_gate.py"
Cohesion: 0.32
Nodes (12): app_files(), check_dest(), echo(), fail(), find_pyexe(), fresh_dir(), interpreter_version(), main() (+4 more)

### Community 618 - "test_process_identity.py"
Cohesion: 0.19
Nodes (8): load_identity(), parametrize, Exercise the extension helper with CLR/pyRevit doubles, never live Revit., test_actual_status_handler_exposes_identity_without_document(), route(), test_getter_never_lazily_creates_startup_identity(), test_missing_bound_port_does_not_invent_default(), test_startup_is_once_and_actual_port_comes_from_retained_server()

### Community 619 - "Info"
Cohesion: 0.17
Nodes (11): IN-01: A JSON-looking user_request is not stored verbatim, IN-02: Arguments are held by reference and shaped at call end, IN-03: prune() can delete another live server's active segment on POSIX, IN-04: Small cleanups, Info, Phase 6: Code Review Report, Summary, Warnings (+3 more)

### Community 620 - "Phase 7 Plan 03: Payload pywin32 shim and transport proof Summary"
Cohesion: 0.17
Nodes (11): Accomplishments, Auto-fixed Issues, Deviations from Plan, Issues Encountered, Known Stubs, Next Phase Readiness, Phase 7 Plan 03: Payload pywin32 shim and transport proof Summary, Self-Check: PASSED (+3 more)

### Community 621 - "Сессия 2026-10-06/07: планирование фазы 1 — сериализация и `REVIT_PORT` разбиты на пять планов"
Cohesion: 0.33
Nodes (6): Отступления планировщика (checker счёл все обоснованными), Сессия 2026-10-06/07: планирование фазы 1 — сериализация и `REVIT_PORT` разбиты на пять планов, Следующий шаг, Хвосты, Цель, Что сделано

### Community 622 - "Аудитория — BIM-инженеры на Windows с Revit и pyRevit"
Cohesion: 0.29
Nodes (7): Аудитория — BIM-инженеры на Windows с Revit и pyRevit, Кто НЕ аудитория, Портрет пользователя, Практические сценарии, на которые он рассчитан, Связанное, Технический барьер входа, Требования к рабочему месту

### Community 623 - "policy_tool.py"
Cohesion: 0.25
Nodes (10): _build_parser(), check_policy_file(), main(), PolicyToolError, Exception, r"""Build-time operator-policy tool: stage the path of the operator file, and…, The staging could not be done., Write ``policy_file`` and one LF to ``dest`` as UTF-8 without a byte order mark. (+2 more)

### Community 624 - "Gate-by-Gate Answers (from the orchestrator's research priorities)"
Cohesion: 0.18
Nodes (11): Gate 10 - Hook point, Gate 1 - MCP SDK upgrade (D-06), Gate 2 - Unchanged HermesFork elicitation handler (read-only), Gate 3 - Permit scheme (D-18), Gate 4 - Preflight read-only facts (D-09/D-10), Gate 5 - Complete classification (D-10..D-13, D-22, D-23), Gate 6 - D-22 shared parameters from the company FOP, Gate 7 - D-23 operations that redefine an existing parameter (+3 more)

### Community 625 - "Phase quick-261025-ld5 Plan 01: open_model defaults to a local copy Summary"
Cohesion: 0.18
Nodes (10): Decisions, Deviations from Plan, Known Stubs, Phase quick-261025-ld5 Plan 01: open_model defaults to a local copy Summary, Reply fields (workshared path only), Self-Check: PASSED, Test results, Threat Flags (+2 more)

### Community 626 - "Принят checkpoint 02-20 и реализован selected status 02-01"
Cohesion: 0.33
Nodes (6): Модель, Принят checkpoint 02-20 и реализован selected status 02-01, Проверки, Результаты, Решения и ограничения, Точка продолжения

### Community 627 - "fill"
Cohesion: 0.27
Nodes (11): fill(), _mismatch_naming(), _one_open_document(), Substitute this test's scratch directory into a body., _refused(), test_a_validation_error_after_the_guard_is_attributed_too(), test_suppress_warnings_comes_immediately_after_start(), test_with_a_wrong_secret_a_mutation_is_401_before_any_side_effect() (+3 more)

### Community 628 - "refuses"
Cohesion: 0.18
Nodes (6): test_a_failed_save_as_names_the_document_with_the_path_it_still_has(), test_a_save_as_that_raises_names_the_requested_path_as_the_failed_item(), test_a_save_that_raises_is_a_500_with_the_document_path_as_the_failed_item(), refuses(), test_load_family_that_raises_is_a_500_naming_the_file(), test_place_family_names_an_unsupported_parameter_type_and_a_set_that_raises()

### Community 629 - "Tests"
Cohesion: 0.22
Nodes (8): 1. Criterion 3 on offline evidence, 2. AUDIT-05 and AUDIT-06 edge probes, 3. user_request compliance by the model, 4. Review warnings WR-01..WR-03 (lone surrogate drops an entry; failed read audited as success; NaN/Infinity in the log), Current Test, Gaps, Summary, Tests

### Community 630 - "Architecture Patterns"
Cohesion: 0.22
Nodes (9): Anti-Patterns to Avoid, Architecture Patterns, Pattern 1: Single choke point in `bridge.revit_post`, fail closed, Pattern 2: Decision flow with human wait outside the lock, Pattern 3: Stateless permit, verified and consumed in `gate_or_response`, Pattern 4: Colocated read-only preflight routes, Pattern 5: Policy engine data model (TOML, closed vocabulary), Recommended Project Structure (new and changed files) (+1 more)

### Community 631 - "Phase 06 — Security"
Cohesion: 0.25
Nodes (7): Accepted Risks Log, Phase 06 — Security, Security Audit 2026-10-25, Security Audit Trail, Sign-Off, Threat Register, Trust Boundaries

### Community 632 - "Phase 7: Repository-owned mutation safety and human approval - Discussion Log"
Cohesion: 0.25
Nodes (7): Claude's Discretion, Deferred Ideas, Phase 7: Repository-owned mutation safety and human approval - Discussion Log, Revit-сторона и выкладка, Канал подтверждения, Политика: файл и владелец, Что подтверждать

### Community 633 - "Phase 7 — Validation Strategy"
Cohesion: 0.20
Nodes (9): 07-14 Task 1 — final-tree offline evidence (2026-10-26), Live bench (D-20), Manual-Only Verifications, Per-Task Verification Map, Phase 7 — Validation Strategy, Sampling Rate, Test Infrastructure, Validation Sign-Off (+1 more)

### Community 634 - "Phase 7 Plan 06: Complete policy inventory and decisions Summary"
Cohesion: 0.29
Nodes (6): Accomplishments, Deviations and Notes, Next Phase Readiness, Phase 7 Plan 06: Complete policy inventory and decisions Summary, Task Commits, Verification

### Community 635 - "_send"
Cohesion: 0.15
Nodes (14): AsyncClient, The one HTTP send. Does no locking; callers decide. A POST ``data`` that is…, read(), write(), _send(), anyio, test_send_posts_exactly_json_dumps_of_the_body_it_is_given(), anyio (+6 more)

### Community 636 - "Цены нет — проект под лицензией MIT"
Cohesion: 0.29
Nodes (7): Модель распространения, Пробел в знании, Родословная проекта, Связанное, Стоимость для пользователя, Цены нет — проект под лицензией MIT, Что это означает для планирования

### Community 637 - "07-02-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), Interfaces this plan creates (later plans build on these names; keep them stable), STRIDE Threat Register, Trust Boundaries

### Community 638 - "07-04-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), Interfaces this plan adds to policy.py, STRIDE Threat Register, Trust Boundaries

### Community 639 - "07-06-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Facts contract `decide` reads (produced by /mutation_preflight/ in 07-10; absent keys mean unknown), Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 640 - "07-12-PLAN.md"
Cohesion: 0.29
Nodes (6): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, The pinned sentences (verbatim; one line each in every listed file), Trust Boundaries

### Community 641 - "clash_tools.py"
Cohesion: 0.29
Nodes (7): Strict 1:1 domain mirroring pattern, Register clash detection tools with the MCP server., Clash detection tools — hard interference checking for BIM coordination, Transport keyword for the per-call process selector; absent when not given., register_clash_tools(), check_clashes(), _target_options()

### Community 642 - "parametrize"
Cohesion: 0.24
Nodes (11): parametrize, test_audit_must_prove_same_request_and_fractional_arguments(), test_audit_refusal_contracts(), test_direct_bad_arguments_refuse_without_transport(), test_h4_identical_requests_and_distinct_call_ids_remain_required_with_preflights(), test_malformed_audit_rows_still_stop_with_valid_target_rows(), test_negative_record_contracts(), test_preflight_success_does_not_mask_final_decision_approval_or_outcome() (+3 more)

### Community 643 - "Разработчики инструментов работают без доступа к репозиторию"
Cohesion: 0.29
Nodes (7): Почему это стало возможно только сейчас, Проверено, Разработчики инструментов работают без доступа к репозиторию, Решение, Связанное, Три компонента, Явный предел автоматики

### Community 645 - "Стек делится на CPython 3.11+ и IronPython 2.7"
Cohesion: 0.25
Nodes (8): Конфигурация, Пакетный менеджер, Рантайм, Связанное, Стек делится на CPython 3.11+ и IronPython 2.7, Требования к платформе, Фреймворки, Языки

### Community 646 - "room_tools.py"
Cohesion: 0.29
Nodes (9): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, Room creation tools — rooms and room separation lines, Register room tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_room_tools(), create_room(), create_room_separation() (+1 more)

### Community 647 - "test_outcome_docstrings.py"
Cohesion: 0.33
Nodes (3): parametrize, The mutation tools' docstrings state the outcome statuses their routes can…, test_docstring_states_what_the_route_can_return_and_nothing_else()

### Community 648 - "CLAUDE.md Contributor Guide"
Cohesion: 0.25
Nodes (6): graphify knowledge graph integration workflow, CLAUDE.md Contributor Guide, MCP Server Runtime (CPython >=3.11), Obsidian Knowledge Vault session workflow, Revit Extension Runtime (IronPython 2.7), The Two-Runtime Rule

### Community 649 - "Bench фазы 7 — preflight и итог операции имеют общий call_id"
Cohesion: 0.40
Nodes (5): Bench фазы 7 — preflight и итог операции имеют общий call_id, Другие замечания той же приёмки, Измерение на рабочем ПК, Причина в коде, Требуемое исправление (ещё не сделано)

### Community 650 - "Phase 06 Plan 07: Live audit gate Summary"
Cohesion: 0.33
Nodes (5): Accomplishments, Deviations, Limitations, Phase 06 Plan 07: Live audit gate Summary, Self-Check: PASSED

### Community 651 - "07-01-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 652 - "07-03-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 653 - "07-05-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 654 - "07-07-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 655 - "07-08-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 656 - "07-09-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 657 - "07-10-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 658 - "07-11-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 659 - "07-13-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 660 - "07-14-PLAN.md"
Cohesion: 0.33
Nodes (5): Artifacts this phase produces (this plan), Execution rules for every task in this plan, Flagged assumptions (spec-less probe fallback), STRIDE Threat Register, Trust Boundaries

### Community 661 - "Строки из Revit прогоняются через sanitize_string"
Cohesion: 0.33
Nodes (6): Как применять сейчас, Но обоснование в докстринге неверно, Паттерн, как он был реализован (до фикса), Связанное, Строки из Revit прогоняются через sanitize_string, Урок паттерна

### Community 662 - "Bench фазы 7 — отсутствие audit и неверный ответ уровней давали ложное доказательство"
Cohesion: 0.40
Nodes (5): Bench фазы 7 — отсутствие audit и неверный ответ уровней давали ложное доказательство, Исправление, Причина, Проверка и пределы, Симптом

### Community 663 - "Сессия 2026-10-07: перепланирование фазы 1 после d27-b — три gap-плана вместо 01-05"
Cohesion: 0.29
Nodes (7): Решения пользователя в этой сессии, Связанные заметки, Сессия 2026-10-07: перепланирование фазы 1 после d27-b — три gap-плана вместо 01-05, Следующий шаг, Цель, Что сделано, Что стоит помнить

### Community 664 - "format_response прячет поля ответа за ключом message"
Cohesion: 0.40
Nodes (5): format_response прячет поля ответа за ключом message, Причина, Симптом, Урок, Фикс

### Community 665 - "2026-09-04 — настройка окружения, восстановление Routes после сбоя, находка бага с кириллицей"
Cohesion: 0.40
Nodes (5): 2026-09-04 — настройка окружения, восстановление Routes после сбоя, находка бага с кириллицей, Открытые вопросы / следующие шаги, Связанное, Текущее состояние окружения, Что сделано

### Community 666 - "Планирование фазы 7: четырнадцать планов в девять волн, SDK 1.30, требования SAFE-01..21"
Cohesion: 0.33
Nodes (5): Отладка, Планирование фазы 7: четырнадцать планов в девять волн, SDK 1.30, требования SAFE-01..21, Результаты, Решения, Что остаётся

### Community 667 - "Validation Architecture"
Cohesion: 0.40
Nodes (5): Phase Requirements -> Test Map, Sampling Rate, Test Framework, Validation Architecture, Wave 0 Gaps

### Community 668 - "261025-ld5-PLAN.md"
Cohesion: 0.40
Nodes (4): Design decisions (record each one in SUMMARY.md under "Decisions", with the justification), Executor ground rules (MANDATORY, read before Task 1), STRIDE Threat Register, Trust Boundaries

### Community 669 - "get_revit_process_status различает Revit закрыт от Revit без документа"
Cohesion: 0.40
Nodes (5): get_revit_process_status различает Revit закрыт от Revit без документа, Причина, Симптом, Урок, Фикс

### Community 670 - "Phase 7 Plan 09 Summary"
Cohesion: 0.25
Nodes (7): Changes, Commits, Constraints observed, Follow-up, Outcome, Phase 7 Plan 09 Summary, Verification

### Community 671 - "HermesCallback"
Cohesion: 0.40
Nodes (3): HermesCallback, object, Elicitation callback shaped like the Hermes handler: consent is the action only.

### Community 672 - "tag_tools.py"
Cohesion: 0.28
Nodes (8): _blank_document(), True for a document selector that was given but is not a usable string. A blank…, Tagging tools — tag elements with annotation symbols, Register tag tools with the MCP server., Transport keyword for the per-call process selector; absent when not given., register_tag_tools(), tag_elements(), _target_options()

### Community 673 - "Standard Stack"
Cohesion: 0.50
Nodes (4): Alternatives Considered, Core, Standard Stack, Supporting

### Community 674 - "Code Examples"
Cohesion: 0.50
Nodes (4): Code Examples, Guard-test skeleton (derives from the AST inventory), Hot reload loader (CPython), Revit-side verification skeleton (IronPython 3.4 dialect)

### Community 675 - "Sources"
Cohesion: 0.50
Nodes (4): Primary (HIGH confidence), Secondary (MEDIUM confidence), Sources, Tertiary (LOW confidence)

### Community 676 - "operator_path"
Cohesion: 0.50
Nodes (3): operator_path(), Where the operator policy lives (D-27): REVIT_MCP_POLICY_FILE, else the first…, Worker thread: (path, first read, second read), or (None, None, None) when no…

### Community 677 - "open_model по умолчанию создаёт локальную копию, существующую переименовывает со штампом"
Cohesion: 0.40
Nodes (5): open_model по умолчанию создаёт локальную копию, существующую переименовывает со штампом, Обоснование, Принятые уточнения, Решение, Связано

### Community 678 - "2026-10-26 — 07-13 bench проверен офлайн, продолжить с 07-14"
Cohesion: 0.25
Nodes (8): 2026-10-26 — 07-13 bench проверен офлайн, продолжить с 07-14, Запрос и границы, Изменённые файлы этой сессии, Информация о сессии, Коммиты и рабочее дерево, Проверки, Результаты, Следующий шаг

### Community 679 - "Деплой в контур — сервер раздаёт файлы, оба процесса живут на станции"
Cohesion: 0.40
Nodes (5): Архитектура доставки, Деплой в контур — сервер раздаёт файлы, оба процесса живут на станции, Ключевой пересмотр решения: не свой Python, а Python из pyRevit, Находки в процессе, не связанные напрямую с целью, Решение

### Community 680 - "Защита операций Revit принадлежит MCP-репозиторию, не Hermes Fork"
Cohesion: 0.40
Nodes (5): Защита операций Revit принадлежит MCP-репозиторию, не Hermes Fork, Материалы, Направление для планирования, Решение пользователя, Что ещё не доказано

### Community 681 - "tag_walls_call"
Cohesion: 0.17
Nodes (13): _Item, _named(), A collector result: a named element with the few members the routes read., An existing wall tag that points at the wall with id ``target``., _tag(), tag_walls_call(), tag_walls_world(), test_tag_walls_where_every_attempted_wall_fails_is_a_422() (+5 more)

### Community 682 - "Фаза 7 — preflight закрепляет документ, повторная проверка фактов и ФОП отменяет устаревшее согласие"
Cohesion: 0.40
Nodes (5): Границы доказанного, Контракт, Почему, Связанное, Фаза 7 — preflight закрепляет документ, повторная проверка фактов и ФОП отменяет устаревшее согласие

### Community 683 - "_resolve_port"
Cohesion: 0.50
Nodes (5): Strictly parse REVIT_PORT. None (variable unset) is the default. Anything else…, _resolve_port(), parametrize, test_port_accepts(), test_port_refuses()

### Community 684 - "Revit MCP — индекс"
Cohesion: 0.40
Nodes (4): Revit MCP — индекс, Отладка, Рабочие заметки, Сессии

### Community 686 - "netstat на ru-RU Windows печатает заголовки в cp866, строгий парсер возвращал None"
Cohesion: 0.50
Nodes (4): netstat на ru-RU Windows печатает заголовки в cp866, строгий парсер возвращал None, Исправление, Причина, Симптом

### Community 687 - "Threat Model and Security Domain (ASVS L1, block on high)"
Cohesion: 0.67
Nodes (3): Applicable ASVS categories, Known threat patterns, Threat Model and Security Domain (ASVS L1, block on high)

### Community 688 - "Общая venv повреждена при обновлении SDK из-за работающих MCP-сессий"
Cohesion: 0.50
Nodes (4): Общая venv повреждена при обновлении SDK из-за работающих MCP-сессий, Ограничения восстановления, Проверенный обход, Симптом и причина

### Community 689 - "start_revit — единственная пара инструментов без Revit-стороны"
Cohesion: 0.50
Nodes (4): start_revit — единственная пара инструментов без Revit-стороны, Не проверено вживую, Особенности реализации, Решение

### Community 690 - "Исполнители фазы 2 идут последовательно в основном дереве, коммиты по путям"
Cohesion: 0.50
Nodes (4): Исполнители фазы 2 идут последовательно в основном дереве, коммиты по путям, Почему, Решение, Следствия

### Community 691 - "Перепланирование фазы 1 — новые gap-планы вместо переписывания 01-05, d27-c в бэклог"
Cohesion: 0.50
Nodes (4): 01-05 — superseded, а не переписан, d27-c — бэклог, не фаза, Перепланирование фазы 1 — новые gap-планы вместо переписывания 01-05, d27-c в бэклог, Следствия

### Community 692 - "Под замок все маршруты кроме status, одна общая запись сервера без копий"
Cohesion: 0.50
Nodes (4): A5 → a5-a, одна общая запись сервера, D-27 → d27-b, позже d27-c, Под замок все маршруты кроме status, одна общая запись сервера без копий, Связанное

### Community 693 - "Релиз предлагается на границе фазы по RELEASES.md, а не готовится параллельно"
Cohesion: 0.50
Nodes (4): Как применять, Почему, Релиз предлагается на границе фазы по RELEASES.md, а не готовится параллельно, Решение

### Community 694 - "Схема версий — метка сборки с именем релиза, rc-теги и пилотный share"
Cohesion: 0.50
Nodes (4): Как применять, Почему, Решение, Схема версий — метка сборки с именем релиза, rc-теги и пилотный share

### Community 695 - "Живая приёмка фазы 2, 8 из 9 критериев, G6 остался stop, верификация gaps_found"
Cohesion: 0.50
Nodes (4): Живая приёмка фазы 2, 8 из 9 критериев, G6 остался stop, верификация gaps_found, Результаты, Решения, Что остаётся

### Community 696 - "Планирование фазы 3, восемь планов секрета и целостности, проверка прошла со второго раунда"
Cohesion: 0.50
Nodes (4): Планирование фазы 3, восемь планов секрета и целостности, проверка прошла со второго раунда, Результаты, Решения, Что остаётся

### Community 697 - "Планирование фазы 4, одиннадцать планов честных исходов мутаций, проверка прошла со второго раунда"
Cohesion: 0.50
Nodes (4): Планирование фазы 4, одиннадцать планов честных исходов мутаций, проверка прошла со второго раунда, Результаты, Решения, Что остаётся

### Community 698 - "Обсуждение фазы 5, шлюз секрета в каждом маршруте, payload раньше ext, откат через ext-previous"
Cohesion: 0.50
Nodes (4): Обсуждение фазы 5, шлюз секрета в каждом маршруте, payload раньше ext, откат через ext-previous, Результаты, Решения, Что остаётся

### Community 699 - "Планирование фазы 5, шестнадцать планов шлюза секрета и целостности, проверка прошла со второго раунда"
Cohesion: 0.50
Nodes (4): Планирование фазы 5, шестнадцать планов шлюза секрета и целостности, проверка прошла со второго раунда, Результаты, Решения, Что остаётся

### Community 700 - "2026-10-25 — исполнение фазы 6, семь планов, живой шлюз PHASE6_AUDIT_OK, верификация human_needed"
Cohesion: 0.50
Nodes (4): 2026-10-25 — исполнение фазы 6, семь планов, живой шлюз PHASE6_AUDIT_OK, верификация human_needed, Дальше, Открытое, Что сделано

### Community 701 - "Обсуждение фазы 6: журнал всех операций с промптом пользователя, call_id в конверте, 180 дней"
Cohesion: 0.50
Nodes (4): Обсуждение фазы 6: журнал всех операций с промптом пользователя, call_id в конверте, 180 дней, Результаты, Решения, Что остаётся

### Community 702 - "test_post_counts_before_transport_exception_and_strips_exception_text"
Cohesion: 0.20
Nodes (3): test_level_http_failure_is_not_absence(), test_post_counts_before_transport_exception_and_strips_exception_text(), test_post_step_does_not_copy_untrusted_secret_or_mac()

### Community 703 - "Обсуждение фазы 7: подтверждение через elicitation Hermes, одно «Да» на одну операцию, ФОП компании"
Cohesion: 0.50
Nodes (4): Обсуждение фазы 7: подтверждение через elicitation Hermes, одно «Да» на одну операцию, ФОП компании, Результаты, Решения, Что остаётся

### Community 704 - "Планирование фазы 6: семь планов журнала аудита в семь волн, проверка прошла с первого раунда"
Cohesion: 0.50
Nodes (4): Планирование фазы 6: семь планов журнала аудита в семь волн, проверка прошла с первого раунда, Результаты, Решения, Что остаётся

### Community 713 - "test_batch_config_encoding.py"
Cohesion: 0.33
Nodes (5): parametrize, skipif, Read-only config parsing in scratch cmd sessions; no deploy script is run., test_scratch_config_preserves_ascii_overrides_and_complete_parse(), test_windows_powershell_utf8_stdin_preserves_quotes_and_cyrillic()

## Ambiguous Edges - Review These
- `Revit MCP Server README` → `LLM.txt Project Architecture (stale nested-extension layout)`  [AMBIGUOUS]
  CLAUDE.md · relation: conceptually_related_to

## Knowledge Gaps
- **3469 isolated node(s):** `name`, `type`, `builtin`, `default_enabled`, `rocket_mode_compatible` (+3464 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 6054 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **27 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Revit MCP Server README` and `LLM.txt Project Architecture (stale nested-extension layout)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `format_response()` connect `format_response` to `clash_tools.py`, `test_status_target.py`, `room_tools.py`, `test_audit_correlation.py`, `unit/test_phase5_live_gate.py`, `annotation_tools.py`, `test_runtime_info.py`, `test_document_contracts.py`, `mep_tools.py`, `test_identity_rendering.py`, `tag_tools.py`, `unit/test_phase4_live_outcomes.py`, `tag_walls_call`, `tests/test_phase4_live_outcomes.py`, `test_routes_analysis_color_identity.py`, `building_tools.py`, `test_routes_mep_parameter_identity.py`, `test_selected_elements_output.py`, `test_audit_secret.py`, `_BenchProblem`, `document_tools.py`, `test_audit_tracer.py`, `tools/utils.py`, `mep_call`, `test_secret_gate_e2e.py`, `check_integrity`, `worksharing_tools.py`, `register_colors_tools`, `register_family_tools`, `read_options`, `detail_tools.py`, `test_bridge_serialization.py`, `test_tool_forwarding_model.py`, `describe_broken_path`, `test_phase5_gate_e2e.py`, `documentation_tools.py`, `StepGrid`, `view_management_tools.py`, `test_tool_forwarding_views.py`, `_through_the_bridge`, `structure_tools.py`, `_send`, `call`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Why does `step()` connect `_BenchProblem` to `format_response`, `unit/test_phase4_live_outcomes.py`, `object`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Why does `capture()` connect `_BenchProblem` to `_now`, `tests/test_phase2_live_identity.py`, `_dict`, `AccBench`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 43 inferred relationships involving `revit_post()` (e.g. with `read()` and `write()`) actually correct?**
  _`revit_post()` has 43 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `type`, `builtin` to the rest of the system?**
  _3469 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `cmd` be split into smaller, more focused modules?**
  _Cohesion score 0.0782312925170068 - nodes in this community are weakly interconnected._