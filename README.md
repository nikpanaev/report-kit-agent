# Report Kit

Windows: подготовлен вариант подключения LiveDune, настоящую проверку выполняет пользователь. Начать после разрешённой установки по [короткому порядку](docs/WINDOWS-CHECK.md); локальные тесты не подтверждают поддержку устройства.

Локальная подготовка переносимого комплекта для будущих отчётов. Версия: [VERSION](VERSION). Maturity: prototype; channel: development; stable release отсутствует.

Публикация, установка и подключение аккаунтов не разрешены этим этапом. Существующие клиентские агенты и материалы не включены. Git remote: no remote. Собственный код: [MIT](LICENSE), правообладатель Report Kit; проверка сторонних лицензий и уведомлений остаётся отдельной. Публикация этим решением не разрешена.

## Использование

Для сотрудника: [краткое руководство](docs/USER-GUIDE.md) и [помощь](docs/HELP.md). При первом обычном обращении к активному Report Kit агент сам начинает или продолжает настройку. Штатное действие настройки в приложении ведёт в тот же мастер; отдельный запрос «помоги настроить» не требуется. Агент по шагам выясняет образец, формат, период, источники и место сохранения; проверки и разрешённые настройки выполняет сам. [Опрос и помощь](references/onboarding.md). Технический план — [передача сотруднику](HANDOVER.md), настройка — [setup skill](skills/report-kit-setup/SKILL.md). Пакет подготавливает будущих клиентов; существующие runtime/chats/profiles не импортируются. Источники отчётных данных и настройки сотрудника — отдельная private workspace вне обеих package folders.

Восемь workflows: локальный черновик выпуска, помощь, setup, подключение клиента, сборка периода, QA, update/context refresh, [сопровождение](skills/report-kit-maintenance/SKILL.md). [Общий процесс](references/workflow.md); [принятый scope и ограничения](CHANGE-SPEC.md); [проверки/оставшиеся gates](EVIDENCE-INDEX.md). Пример workspace не рабочая конфигурация.

Local manifest `plugin.json` и `.agents/plugins/marketplace.json` подготовлены, но не установлены и не проверены actual host install. Вторая зависимость — exact pair в dependencies.json; source skills отдельно. Native connected Google/Docs/Sheets/Slides capabilities подключаются сотрудником, third-party plugin code не поставляется.

Проверки сопровождающего, не команды для сотрудника: `python3 scripts/check_package.py . --skills-root ../report-kit-skills`, `python3 scripts/test_package_boundaries.py`, `python3 scripts/check_report_templates_selftest.py`. Source checks only; no accounts/keys/Google writes. Для workspace отдельный check_workspace.py.

Для основ Google Таблиц: [маршрут проверки](references/sheet-templates.md), `python3 scripts/test_sheet_templates.py` и `python3 scripts/test_update_interfaces.py`. Это локальные примеры без доступа к Google; полнота источников, формулы на настоящих данных и устройство сотрудника проверяются отдельно.

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


## Report Kit naming and legacy compatibility

New client chat: `Report Kit / <client name>`; new portable reporting agent identifier: `report-kit-<client_id>`. Workflow IDs also use report-kit-. Package IDs are report-kit-agent/report-kit-skills; workspace schema2 is required. Legacy configurations and installed copies are not silently switched by a display rename. VK/LiveDune source skill IDs, REPORT_SKILLS_STATE_DIR and existing queue/state path names remain stable; their old report-skills label does not identify a second package or store. Setup must check the actual selected bytes and one UI queue before installation.

Google Таблицы: для новых клиентов доступно обычное копирование с проверкой копии перед заполнением (`scripts/check_sheet_copy.py`). Порядок и предел проверки — [здесь](references/sheet-templates.md). Отдельная синтетическая копия проверена на текущем рабочем подключении; это не установка у сотрудника и не приёмка клиентского отчёта.

Проверка истории для сопровождающего: добавить `--history` к check_package.py в исходном репозитории. Скачанный архив проверяется без этого флага и не требует Git; происхождение и хеши релиза сверяются отдельно.

## Одна ссылка для сотрудника

Сотруднику передают только ссылку на этот репозиторий, **report-kit-agent**. Агент сам организует получение совместимого опубликованного report-kit-skills, проверку и штатное подключение; версии и команды остаются его задачей. [Что подготовить и как начать](docs/USER-GUIDE.md#одна-ссылка-и-первая-настройка). Получение и обновление используют один [порядок](references/updates.md#единый-порядок-получения-комплекта).

Локально реализованы проверка delivery, инертная подготовка архивов и планы настройки/возврата. Source URLs пока не опубликованы. Настоящее скачивание GitHub Release, native install/update/rollback и устройство сотрудника остаются отдельными проверками; текущая подготовка их не выполняет.

[Файл для поддержки](docs/HELP.md#не-работает--нужен-файл-для-поддержки): по фразе «Не работает. Подготовь файл для поддержки» агент готовит один local ZIP без автоматической отправки. Запасной способ двойным нажатием использует тот же collector. Исходные журналы и клиентские данные не упаковываются.
