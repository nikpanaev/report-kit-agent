# report-agent

Локальная подготовка переносимого комплекта для будущих отчётов. Версия: [VERSION](VERSION). Maturity: prototype; channel: development; stable release отсутствует.

Публикация, установка и подключение аккаунтов не разрешены этим этапом. Существующие клиентские агенты и материалы не включены. Git remote: no remote. Владелец подтвердил права и принял MIT; публичное имя правообладателя и файл LICENSE пока не согласованы. Публикация этим решением не разрешена.

## Использование

Для сотрудника: [краткое руководство](docs/USER-GUIDE.md) и [помощь](docs/HELP.md). Начать можно сообщением «Помоги настроить отчётного агента». Технический план — [передача сотруднику](HANDOVER.md), настройка — [setup skill](skills/report-setup/SKILL.md). Пакет подготавливает будущих клиентов; существующие runtime/chats/profiles не импортируются. Источники отчётных данных и настройки сотрудника — отдельная private workspace вне обеих package folders.

Восемь workflows: локальный черновик выпуска, помощь, setup, подключение клиента, сборка периода, QA, update/context refresh, [сопровождение](skills/report-maintenance/SKILL.md). [Общий процесс](references/workflow.md); [принятый scope и ограничения](CHANGE-SPEC.md); [проверки/оставшиеся gates](EVIDENCE-INDEX.md). Пример workspace не рабочая конфигурация.

Local manifest `plugin.json` и `.agents/plugins/marketplace.json` подготовлены, но не установлены и не проверены actual host install. Вторая зависимость — exact pair в dependencies.json; source skills отдельно. Native connected Google/Docs/Sheets/Slides capabilities подключаются сотрудником, third-party plugin code не поставляется.

Проверка: `python3 scripts/check_package.py . --skills-root ../report-skills`, `python3 scripts/test_package_boundaries.py`, `python3 scripts/check_report_templates_selftest.py`. Source checks only; no accounts/keys/Google writes. Для workspace отдельный check_workspace.py.

Privacy: никаких реальных API keys, сессий, cookies, браузерных профилей, личных аккаунтов, клиентских IDs или сырой истории. Проверяются candidate files и reachable Git history; ignored tool caches не часть distribution. Pattern scan не полная независимая security проверка.

## Product Versioning + Maturity/Channel Contract

- **Maturity phase:** prototype
- **Release channel:** development
- **Public compatibility promise:** none; no employee-device/account/runtime support validated yet
- **1.0.0 entry criteria:** actual supported-device/account install and control report; reviewed license/dependencies; independent QA/security; packaged acceptance and separate owner G6
- **Rebaseline policy:** only explicit owner decision before external distribution; never rename old artifacts or silently migrate private workspaces
- **Release destination:** local-only
- **External AI/model API:** not applicable; no new model API client or SDK/key provisioning; employee Codex provider/data-use terms must be checked before live work

VERSION is the sole development-version source; plugin manifest is a checked mirror. Package content identity and private workspace schema are separate. Public GitHub release/URLs require later explicit authority.

Подготовка локального черновика: [release workflow](references/releases.md). [Изменения для пользователя](CHANGELOG.md). Публикация и расписание не активированы.
