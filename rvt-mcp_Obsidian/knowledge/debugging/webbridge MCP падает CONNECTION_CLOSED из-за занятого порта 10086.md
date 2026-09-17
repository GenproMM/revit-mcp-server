---
tags: [debugging, tooling, mcp, workaround, resolved]
date: 2026-09-07
---

# webbridge MCP падает CONNECTION_CLOSED из-за занятого порта 10086

**Статус:** ОБХОДНОЙ ПУТЬ НАЙДЕН · внешний инструмент, не код этого репозитория

## Симптом

MCP-сервер `webbridge` (пакет `kimi-webbridge`, запускается как
`cmd /c npx kimi-webbridge mcp`) не поднимается в сессии Claude Code.
Harness показывает только `webbridge (CONNECTION_CLOSED): "Connection closed"`
— по этому сообщению выглядит так, будто сервер не настроен или недоступен
вообще.

## Причина

`kimi-webbridge mcp` держит WebSocket-сервер моста к браузеру на
захардкоженном порту **10086**. Если такой процесс уже запущен (из другой
сессии или зависший), новый экземпляр падает при старте:

```
[webbridge] 启动 MCP 服务器...
[ws] 服务器错误: listen EADDRINUSE: address already in use :::10086
```

Ровно эту ошибку harness сворачивает до `CONNECTION_CLOSED` — сообщение не
называет причину.

## Диагностика

```powershell
netstat -ano | Select-String ":10086"
Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" | Select ProcessId,Name,CommandLine
```
Живой процесс на порту 10086 подтверждает: мост фактически работает, просто
занят другим экземпляром MCP-обёртки.

## Обходной путь

Уже запущенный `kimi-webbridge mcp` продолжает обслуживать браузер, и до него
можно достучаться напрямую через CLI того же пакета — без MCP-транспорта:

```bash
npx kimi-webbridge <tool> '<json-аргумент>'
```

Инструменты: `navigate, find_tab, find, evaluate, network, snapshot, read_page,
click, fill, mouse_click, cdp, key_type, send_keys, screenshot, scroll,
save_as_pdf, upload, close_tab, list_tabs, close_session, wait, dialog,
select_option, hover, drag`.

Практически проверено на живой задаче (правка заголовка страницы Confluence):
`navigate` → `read_page` → `fill('#content-title', …)` →
`click('#rte-button-publish')` — сработало end-to-end.

Важные детали вызова:
- Запускать из **Bash**, не PowerShell — PowerShell разъедает внутренние
  кавычки JSON-аргумента, и CLI получает невалидный JSON
  (`参数不是有效的 JSON`). Для не-ASCII текста надёжнее собрать JSON в
  файл (heredoc) и передать `"$(cat file)"`.
- `evaluate` ожидает поле `code`, не `expression`.
- `navigate`/`fill`/`click`/`evaluate` принимают `tabId`, полученный из
  ответа `navigate` — без него мост может выбрать не ту вкладку.

## Настоящее исправление

Не относится к этому репозиторию — это инфраструктурная проблема самого
`kimi-webbridge` (жёстко зашитый порт без опции `--port` и без проверки уже
работающего инстанса перед бросанием ошибки). Если конфликт мешает регулярно,
варианты: `Stop-Process` лишнего `node.exe` перед стартом сессии, либо
попросить апстрим сделать порт настраиваемым / переиспользовать существующий
сервер вместо падения.

## Связанное

Использовано в рамках задачи, не связанной с кодовой базой revit-mcp-server
(правка заголовка страницы Confluence через Kiwi Web Bridge) — отдельного
пункта в [[Текущие приоритеты]] не заводилось.
