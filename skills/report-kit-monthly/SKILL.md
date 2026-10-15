---
name: report-kit-monthly
description: "Собрать отчёт за явно заданный период для подключённого клиента по его профилю, принятым native шаблонам и источникам; использовать и для накопительного формата по клиентским правилам."
---

# Сборка отчёта

Прочитай [workflow](../../references/workflow.md) и только явно выбранный private client profile/registry. Уточнить отсутствующий период/year, account для exact new files, sources и changed client rules. Без profile/base/source approval остановить зависимую сборку, не подставлять прошлый отчёт.

Создать frozen run inventory в private workspace: identities, budget, source/spec hashes, period/filter/population и полная coverage. Проверить actual template native readbacks/metadata/assets/history для всех required roles. Для Docs/Slides и выбранного full_snapshot выполнить scripts/check_report_templates.py перед копированием. Для Google Таблиц с native_copy следовать [порядку копирования и проверки](../../references/sheet-templates.md): подтвердить принятую основу и аккаунт, скопировать целиком, проверить новый ID и запустить scripts/check_sheet_copy.py до заполнения. Backing data копировать отдельно; источники read-only.

Сбор метрик/cursors и каждый social capture — правильным source skill, не собственной реализацией. Полный post inventory, модерация и дедуп по client contract; строки/formulas/native tables/editable charts и protected zones проверяются. Сохранять принятую накопительную историю; новый месяц только отдельно разрешённый.

При сбое/изменении использовать [maintenance](../report-kit-maintenance/SKILL.md): exact разрешённый адресат, один incident, actual callback и origin replay. Не исправлять installed skill самостоятельно, не обходить denial, сохранять pause/budget и незавершённые assets. Обычный callback не означает возобновление paused отчёта.

Заполнить копию, выполнить [QA](../report-kit-quality-check/SKILL.md), исправить разрешённые проблемы с новым receipt/revision. Полный readback/render и визуальный просмотр всех страниц/снимков, ссылки/account/location/sharing проверены перед выдачей. Дать настоящий file link и ограничения; ждать приёмки. После приёмки cleanup workflow. Никакой автоматической отправки или нового периода.

Перед новой работой используй [общий единый порядок обновлений](../../references/updates.md): координатор проверяет published releases не чаще24ч и полную совместимость всех клиентов. В клиентской роли используй сохранённый coordinator check и разрешённый maintenance маршрут; не читай чужие профили и не устанавливай пакеты сам. Обновление только между заданиями, без изменения клиентских правил и истории. Новые client profiles получают этот же общий механизм.
