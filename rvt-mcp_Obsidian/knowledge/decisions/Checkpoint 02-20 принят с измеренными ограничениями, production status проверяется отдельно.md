---
tags: [decision, phase-2, checkpoint, identity]
date: 2026-10-16
---

# Checkpoint 02-20 принят с измеренными ограничениями, production status проверяется отдельно

Пользователь: «Принимаю чекпоинт, давай дальше». Разрешён следующий существующий план 02-01, не автоматическое выполнение всей фазы.

- G1: .NET GUID/AppDomain при startup расширения в новом Revit-процессе; не буквальный момент OS process creation. Actual port — существующий bound RoutesServer; explicit-route-only, общая wrapper-семантика не доказана.
- G2: retained-reference-equals-v1; IsValidObject, единственное семантическое Equals, lifetime reference и будущие monotonic tokens/tombstones. Hash не selector.
- G3: явный неактивный Document только для измеренных summary/levels, без UI switch.
- G4: измеренная активация saved-existing-path; unsaved/non-file cases отказывают. Saved-workshared не включать по аналогии; save/reopen/source substitution не допускаются.
- G5: полный netstat сохраняет обоих реальных PID одного endpoint. Get-NetTCPConnection оказался неполным. Временные genuine RoutesServer остановлены и teardown проверен. Это не доказательство автоматического primary-port assignment.
- D-15: execute_revit_code и /execute_code/ остаются включены как trusted arbitrary-code exception, не document sandbox.

Исторические STOP и missing-provenance captures сохраняются. Человеческое принятие не подменяется автоматически выданным classifier approval и не объявляет более сильную G1 timing-гарантию.

02-01 готов offline; **production recheck — отдельный 02-02 после полного рестарта Revit**. No-target пока legacy; discovery/full target routing/locks — 02-03. G6 не запускался и требует отдельного разрешения. Чужое расширение не трогать; наш пакет/API — genpro_revit_mcp.

См. [[2026-10-16 — принят checkpoint 02-20 и реализован selected status 02-01]], [[Под замок все маршруты кроме status, одна общая запись сервера без копий]], [[Фаза 2 адресует процесс на вызов и разделяет чтение с мутацией документа]].
