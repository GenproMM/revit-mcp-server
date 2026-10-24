---
tags: [decision, security, approval, jev, phase7]
date: 2026-10-16
status: accepted-ownership-not-implementation
---

# Защита операций Revit принадлежит MCP-репозиторию, не Hermes Fork

## Решение пользователя

Вся безопасность операций revit-mcp-server должна находиться в этом репозитории. Предложение реализовать обязательный gate в Hermes Fork отклонено. Hermes остаётся неизменённым клиентом: существующий интерфейс подтверждения можно использовать только после проверки совместимости, но правила и enforcement не размещаются в harness.

Пользователь также требует лёгкую адаптацию, стабильную защиту и корректируемые правила. В roadmap добавлена фаза 7 — Repository-owned mutation safety and human approval. Создание фазы не разрешает реализацию, deployment или live-мутации.

## Направление для планирования

- CPython: локальная валидируемая политика, классификация, объяснение риска, запрос подтверждения.
- Revit extension: минимальное обязательное enforcement до эффекта, связанное с процессом/документом и окончательными аргументами.
- Одноразовые разрешения, expiry, проверка предусловий и защита от повторного выполнения; подписи без учёта использования недостаточно.
- Jev необязателен и не может ослаблять обязательные правила. Внешняя передача BIM-данных не разрешена.
- Переиспользовать identity, authentication/integrity, honest outcomes и audit фаз 2/4/5/6; не создавать конкурирующие системы.

## Что ещё не доказано

Поддержка server-initiated MCP elicitation установленным SDK и неизменённым Hermes, строгая связь клика с операцией, минимальный permit protocol и cross-process single-use требуют исследования и тестов. Direct HTTP enforcement не решает arbitrary-code/ОС обходы и cross-wiring общего pyRevit handler.

Оба execute-code пути остаются доверенными произвольными исключениями по D-15 фазы 2. Они не отключаются молча и не объявляются sandbox. Полной защиты от кода с теми же ОС-правами не обещаем.

## Материалы

- `.planning/phases/07-repository-owned-mutation-safety-and-human-approval/07-CONTEXT.md`
- `.planning/phases/07-repository-owned-mutation-safety-and-human-approval/07-RESEARCH-NOTES.md`
- [[2026-10-16 — исследование Jev и серверной защиты, добавлена фаза 7]]
- [[Фаза 2 адресует процесс на вызов и разделяет чтение с мутацией документа]]
- [[Checkpoint 02-20 принят с измеренными ограничениями, production status проверяется отдельно]]
