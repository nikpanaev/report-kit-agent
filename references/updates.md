# Обновление и откат

Обновляются package инструкции и код, не клиентские данные/отчёты. Проверка наличия новых версий не разрешает установка, выполнение downloaded hooks или переход на main.

- Между отчётами проверить утверждённый source/release, exact agent version и совместимую report-kit-skills identity. Пока public source не задан, использовать явно выбранные локальные копии; не придумывать URL, release signature или signer trust.
- Показать diff, changed capabilities/permissions, известные ограничения, проверенные license/provenance и связанные версии. Secrets/auth/provider/updater изменения требуют отдельного review. Hash доказывает совпадение, не доверенность автора.
- Получить разрешение на exact обновление, сохранить old package identities и локальную возможность отката. Native plugin installation route предпочтительнее собственного updater. Не запускать update посередине активного run.
- Package read-only; workspace path отделён. Не делать массовый search/replace профилей. Новый общий процесс не отменяет принятые клиентские правила и не мигрирует workspace schema автоматически.
- Для явно разрешённых собственных клиентских чатов отправить context refresh только при direct human authority. Каждый адресат перечитывает common files и свой профиль, сохраняет прежний receipt, подтверждает actual new identity и blockers. Delivery не ACK. Общий update не запускает отчёт, сбор данных, browser UI или sharing.
- Откат выбрать по сохранённой identity после проверки, что нет последующих owner edits. Не изменять reports, source snapshots, Google permissions или browser sessions. После отката снова подтвердить identity и refresh собственных явно разрешённых чатов.
- При несовместимости или missing receipt результат BLOCKED/PARTIAL. Не ослаблять checks, не менять dependency pin ради green; сохранить failed attempt и исправить причину в разрешённом scope.

Distribution URLs, release signing/hosting и live update/rollback на новом устройстве ещё не проверены. После отдельного решения о публикации проверить настоящий install/update path, а не только file hashes.

## Обнаружение версии

Читай approved source через доступный native GitHub/HTTP tool. assets/update-source.example.json не настроен: null URLs означают CONFIGURE_SOURCE, не догадку об upstream. Выбранные сотрудником настоящие URLs и канал сохраняются только в private workspace. Общий release index в report-kit-agent содержит exact pair обоих packages; assets/release-index.example.json пустой. Пока публикации нет, локальные synthetic fixtures не считать published release.

Проверка перед работой: scripts/updates.py due с локальными source/checked_at, не чаще24ч. USE_CACHE/отсутствие новой версии — без сообщения; KEEP_CURRENT_OFFLINE сохраняет текущий комплект. При отозванном текущем релизе, нарушенной identity или необходимом действии сообщить конкретную проблему. Нет daemon/фоновой проверки при закрытом приложении. Helper не загружает сеть, не запускает downloaded code и не записывает время: native результат проверки и timestamp сохраняет исполнитель приватно.

У GitHub latest исключены prerelease/draft: для согласованного рабочего dev-канала читать весь approved index/list, не latest и не main. [GitHub Releases API](https://docs.github.com/en/rest/releases/releases) и [SemVer](https://semver.org/). select отвергает draft/revoked/другой канал, ambiguous pair и same-version drift; ниже текущей версии автоматически не переходит. Skills-only изменение требует нового agent release с новым exact dependency pair. Проверить original repository/tag/assets и provenance штатным tool, независимо от согласованности JSON. Hash не подпись автора. Отозванный release не использовать для обычного отката без отдельного решения владельца.

## Полный compatibility snapshot

Candidate contracts.json — versioned declarations. report-kit-agent CORE: workspace2, maintenance1, template_registry3, profile1. report-kit-skills: source:<skill>1 и shared helpers1. workspace2 вводит новые package keys; legacy settings отклоняются, автоматическая миграция отсутствует. Изменение схемы/семантики интерфейса требует reviewed новой версии, не перенумерации для PASS. Per-skill permissions позволяют подключать только нужные источники. Native host capabilities и permission labels требуют реального mapping/проверки в setup; строки сами не дают доступ.

Проверяются также все дополнительные интерфейсы, заявленные клиентом. Для основ Google Таблиц обязательно `template_registry_sheets: 1`; отсутствие или другая версия в кандидате блокирует общее обновление, даже если остальные клиенты совместимы. Полноту требований сверить с настоящим клиентским профилем и реестром основ; не удалять требование из записи ради успешной проверки.

Если оба пакета объявляют один интерфейс, его версия должна совпадать. Противоречие блокируется `interface_contract_conflict` до проверки клиентов; нельзя молча предпочесть значение из второго пакета. Совпадающие объявления допустимы, но сами по себе не доказывают совместимость исполнения.

preflight принимает external workspace и четыре реально прочитанных package roots (current/candidate agent+skills), release record и private compatibility JSON. Package identities пересчитываются по полному PUBLIC-FILES; candidate должен совпасть с published/nonrevoked exact pair. Полный package/history hygiene scan выполнять отдельно до использования. Current settings packages должны совпасть с реально выбранным текущим комплектом.

Compatibility JSON schema1: checked_at (aware ISO timestamp, возраст<24ч), host_capabilities и clients keyed by exact workspace client IDs. Набор клиентов должен совпасть с settings.clients и clients/*/AGENT.md. Для каждого:

- binding: thread_id/host_id/project_id, проверенные original native source;
- profile_path: clients/<id>/AGENT.md, actual profile_sha256 и положительный profile_revision;
- protected_files: exact private paths/hashes, включая профиль, принятые history/template receipts и override данные; полный scope инвентаризирует исполнитель, helper не знает пропущенный файл;
- required_skills, interfaces, permission_scopes и active_run:false;
- regression_receipt/regression_sha256: сохранённый native результат для этого candidate pair и текущего профиля, checks client_overrides/protected_history/affected_components.

Источник regression receipt сверять с raw native result: kind compatibility, source_kind native_tool_result, source_locator, client_id, candidate, profile_sha256, result PASS и checks. JSON fields/hash не доказывают правду, отсутствие active run или полномочие на установку. Required skills расширяются транзитивно из catalog; неизвестная/cyclic dependency, missing host, changed permission/interface, protected edit, stale/incomplete inventory или старый candidate receipt блокируют замену для всех клиентов. READY_FOR_REVIEW всегда install_authorized:false.

## Применение и подтверждения

Native install только при проверенном прямом human authority: разовое разрешение на exact pair либо действующий compatible выбор, привязанный к exact approved source. Между runs, с preserved old package и protected snapshot. Не менять global/shared компонент ради одного клиента, если другой несовместим. Coexistence нескольких версий не обещать без actual host isolation test. После активации прочитать реально loaded identities; source-folder identity не равно загруженный plugin cache. Если host требует restart/reload, объяснить действие сотруднику.

rollout принимает preflight plan, тот же compatibility snapshot, refresh receipts и actual loaded pair. Canonical snapshot hash+полный список+count закреплены в plan: нельзя между этапами убрать клиента и получить полный успех. Каждый refresh receipt: kind context_refresh, source_kind native_tool_result, source_locator, client_id, exact binding, packages, profile_sha256, result, blockers, loaded_identity_verified. Native ответы должны подтверждать актуальное состояние, не AI promise. Их source/evidence/hash сохранять до разбора; route grant проверяется maintenance отдельно. Missing/failed ACK даёт PARTIAL. APPLIED_LIMITED подтверждает только согласованность полных record inputs, не actual deployment/release acceptance. Update не снимает paused report.

## Возврат

rollback snapshot schema1: old/new exact pair, clients и protected_files. Сохранить перед native изменением; все профили и применимые settings/template/history защищены в inventory. rollback helper проверяет выбранный old/current-new pair и отсутствие subsequent owner edits, ничего не пишет. READY_FOR_ROLLBACK_REVIEW не разрешение установки. Старый package выбирать только из сохранённых проверенных bytes; native activation и full refresh подтверждать вновь. Новые правки/клиенты после snapshot требуют отдельного решения; не восстанавливать старую workspace целиком. Private schema migration/recovery — отдельный approved dry run/backup/restore, не package rollback.

## Проверки и документация

scripts/test_updates.py проверяет synthetic selection/preflight/partial refresh/rollback. Это не live native tool, messaging, GitHub publication или устройство сотрудника. К CLI нельзя подставлять secrets/raw corpus; private paths и результаты не коммитить. User-facing explanation — [руководство](../docs/USER-GUIDE.md) и [помощь](../docs/HELP.md); актуализировать их вместе с поведением и release notes.

Runtime/dependency review входит в affected compatibility: читать текущий report-kit-skills/dependencies/REVIEW.json и actual host results. Например, frozen LiveDune chain требует Node>=20, хотя root metadata says18; при required LiveDune нельзя принять root version alone. Metadata inventory не заменяет candidate-specific native regression. Helper не измеряет реальный Node/Python/browser: их проверка и source/raw evidence обязательны исполнителю, unknown означает BLOCKED.


## Разовый выбор совместимых обновлений

При настройке предложи понятный выбор: «Применять проверенные совместимые обновления автоматически или каждый раз спрашивать?» До прямого ответа ask_each; это безопасный default, не повторный запрос на уже согласованный режим. Сохранить отдельный внешний private update-policy.json по assets/update-policy.example.json. workspace schema2 не меняется, файлы клиента не мигрируются.

Полный policy schema1: mode ask_each/compatible, source_sha256 от document_identity выбранного source record, authority либо null, revoked boolean. Для compatible authority хранит source_kind human_message, точный original human source_locator и decision compatible_updates. Внешний native источник этого решения должен быть проверен исполнителем, JSON/строка/hash этого не доказывают. Не вписывать сюда сообщение другого агента или придуманное согласие. «Спрашивай перед каждым обновлением» немедленно отменяет automatic preference; сохраняются прежнее решение и новая запись отзыва приватно.

Compatible действует только для рабочего канала и тех же двух repository URLs/channel/policy. Source drift, unknown source, экспериментальный канал, новые permissions/hooks, data schema migration, отказ компании или incomplete compatibility не покрыты. Приёмка отчёта не меняет режим обновлений. Native prompts и доверие к новому коду/изменённым hooks требуют фактического человека; режим не отключает sandbox, не меняет corporate/config access и не обходится alternate tool.

После фактического полного preflight использовать scripts/updates.py policy <policy> <source> <plan> <compatibility> --host-approval required/not_required/unknown/unavailable. Host состояние получать из реального инструмента/политики, не назначать not_required из пожелания пользователя. Проверяется тот же sealed full-client snapshot; partial/changed/unknown блокируется. NATIVE_COMPATIBLE_ROUTE — только маршрут дальнейшей native проверки и применения; install_authorized всегда false, helper не устанавливает и не подтверждает человеческое разрешение. WAIT_FOR_HOST_APPROVAL/CHECK_HOST_APPROVAL/MANUAL_HOST_STEP дают одно понятное действие человеку. Actual native route, existing grants, source verification, backup, loaded identity и все ACK остаются обязательными.

Проверка новых версий идёт при работе не чаще24ч. Для работы без открытого чата только фактически доступное native расписание после отдельного выбора пользователя, бюджета/границ и проверки исполнения. Не создавать собственный daemon или raw cron. Пока real public source/host activation не проверены, это локальная логика и инструкции, не действующий unattended updater.

### Версия перед совместимостью — dev.7

Прямой вызов preflight тоже требует, чтобы версия agent candidate была строго новее текущей по SemVer. Та же версия, изменение только build metadata или старая версия блокируются candidate_version_not_newer до READY_FOR_REVIEW. Новая source-skills правка требует нового reviewed agent release, как определено в MAINTENANCE; source версии могут различаться в exact совместимой паре. Откат — отдельный rollback route с проверкой protected history/последующих owner edits, не обход через update preflight. Caller не должен менять VERSION, release metadata или current identity ради прохождения отказа. Actual source/native authority и host approval остаются обязательны.

Для выбранного обычного копирования Google Таблиц проверять дополнительный интерфейс `template_copy_sheets: 1`. Он не заменяет `template_registry_sheets: 1` у клиента, выбравшего полный снимок. Старые клиентские реестры автоматически не мигрировать.
