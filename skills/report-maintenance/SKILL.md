---
name: report-maintenance
description: "Сопроводить сбой или изменение отчётного процесса/скилла: правильный служебный адресат, разрешённое обращение, проверка исправления и повтор исходного шага. Не обычная сборка отчёта."
---

# Сопровождение отчётов и скиллов

Прочитай [maintenance](../../references/maintenance.md) и явно выбранный private workspace. Определи роль: origin клиента, координатор общего процесса или сопровождающий exact skill. Сверь current binding, original human authority и scope; не переносить чужие IDs/grants и не угадывать адресат по названию.

Сначала минимально отличить defect от доступа/среды/данных. Подготовить обезличенный incident с exact identity, reproducer, scope, budget и sealed receipts. scripts/maintenance.py — read-only consistency guard, не доказательство прав и не messaging tool. До разрешённого native send сохранять STARTED, после — actual delivery/ACK; uncertain отправку не повторять без readback исходного handle.

Исправление делает только назначенный сопровождающий в разрешённой source branch; клиентский агент общую копию не меняет. Regression/source identity и [compatible update](../../references/updates.md) перед callback/replay; не править критерии ради PASS. Callback route ведёт к origin. Разрешённые UI/Git действия сериализовать штатно.

Incident закрывать после actual успешного origin replay, с loaded identity и сохранённой историей. Failed replay/open, unknown/unavailable recipient/blocked, paused origin/wait сохранять честно. Callback не запускает новый отчёт, не снимает паузу и не повышает бюджет. Нужные получателю assets сохранять до получения/приёмки, затем exact cleanup; proof-only хеш не заменяет PNG.

Сотруднику сообщить результат или один конкретный вопрос. Отправка GitHub Issue/внешним людям, установка/публикация/новые логины требуют отдельного полномочия; local JSON receipt не расширяет его.
