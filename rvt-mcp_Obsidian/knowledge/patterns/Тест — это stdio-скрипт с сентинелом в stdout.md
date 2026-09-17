---
tags: [pattern, testing, howto]
date: 2026-09-04
---

# Тест — это stdio-скрипт с сентинелом в stdout

## Скелет

Копируется целиком, меняются только имя инструмента, аргументы и ассерты.

```python
# Что проверяет + нужен ли живой Revit.
import asyncio, sys, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PY = sys.executable
MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

async def main():
    async with stdio_client(StdioServerParameters(command=PY, args=[MAIN])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("get_revit_model_info", {})
            txt = " ".join(getattr(c, "text", "") for c in res.content)
            assert "ERROR DETAILS" not in txt, "false error header present:\n" + txt[:300]
            assert "total_elements" in txt, "expected model data missing"
            print("MODEL_INFO_OK")

asyncio.run(main())
```

## Обязательные элементы паттерна

**Абсолютный путь к `main.py` из `__file__`**, никогда относительно CWD:

```python
MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
```

**`sys.executable`** как команда — тот же интерпретатор, что запустил тест.

**Вложенные `async with`** — они же и teardown: закрывают сессию и убивают подпроцесс.

**Ассерт по подстроке** плоского текста `res.content`, с урезанным срезом полезной
нагрузки в сообщении об ошибке:

```python
txt = " ".join(getattr(c, "text", "") for c in res.content)
assert "..." in txt, "пояснение:\n" + txt[:300]
```

Срез `[:300]` обязателен — без него сообщение о падении может быть на десятки
килобайт.

**Уникальный сентинел заглавными** в stdout при успехе: `MODEL_INFO_OK`,
`INIT_LATENCY_S=0.912`. Код выхода 0 = пройден.

**Комментарий в начале файла**, нужен ли живой Revit. Это критично: половина тестов
без Revit не проходит, и это надо видеть, не читая код.

## Проверка ошибки — негативным ассертом

Не через перехват исключения, а через отсутствие баннера в отформатированном выводе:

```python
assert "ERROR DETAILS" not in txt, "false error header present:\n" + txt[:300]
```

Это следствие того, что ошибки в проекте — строки, а не исключения:
[[Ошибки не выбрасываются, а возвращаются строками]].

## Запуск

```bash
python tests/test_model_info_format.py   # нужен живой Revit
python tests/test_init_latency.py        # работает где угодно
```

Агрегирующей команды нет. Каждый скрипт запускается отдельно.

## Ограничения паттерна

Это интеграционные тесты, поднимающие настоящий сервер подпроцессом. Юнит-тестов нет.
Мокирования нет вообще — ни `unittest.mock`, ни фикстур.

**Что мокировать нельзя:** stdio-транспорт и рукопожатие `ClientSession`. Обе баги,
которые эти тесты охраняют, воспроизводятся только end-to-end.

**Что стоило бы тестировать иначе:** чистые функции —
`format_response`, `get_element_id_value`, `make_element_id`, `sanitize_string`,
`_resolve_bic`, `_resolve_categories`. Им stdio-скелет не нужен, им нужен обычный
юнит-тест. См. [[Тесты — это самостоятельные скрипты, а не pytest-сьют]].

## Если понадобятся тестовые данные

Каталога фикстур нет. Создавать как `tests/fixtures/` и загружать через
`os.path.join(os.path.dirname(__file__), ...)` — в согласии с существующим правилом
абсолютных путей.

## Связанное

[[Тесты — это самостоятельные скрипты, а не pytest-сьют]] ·
[[Холодный старт 0.9 с — это пол фреймворка, оптимизировать нечего]] ·
[[get_revit_model_info показывал данные под ложным заголовком ошибки]]
