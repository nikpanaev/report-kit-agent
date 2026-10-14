# Сопровождение двух репозиториев

report-kit-agent — source of truth общих правил и orchestration нового переносимого продукта. report-kit-skills — source of truth его reusable source modules. Между этими двумя репозиториями код скиллов не дублируется; agent хранит dependency identity, не копию source skills.

Первый preparation snapshot — отдельная адаптация owner-maintained рабочего кода. Его existing installed copies и клиентский runtime не targets. Будущие изменения исходных рабочих скиллов не применять автоматически: сверить recorded origin hashes, прочитать exact diff, включить только необходимую portable правку, сохранить тесты/provenance и проверить весь affected scope. Не синхронизировать обратно в старые installed skills из нового репозитория без отдельного поручения.

Для принятого изменения агентских правил: scoped branch, изменить VERSION, обновить plugin mirror и compatible dependency descriptor, выполнить checks, записать evidence и локальный commit. Для source skill change — отдельный commit report-kit-skills, catalog version при необходимости, provenance и affected/full regression, затем новое reviewed agent dependency identity. Номер нового месяца не версия пакета.

Сотруднику отдавать reviewed pair, не arbitrary main snapshots. Private workspaces/auth maps/sessions, owner client rules и completed reports остаются вне обновления. Не объявлять package hashes автоматическим invocation, подписью автора или live compatibility.

До public release: owner distribution license, независимый QA/security, реальные URLs и target-device install/update/rollback. Public Git author metadata тоже не содержит личный email; использовать согласованную публичную identity. При подготовке архивов/пакетов включать только exact source inventory, не .git, tool caches или ignored локальные данные.

Сопровождение employee runtime: [contract](references/maintenance.md), report-kit-maintenance и scripts/maintenance.py. Единственный источник ролей/grants/incidents — private workspace; source repos не сохраняют bindings/callback историю. Компонент candidate исправляется в отдельной разрешённой branch, а installed/cache activation проходит compatible native update. SOURCE_FACT/JSON receipt/hash не независимое доказательство human authority или actual replay. Новый скилл включается в catalog, role registry и regression matrix без копирования старых адресов.

## Пользовательская документация

[Руководство](docs/USER-GUIDE.md), [помощь](docs/HELP.md) и report-kit-help входят в тот же проверяемый пакет. При изменении поведения обновить затронутые разделы и примеры в этой же правке, проверить локальные ссылки и соответствие реальным ограничениям. В заметках выпуска кратко указать, что изменится для сотрудника и что ему нужно сделать. Внешние страницы/чат-бот/отдельный сайт помощи сейчас не нужны: не дублировать инструкции и не создавать ещё один контур обновлений. Behavioural testing на устройстве и понимание сотрудником остаются отдельными проверками, не следуют из проверки Markdown.

Для reviewed pair готовить локальный черновик через [release workflow](references/releases.md); exact committed archive/inventory/draft notes отдельно от actual publication approval. CHANGELOG и помощь входят в тот же package.
