---
name: report-monthly
description: "Собрать отчёт за явно заданный период для подключённого клиента по его профилю, принятым native шаблонам и источникам; использовать и для накопительного формата по клиентским правилам."
---

# Сборка отчёта

Прочитай [workflow](../../references/workflow.md) и только явно выбранный private client profile/registry. Уточнить отсутствующий период/year, account для exact new files, sources и changed client rules. Без profile/base/source approval остановить зависимую сборку, не подставлять прошлый отчёт.

Создать frozen run inventory в private workspace: identities, budget, source/spec hashes, period/filter/population и полная coverage. Проверить actual template native readbacks/metadata/assets/history, выполнить scripts/check_report_templates.py для всех required roles. Только затем копировать выбранный native base и его backing data; источники read-only.

Сбор метрик/cursors и каждый social capture — правильным source skill, не собственной реализацией. Полный post inventory, модерация и дедуп по client contract; строки/formulas/native tables/editable charts и protected zones проверяются. Сохранять принятую накопительную историю; новый месяц только отдельно разрешённый.

При сбое/изменении использовать [maintenance](../report-maintenance/SKILL.md): exact разрешённый адресат, один incident, actual callback и origin replay. Не исправлять installed skill самостоятельно, не обходить denial, сохранять pause/budget и незавершённые assets. Обычный callback не означает возобновление paused отчёта.

Заполнить копию, выполнить [QA](../report-quality-check/SKILL.md), исправить разрешённые проблемы с новым receipt/revision. Полный readback/render и визуальный просмотр всех страниц/снимков, ссылки/account/location/sharing проверены перед выдачей. Дать настоящий file link и ограничения; ждать приёмки. После приёмки cleanup workflow. Никакой автоматической отправки или нового периода.
