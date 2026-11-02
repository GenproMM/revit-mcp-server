---
tags: [session, phase7, pilot, live, stop]
date: 2026-10-26
---

# 2026-10-26 — пилот Phase 7, live STOP из-за аудита

## Точка продолжения

Не повторять live-операции. Исправить офлайн-классификатор аудита и видимость выбранных элементов, проверить замечания инструкций/каскада, подготовить обновлённый локальный пилот по новому явному разрешению. Исходный **PHASE7_BENCH_STOP** сохраняется. Фаза 7, SAFE-20/21 не закрыты; H4 коды и gateway не подтверждены.

## Что выполнено

- 07-14 Task 1 выполнен контроллером без субагентов: 6923 passed, 3 skipped (120.25s); latency 0.970s; все три транспорта по 59 инструментов; scratch GATE_OK. Коммит `92fbaf5` только с 07-VALIDATION.md. Отдельно выполнены все автоматические SAFE-01..19; статус draft/nyquist=false сохранён.
- Попытки subagent-worktree были ошибочными; пользователь потребовал работать без субагентов. Лишние worktrees не удаляли, доступ/права не обходили. Ошибка служебной очистки hot-cirrus не отменяет созданный коммит.
- По прямой просьбе пользователя собран ЛОКАЛЬНЫЙ переносимый пилот с НОВЫМ отдельным секретом. Разрешения отдельно получены на включение секрета в extension и payload. На share контроллер не обращался, runtime на этом ПК не менял, Revit/Hermes не запускал.
- Папка: `C:\Users\Admin\Downloads\RevitMCP-pilot-20261026-113138`. Версия `2026.10.26-1209.92fbaf5`, commit `92fbaf585b0de09add80921165416366f3ee9988`, CPY3123/Python 3.12.3, mcp 1.30.0, ~71.1 MiB, 4267 файлов до BUILD-INFO. `GATE_OK`, latency 1.009s, TOOLS=59, MANIFEST=ok, ruamel OK, integrity verified_match, три копии секрета равны (значения не выводили), source match: extension 37 / payload 133 / installers 4. 65 rollout/scan tests passed; envelope scan 35 файлов.
- Сборка использовала UV_OFFLINE=true, уникальный TEMP-staging и TEMP audit; общую .venv не синхронизировали. CP65001 ломала чтение config.cmd; CP866 сработала. Первый запуск pytest указал несуществующее имя теста; исправленный запуск 65 passed.
- Shipped source paths были чистыми, общая dirty tree содержала посторонние planning/vault/graph/scripts. Они в пилотный исходный код не включены. Секреты/сборка не коммитятся.
- START-HERE.txt обновлён с точным старым ext и порядком переключения. BUILD-INFO.json создан. Инструкция В ФАЙЛЕ всё ещё указывает sibling `06_RevitMCP_pilot`; пользователь затем выбрал вложенное размещение — обновить эту часть перед новой передачей.

## Размещение и переключение

Основная раздача `\\Srv-dfs\BIM\06_RevitMCP`, source clone `...\revit-mcp-server`. Подтверждённое старое расширение `...\ext\revit-mcp-server.extension`, payload `...\payload`.
Пользователь выбрал разместить пилот целиком внутри основной папки, не сливая ext/payload/install:
`\\Srv-dfs\BIM\06_RevitMCP\RevitMCP-pilot-20261026-113138\install\install.cmd`.
Установщик выводит SHARE относительно себя; чтение из nested pilot не переписывает основные ext/payload. Вложенная папка должна быть вне ancestor Git repo (проверить, не предполагать). Запуск build/publish с defaults опасен — это другой сценарий.
Перед установкой закрыть Revit/Hermes, снять ТОЛЬКО старый наш путь через `pyrevit extensions paths forget "\\Srv-dfs\BIM\06_RevitMCP\ext"`. Новая регистрация — nested pilot/ext. Профиль payload общий `%LOCALAPPDATA%\RevitMCP`, не side-by-side. Проверить Hermes current/app/server.py, автообновление (задача/ярлыки) — старый updater не должен вернуть основной payload. При ошибке installer шаги могли частично выполниться. Чужие расширения и серверные файлы не удалять. Full restart, не Reload.
Политика пилота: `C:\RevitMCP-Pilot\operator_policy.toml`, файл отсутствует → base `dd435f53b542`. REVIT_MCP_POLICY_FILE имеет приоритет. Сетевую политику отделa для bench не использовать.

## Live — выполнено пользователем на другом рабочем ПК

Пользователь `e.ermolenko`, Revit 2024. Документ `REvit_MCP_TEST_261026`, путь `C:\Users\e.ermolenko\Desktop\REvit_MCP_TEST_261026.rvt`. Один listener 127.0.0.1:48884 PID 14024, health healthy, permit protocol 1. Readiness: OK, POSTS_SENT=0, status200, base hash dd435f53b542/blocked=false/operator absent.
Direct: **DIRECT_CHECK_OK, POSTS_SENT=5, SECRET_OCCURRENCES=0**. Повтор запрещён.

| Сценарий | call_id | Факт/аудит из вывода пользователя |
|---|---|---|
| H1 | 2f275edd-ed5c-4965-9423-d0840798d788 | карточка подтверждена; выбранный элемент исчез (отдельное да пользователя); 1+13 hosted удалены; confirm/accepted/success |
| H2 | 3ac44370-fee9-4cd8-85bc-f91928edc2f4 | отказ, элемент остался; confirm/declined/denied |
| H3 | c95be1c4-6498-4911-8527-6fbd006df82d | ~5 минут ожидания; confirm/expired/expired |
| H4 first | fe61cf1c-a78f-4f66-a218-606cdf4c5a4d | confirm/declined/denied |
| H4 second | da96615d-7b95-46d4-bcdb-218d15010178 | новая карточка, элемент остался; confirm/declined/denied; коды карточек НЕ записаны |
| H5 | 826b5e07-d763-4beb-9603-b3843bfbcd54 | карточка подтверждена, сдвиг 12.5 мм по global X проверен пользователем; confirm/accepted/success |

Полученный классификатор: **PHASE7_BENCH_STOP, POSTS_SENT=5, SECRET_OCCURRENCES=0, REVIT_VERSION=2024**.
Причины: для H1,H2,H3,H4(оба),H5 `expected one audit entry`, затем производные ошибки expected accepted/declined/expired/each approval/fractional transform.
Диагностика: AUDIT_FILES=1, 25 строк; tools get_revit_status2/get_revit_model_info1/get_selected_elements2/delete_elements17/transform_elements3. H1/H5 по 3 совпадения call_id (два preflight+целевой маршрут), H2/H3/H4 по 2 (один preflight+целевой маршрут). Это законные строки разных стадий вызова, ошибочно считаемые дублями. Полный final.json контроллер не видел; итоговые args H4 ещё не проверены.
H3 timestamps 14:05:34.180Z preflight → 14:10:34.178Z expired. H1 target14:01:43.840Z; H2 target14:04:03.341Z; H4 targets14:13:43.188Z/14:14:31.232Z; H5 target14:18:12.089Z (2026-10-26).

## Где доказательства (НЕ на этом dev-ПК)

На рабочем ПК:
`C:\Users\e.ermolenko\AppData\Local\RevitMCP-Pilot-check-c6a220b603c5454aba8bd9b25c10976d\`
- preflight.json
- direct.json
- replies.json
- final.json

Исходный audit:
`C:\Users\e.ermolenko\AppData\Local\RevitMCP\audit\audit-20261026-132448-10452.jsonl`.
Пользователю предложено СКОПИРОВАТЬ 5 файлов в Документы/RevitMCP-Phase7-evidence, не перемещать/редактировать оригиналы; факт копирования/передачи не подтверждён. Не добавлять _bridge_secret/_build; журналы могут содержать BIM paths/args/user, не публиковать. Исправленный прогон только offline по копии, новый output; исходный STOP сохранять.

## Найденные замечания

См. [[Bench фазы 7 — preflight и итог операции имеют общий call_id]]. Ключевое: исправить `_scenario_entry` в live bench и тесты, узко исправить скрытые elements в `get_selected_elements`, актуализировать инструкции nested pilot/PowerShell stdin/CP866, разобраться с каскадной формулировкой без выдуманного точного прогноза. Нельзя трактовать автоматическое OK как доказательство различия незафиксированных кодов H4 или gateway/FOP company.

## Проверки при сохранении

- Текущие 46 тестов live bench проходят (0.86s), несмотря на подтверждённый live-дефект сопоставления аудита: реалистичная последовательность preflight/итог отсутствует в проверке, регрессию ещё добавить.
- Холодный старт 1.036s; TRANSPORTS_OK, все три транспорта по 59 инструментов.
- Полный suite запущен отдельно при CP866 перед коммитом; результат фиксируется при завершении.
- Сохранены все 11 строк REASON исходного STOP, draft/nyquist=false не изменены. Новые заметки — UTF-8 без BOM, ссылки проверены.

## Сохранение и коммит

Навигация index.md и текущие приоритеты.md обновлена, но эти файлы уже содержали посторонние staged/unstaged изменения до сохранения. Чтобы не включить прежние сессии, отдельный сессионный коммит включает две новые заметки (эту сессию и debugging «Bench фазы 7 — preflight и итог операции имеют общий call_id») и новый раздел Live bench (D-20) в 07-VALIDATION.md с исходным STOP/причинами и blocked SAFE-20. Офлайн-часть 07-VALIDATION.md уже закоммичена отдельно в 92fbaf5. STATE.md ранее изменён для Task 2 и остаётся вне нового коммита из-за смешанных правок. Поставляемый код в этой сессии не менялся.

## Информация о сессии

- Модель: Claude Code (точный ID модели не предоставлен средой).
- Дата: 2026-10-26.
- Изменено файлов в новом сессионном коммите: 3.
- Файлы: .planning/phases/07-repository-owned-mutation-safety-and-human-approval/07-VALIDATION.md; sessions/2026-10-26 — пилот Phase 7, live STOP из-за аудита.md; knowledge/debugging/Bench фазы 7 — preflight и итог операции имеют общий call_id.md.
- Другие изменения сессии: 07-VALIDATION.md (отдельный коммит), часть STATE.md, навигация vault; вне репозитория START-HERE.txt и BUILD-INFO.json пилотного комплекта. Предшествующие правки не присваивать этой сессии.

## Задание следующей сессии

1. Читать эту заметку и связанный debugging, CLAUDE.md, фактические diff/status; работать без субагентов. Сначала graphify query по задаче. Код ещё не исправлен.
2. Починить `_scenario_entry`/сопоставление аудита bench и добавить негативные/положительные регрессии. Защитить семантику аудита: preflight-строки не удалять и audit.py не ослаблять ради прохождения теста.
3. Узко исправить контракт get_selected_elements → format_response и тесты (ID/category/non-ASCII/empty/string/error), сохранив format_response и truthy-error invariant.
4. Проверить предупреждение каскада 1+13 и операции/коды H4; не выдумывать UI evidence. При невозможности доказать оставить пробел. Исправить operator docs: вложенный pilot, остановка старого updater, частичные установки, переносимый запуск PowerShell stdin и кодировки.
5. Запросить у пользователя ЛОКАЛЬНО размещённые копии пяти evidence-файлов, если они не переданы. Не ходить за ними на рабочий ПК/share. Reclassify существующего final.json только офлайн, в отдельный результат с provenance; новый live не запускать. Приёмка только после честных результатов; FOP/gateway/codes не объявлять пройденными.
6. Прогнать focused и полный suite отдельным test interpreter при CP866, cold start, transport и scratch payload. graphify update . после code changes. Коммиты только по явно затронутым путям, не включать чужое staged.
7. По новому разрешению подготовить новую локальную папку пилота с новой VERSION, совместимыми обеими половинами, тем же пилотным секретом (не ротировать), manifest/gate/source checks и START-HERE под фактическое размещение. Старый комплект не затирать. Архив/сеть/установку выполняет пользователь; новые секрет-containing copies требуют явного разрешения среды.

## Ограничения продолжения

Работать без субагентов, в основном дереве, чужие dirty/staged изменения не включать. Полные тесты — отдельный phase7-test-venv, cmd CP866. Shared .venv не трогать, чужие процессы не останавливать. Нет разрешения следующей сессии на live routes, share, push/tag/fleet release. Повтор сборки с тем же пилотным секретом — только после нового явного разрешения, не ротировать автоматически. Если редактируется revit_mcp, full Revit restart обязателен. R5/phase close не объявлять.
