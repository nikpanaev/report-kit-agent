# Сопровождение двух репозиториев

report-agent — source of truth общих правил и orchestration нового переносимого продукта. report-skills — source of truth его reusable source modules. Между этими двумя репозиториями код скиллов не дублируется; agent хранит dependency identity, не копию source skills.

Первый preparation snapshot — отдельная адаптация owner-maintained рабочего кода. Его existing installed copies и клиентский runtime не targets. Будущие изменения исходных рабочих скиллов не применять автоматически: сверить recorded origin hashes, прочитать exact diff, включить только необходимую portable правку, сохранить тесты/provenance и проверить весь affected scope. Не синхронизировать обратно в старые installed skills из нового репозитория без отдельного поручения.

Для принятого изменения агентских правил: scoped branch, изменить VERSION, обновить plugin mirror и compatible dependency descriptor, выполнить checks, записать evidence и локальный commit. Для source skill change — отдельный commit report-skills, catalog version при необходимости, provenance и affected/full regression, затем новое reviewed agent dependency identity. Номер нового месяца не версия пакета.

Сотруднику отдавать reviewed pair, не arbitrary main snapshots. Private workspaces/auth maps/sessions, owner client rules и completed reports остаются вне обновления. Не объявлять package hashes автоматическим invocation, подписью автора или live compatibility.

До public release: owner distribution license, независимый QA/security, реальные URLs и target-device install/update/rollback. Public Git author metadata тоже не содержит личный email; использовать согласованную публичную identity. При подготовке архивов/пакетов включать только exact source inventory, не .git, tool caches или ignored локальные данные.
