# Phase 4: Live identity, ambiguity refusal, and multi-document addressing - Context

**Gathered:** 2026-09-23
**Status:** Ready for planning
**Mode:** `--auto` — все серые зоны выбраны автоматически, по каждому вопросу принят рекомендованный вариант (по поручению пользователя). Альтернативы — в `04-DISCUSSION-LOG.md`.

<domain>
## Phase Boundary

Каждый ответ относится к конкретному документу в конкретном процессе Revit; два процесса на
одном порту дают громкий именованный отказ; инженер может перечислить открытые документы,
адресовать мутацию явно и переключить активный документ. Единственная фаза, которая правит
`startup.py`: обёртка `api.route` ставится до цикла регистрации и одновременно включает шлюз
секрета и проверку целостности из фазы 2. Требования: IDENT-01…04, AMBIG-01…04, MDOC-01…05,
плюс живое включение SEC/INTG.

Вне фазы: мутации неактивного документа без переключения, адресация нескольких Revit-процессов
из одного сервера, журнал аудита.

</domain>

<decisions>
## Implementation Decisions

### Механизм подключения
- **D-01:** `startup.py` в начале `register_routes()`, до импорта доменов: (1) выполняет проверку
  целостности и сохраняет результат в модульном состоянии, которое читает `/status/`; (2) ставит
  `api = security.wrap_api(api)`. Подменённый `api.route` оборачивает каждый обработчик при
  регистрации. Правок в 23 доменных модулях нет.
- **D-02:** **Главный исследовательский флаг фазы.** pyRevit по параметрам обработчика решает,
  что внедрять (`doc`/`uidoc`/`uiapp`/`request`) и пускать ли вызов через `ExternalEvent`. Обёртка
  обязана сохранить набор и имена параметров исходного обработчика. До реализации нужно прочитать,
  **как** pyRevit их инспектирует (`pyrevitlib/pyrevit/routes/server/handler.py`, локальная копия
  `%APPDATA%\pyRevit-Master\`), и выбрать способ (генерация обёртки с той же сигнатурой, копия
  `co_varnames` и т.п.). Нельзя строить на догадке.
- **D-03:** Порядок проверок в обёртке POST: разобрать конверт `_mcp` → секрет (401) → целостность
  (423 при `verified_mismatch`) → документ (412/404, см. ниже) → обработчик с **очищенным**
  payload. Если объект `Request` pyRevit не позволяет подменить `.data`, обработчик получает
  прокси-объект запроса с тем же интерфейсом — выбирает планировщик после чтения
  `routes/server/base.py`.
- **D-04:** Секрет проверяется первой строкой обёртки, но внутри `ExternalEvent` (отдельного
  pre-dispatch крючка в pyRevit нет — проверено исследованием). Пока Revit инициализируется,
  неверный секрет висит так же, как любой запрос; записано как известное ограничение, не
  исправляется.
- **D-05:** `bridge.py` начинает класть конверт `_mcp` (`secret`, `document`) в тело каждого POST
  **в том же изменении**, что и обёртка на стороне Revit. Порядок выката на парк: сначала payload,
  затем перезапуск Revit с новым расширением (новое расширение со старым payload даст 401 до
  обновления payload). Планировщик проверяет grep-ом, что ни один обработчик не перебирает все
  ключи верхнего уровня тела (иначе лишний `_mcp` что-то сломает при частичном выкате).

### Идентичность
- **D-06:** Блок идентичности — вложенный ключ `revit_identity` в каждом ответе-словаре (GET и
  POST), никогда не новые `status`/`error`: `{pid, process_start, revit_version, port,
  session_token, document: {title, path, key}}`. Вложенный ключ не сталкивается с существующими
  полями (`document_title` в `/status/`) и не может сработать как сигнал ошибки в `format_response`.
- **D-07:** `session_token` — `uuid4().hex`, создаётся один раз на процесс Revit и хранится в
  `System.AppDomain.CurrentDomain.SetData("revit_mcp.session_token", ...)`: переживает Reload
  pyRevit и меняется только при перезапуске процесса (IDENT-01 «выдан один раз при запуске
  процесса»). `process_start` (`Process.GetCurrentProcess().StartTime`, ISO) защищает от повторного
  использования PID.
- **D-08:** Порт: как сторона Revit узнаёт свой порт — исследовательский флаг (конфиг routes
  pyRevit, сокет сервера или заголовок `Host` запроса). Планировщик выбирает по коду pyRevit.
- **D-09:** Документ в идентичности — тот `doc`, который получил обработчик, разрешённый на
  момент запроса (не кэш), через один общий защитный помощник `current_document()`, вынесенный
  из существующего исправления null-документа (Pitfall 14). `path` = `doc.PathName` (в том числе
  `RSN://`), `key` = `PathName`, если он не пуст, иначе `"unsaved:" + Title`, `title` через
  `sanitize_string`. Два `Project1` в двух процессах различимы по `pid` + `session_token` (IDENT-04).
- **D-10:** `format_response` добавляет одну строку идентичности перед телом любого ответа-словаря
  с `revit_identity`: `[Revit 2027 · PID 1234 · :48884 · <title>]`. Без этого успех-ветка вернула
  бы только `message`, и идентичность не дошла бы до модели. Тест фиксирует строку.

### Отказ при двух слушателях
- **D-11:** Обнаружение на стороне CPython **перед каждым** вызовом bridge (GET и POST): ctypes
  `GetExtendedTcpTable` (iphlpapi, `TCP_TABLE_OWNER_PID_LISTENER`, IPv4 и IPv6) — без новых
  зависимостей, быстрее миллисекунды, без кэша. Больше одного **разного** PID на `REVIT_PORT` →
  отказ без отправки: `"Error: two processes are listening on port 48884 (PID 1234 Revit.exe,
  PID 5678 Revit.exe) — close one and retry; nothing was sent"` (AMBIG-01…03). Имена процессов —
  best-effort через ctypes.
- **D-12:** Не-Windows или ошибка API таблицы → вызов проходит, а `get_revit_status` сообщает
  `listener_check: unverifiable`. Чистая функция решения `decide_listeners(rows, port)` тестируется
  на фикстурах, ctypes-сбор — тонкий.
- **D-13:** AMBIG-04: после выката повторить живую репродукцию `param-write-rolls-back` с видимой
  идентичностью и записать исход (гипотеза «отвечал другой процесс» подтверждена или опровергнута)
  в `.planning/debug/param-write-rolls-back.md`.

### Мультидокумент
- **D-14:** **Проверка, а не перенацеливание.** Мутации всегда выполняются над активным документом;
  явный `document` в конверте — предусловие. Не совпадает с активным → **412** с активным
  документом, списком открытых и подсказкой вызвать `activate_document`. Мутации неактивного
  документа без переключения отложены: разделение Document/UIDocument и запрет переключения во
  время событий API не проверены (Pitfall 15), а большинство маршрутов читает `revit.doc`.
  — **Reversibility:** reversible — перенацеливание можно добавить позже поверх того же селектора.
- **D-15:** Поведение без `document` (MDOC-03): открыт ровно один не-связанный документ → вызов
  идёт в него; открыто больше одного → **412** со списком открытых и требованием указать `document`.
  Связанные (`IsLinked`) не считаются; семейные документы считаются (их видит пользователь).
  Одна общая фраза о правиле добавляется в докстринг каждого инструмента, который делает POST.
- **D-16:** Селектор `document`: точный `key` (предпочтительно) или точный `title`, если он
  уникален в сессии; неоднозначный title → 412 с кандидатами. Документ, закрытый после получения
  списка, → **404** «document is not open» со списком открытых (MDOC-05), отличимо от 412.
- **D-17:** Каждый инструмент, вызывающий `revit_post`, получает необязательный параметр
  `document: str = None` (перед `ctx`) и передаёт его `revit_post(..., document=document)`; bridge
  кладёт его в конверт. Правка механическая (~30 функций); `scripts/conventions.py` и
  `test_conventions.py` требуют параметр у каждого инструмента с `revit_post`. Проверка документа
  применяется ко всем POST, включая читающие, — одно правило без классификации.
- **D-18:** Новые инструменты и маршруты: `list_open_documents` (GET `/documents/`: title, path,
  key, is_active, is_linked, is_family) и `activate_document` (POST `/activate_document/`):
  `OpenAndActivateDocument(path)` для сохранённых документов с той же `WorksetConfiguration`, что у
  `/open_model/` (без диалога выбора рабочих наборов); несохранённый документ → понятная ошибка
  «activate it in the Revit UI». `tests/unit/tool_manifest.txt` +2 инструмента в том же коммите.
- **D-19:** Исключения из проверки документа — явный список в `security.py` с тестом: маршруты, не
  работающие над активным документом (`/activate_document/`, `/open_model/`). Список короткий и
  закрытый; каждое добавление требует причины в комментарии.

### Живая проверка
- **D-20:** Всё реализуется и проходит `uv run pytest tests/unit` до первого перезапуска; затем
  один перезапуск Revit и заскриптованный чек-лист критериев 1–9 на стенде (два Revit, несколько
  моделей в одной сессии). Тест повреждённого файла — на установке-копии с манифестом (не на
  junction, где «повредить файл» = править репозиторий).
- **D-21:** До перезапуска: `Get-NetTCPConnection -LocalPort 48884 -State Listen` ровно одна
  строка (кроме намеренного теста двух слушателей), Revit запускается без модели, модели
  открываются через `/open_model/`.

### Claude's Discretion
- Точная форма строки идентичности, текст отказов 412/404, имена помощников в `security.py`.
- Включать ли `revit_identity` в ответы-списки (не словари) — по умолчанию нет.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Объём и требования
- `.planning/ROADMAP.md` §Phase 4 — цель и 9 критериев
- `.planning/REQUIREMENTS.md` §Идентичность, §Разрешение неоднозначности, §Мультидокумент
- `.planning/phases/02-secret-gate-and-payload-integrity-unit-verified/02-CONTEXT.md` — конверт `_mcp`, коды 401/423, три состояния целостности, классификатор бинда
- `.planning/phases/01-serialization-and-configurable-addressing/01-CONTEXT.md` — `bridge.py`, `REVIT_PORT`
- `.planning/phases/03-honest-outcomes-on-every-mutating-route/03-CONTEXT.md` — блок `outcome`, код 409

### Исследование и история
- `.planning/research/ARCHITECTURE.md` §Question 1, §Question 2 — обёртка `api.route`, штамп после возврата обработчика
- `.planning/research/PITFALLS.md` §Pitfall 14 (устаревший `revit.doc`), §Pitfall 15 (порядок детекта слушателей и адресации; Document против UIDocument)
- `.planning/debug/param-write-rolls-back.md` — открытая гипотеза для AMBIG-04
- `CLAUDE.md` §Known sharp edges — два Revit на 48884, диалог рабочих наборов, зависание при инициализации, Reload небезопасен

### Код
- `startup.py:73-122` — `register_routes()`, место установки обёртки
- `revit_mcp/status.py` — `/status/`, дополняется идентичностью, целостностью, биндом
- `revit_mcp/document.py` — `/open_model/` и `WorksetConfiguration`
- `revit_mcp/code_execution.py` — существующее защитное повторное получение `revit.doc`
- `tools/utils.py:5-107` — `format_response`
- pyRevit: `%APPDATA%\pyRevit-Master\pyrevitlib\pyrevit\routes\api.py`, `server\router.py`, `server\handler.py`, `server\base.py`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Один объект `api` передаётся по ссылке во все регистраторы — точка для обёртки.
- `/open_model/` уже умеет открывать без диалога рабочих наборов — основа для `activate_document`.
- Защитное повторное получение `revit.doc` из исправления null-документа — вынести в общий помощник.

### Established Patterns
- Регистрация по соглашению, импорты внутри функций регистрации.
- Правило «dict is an error only if…» — идентичность только вложенным ключом с данными.

### Integration Points
- `startup.py` (обёртка + целостность), `bridge.py` (конверт, детект слушателей), `tools/*_tools.py` (параметр `document`), `tools/utils.py` (строка идентичности), новый домен документов на обеих сторонах.

</code_context>

<specifics>
## Specific Ideas

- Отказ при двух слушателях должен называть оба PID и имена процессов, чтобы инженер знал, что закрыть.
- Отказ из-за неоднозначного документа должен перечислять открытые документы — модель сразу повторит вызов с `document`.

</specifics>

<deferred>
## Deferred Ideas

- Мутации неактивного документа без переключения (перенацеливание `doc` по селектору) — после живой проверки Document/UIDocument по маршрутам.
- Адресация нескольких Revit-процессов из одного процесса сервера.
- Перекрёстная сверка PID из ответа с PID слушателя — только если одного детекта окажется мало.

</deferred>

---

*Phase: 04-live-identity-ambiguity-refusal-and-multi-document-addressing*
*Context gathered: 2026-09-23*
