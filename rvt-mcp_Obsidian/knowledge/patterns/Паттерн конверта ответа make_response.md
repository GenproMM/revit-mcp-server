---
tags: [pattern, response, contract, routes]
date: 2026-09-04
---

# Паттерн конверта ответа make_response

## Форма

Обработчик маршрута **всегда** возвращает `routes.make_response(data=..., status=...)`.
Никогда сырой словарь, никогда строку, никогда `None`.

**Успех:**

```python
return routes.make_response(data={
    "status": "success",
    "clash_count": len(clashes),
    "clashes": clashes,
    "message": "Found {} clash(es)".format(len(clashes)),
})
```

**Провал:**

```python
return routes.make_response(data={"error": str(e)}, status=500)
```

## Ключи, которые понимает форматтер

`format_response` на MCP-стороне выбирает, что показать, по порядку:

| Приоритет | Ключ | Когда использовать |
|---|---|---|
| 1 | `output` | Ответы исполнения кода |
| 2 | `message` | Человекочитаемый итог операции |
| 3 | `result` | Единичное значение |
| 4 | `data` | Вложенная полезная нагрузка |
| 5 | `status == "active"` | Только для статус-ответа |
| 6 | всё остальное | Структурированные данные — выводятся как `Ключ: значение` |

То есть **если в ответе есть `message`, всё остальное клиент не увидит**. Это важнейшая
практическая деталь: класть данные рядом с `message` бессмысленно — они будут
проигнорированы. Либо `message` (краткий итог), либо структурированные поля без него.

## Ключи-сигналы ошибки

Провалом считается **только** непустой `error` либо `status` из
`error` / `failed` / `failure` / `exception`. Всё остальное — данные.

> [!important] Не изобретайте новых сигналов ошибки
> `"ok": false`, `"success": false`, `"failed": true` форматтером **не** распознаются.
> Ответ будет отрендерен как успех. См.
> [[Провал ответа определяется только ключом error или явным статусом]].

## Полезные дополнительные ключи

Форматтер отдельно выводит их в блоке ошибки: `details`, `traceback`,
`code_attempted`, `endpoint`, `request_data`, `response_code`.

Практика проекта — добавлять контекст, помогающий ИИ-клиенту исправиться:

```python
return routes.make_response(data={
    "error": "No valid categories to check",
    "unknown_categories": a_unknown + b_unknown,
    "hint": "Use BuiltInCategory ids like OST_Walls or aliases like 'ducts', 'beams'.",
}, status=400)
```

Ключ `hint` — не стандарт, но он попадает в блок `=== ADDITIONAL RESPONSE DATA ===` и
доезжает до модели.

Аналогично `note` в успешном ответе `clash_check` предупреждает про ограничение Revit:

```python
"note": "Auto-joined concrete and geometry-less elements (e.g. rebar) are not reported by Revit's interference logic.",
```

## Куда это движется

Правильное решение на будущее — один явный конверт на Revit-стороне,
`{"ok": bool, "data": ..., "error": ...}`, и `format_response` как глупый рендерер
поверх него. Сейчас форматтер **угадывает**, и это уже стреляло:
[[get_revit_model_info показывал данные под ложным заголовком ошибки]].

## Связанное

[[Провал ответа определяется только ключом error или явным статусом]] ·
[[Коды статусов 400, 404, 500, 503 несут фиксированный смысл]] ·
[[Паттерн обработчика маршрута — валидация, транзакция, сериализация]] ·
[[Ошибки не выбрасываются, а возвращаются строками]]
