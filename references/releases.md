# Подготовка локального выпуска

Текущая пара — dev.30/dev.21, среда python312-20261013-v3 без NumPy. Для Windows включены точные условия получателя и проверка исходного Python LICENSE.txt. prepare_release проверяет также хеш текста согласия; бинарные архивы v3 повторно не меняются. Лицензионное основание предъявлено владельцу по [LICENSE-STATUS](../LICENSE-STATUS.md); юридическую приёмку не отмечать автоматически. Старые разделы с версиями v2 ниже — исторические.

Этот workflow готовит проверяемый локальный черновик. Он не создаёт GitHub Release, remote, tag, расписание, установку или сообщение сотруднику. Для этих действий требуется отдельное полномочие. Release source должен быть утверждённым; не использовать произвольный main или изменённую installed copy.

## Принятый маршрут проверки пакетов

14.10.2026 владелец принял отдельную проверку готовой пары Report Kit по точным коммитам, архивам и применимым QA/security/licensing evidence. Сотруднику не нужны файлы и инструменты каркаса разработки. Сначала проверить source identities, VERSION/mirrors и dependency hash; затем весь PUBLIC-FILES и применимые tests/прежние FAIL; после clean task commits — полный состав и bytes двух архивов, LICENSE, SHA256SUMS и build-record. Каждая новая сборка выбирает собственные exact identities.

Документ о маршруте, source scanner и LOCAL_DRAFT_NOT_APPROVED не являются независимой приёмкой или разрешением выпуска. Сохраняются отдельные QA/security/licensing решения, фактическая packaged/employee проверка по scope, actual host approvals и owner release authority. Не подставлять временные управляющие файлы/версии ради зелёной проверки, не принимать старые claim failures автоматически и не выдавать родительский проект за проверку публичной пары. Старые результаты developer tools сохранять с их исходными identities; их структурная неприменимость не закрывает product failures.

[Решение о маршруте](../evidence/package-route-decision.json) действует для данной архитектуры; пересмотреть при изменении архитектуры, состава поставки/bundling, обязательных release controls или принятии подходящего нового developer checker. Публикация, установка и независимая приёмка этим решением не разрешены.

## Текущая подготовка

Для dev.28/dev.19 подготовлена среда v2 с python/REPORT-KIT-NOTICES.zip внутри core. Исходные binaries сохранены; manifest/receipt и хеши архивов изменились. Рецепт закрепляет notice_package; prepare_runtime проверяет исходный файл уведомлений, prepare_release требует непустой точный список платформ рецепта, core каждой платформы и совпадение обязательного ZIP с рецептом и manifest. Уведомления нельзя убрать ради уменьшения архива. Исходный supplemental ZIP сопровождающий получает из проверенного core; он не требует от сотрудника отдельного действия.

Локальный кандидат не готов к внешней передаче до решения [лицензионных вопросов](../LICENSE-STATUS.md). Правообладателя, подпись, новые права и юридическое согласие нельзя вывести из одного SHA256 или переданного JSON. Windows проверит сотрудник после отдельного разрешения тестового выпуска.

## Порядок

1. Выбрать согласованные изменения и exact pair report-kit-agent/report-kit-skills. Прочитать весь diff, provenance и применимые прежние FAIL. Обновить VERSION, plugin/contracts/catalog mirrors, dependency hash, CHANGELOG, руководство/помощь и affected tests. Версии и совместимость проверять до упаковки.
2. Пройти public inventory/history hygiene, source/dependency/license review и применимые проверки. Source scanner не независимая privacy приёмка. Unknown/unreviewed материалы не объявлять безопасными; не копировать client workspace, keys, sessions или installed cache в пакет.
3. Сохранить изменения локальными task-owned коммитами, подтвердить clean roots. Получить полные40-symbol commit IDs каждого repo. scripts/prepare_release.py упаковывает именно их штатным Git archive. Выбрать новый external private output вне обоих пакетов: существующая папка не перезаписывается.
4. Helper проверяет clean HEAD/committed PUBLIC-FILES, оба package/history checks и dependency pair, затем сверяет каждый tar entry/байты с inventory. Имена/пути, links, изменённые bytes, export-ignore/subst или moved source выявляются проверкой. Read-only ignored caches и .git не экспортируются. После assembly повторная проверка HEAD/working tree; существующие чужие данные не удаляются.
5. Результат: два .tar, draft-release.json (published:false), RELEASE-NOTES.md, SHA256SUMS и build-record.json. LOCAL_DRAFT_NOT_APPROVED значит local byte preparation, не право публикации, установка, совместимость каждого клиента или independent release pass. Не выполнять downloaded scripts ради чтения пакета. При ошибке частичные собственные outputs сохранить по точному inventory до разбора.
6. Разобрать blockers по текущему EVIDENCE-INDEX и реальным решениям reviewers: license/rights, independent QA/security, актуальные воспроизводимые ошибки выбранной версии, packaged/host/update/rollback checks, privacy/employee account, real repository URLs. Static helper reminders не подменяют актуальное состояние gate. Review самого поставляемого архива обязателен; исходные tests его не заменяют.
7. После отдельного разрешения на exact публикацию использовать native GitHub tools/CLI, не собственный uploader. Сначала skills release с точным архивом, затем agent release с exact pair. Передавать только approved публичные notes/artifacts. Дождаться actual native readback tag/assets/digest/channel: отправка запроса не успех. Если исход неизвестен, readback исходного handle до повтора. Не публиковать частично совместимую пару как рабочую.
8. Approved общий release index хранить в report-kit-agent, append-only release records по согласованному каналу. Не считать latest полным списком prereleases и не менять старые versions/bytes. Recall/revocation фиксировать отдельно; клиент не устанавливает revoked package. Установка и complete client compatibility/refresh — [отдельный workflow](updates.md).

## CLI для сопровождающего

`python3 scripts/prepare_release.py --agent-root <agent-root> --skills-root <skills-root> --agent-commit <exact40> --skills-commit <exact40> --output <new-external-output> --channel working`

Команда сама сеть не читает, GitHub не изменяет и загруженный код не исполняет. Helper использует локальные проверочные модули этой выбранной версии. Выходы могут занимать место: ненужные проверочные архивы удалять после compact path/hash/result receipts; candidate, нужный незавершённому review/rollback, сохранять. Private debug receipts и служебные bindings не добавлять в GitHub assets.

## Регулярность и удобство

Предлагаемая периодичность — раз в неделю при принятых изменениях; важные fixes отдельно. Сборка нового месяца не требует нового release. Пока нет approved source/лицензии/publication scope, расписание и внешние draft writes не активировать. После этих решений использовать штатную automation/manual GitHub workflow с ограниченными правами и exact tested heads. Эта локальная подготовка не обещает действующую CI или unattended публикацию.

Release notes простым языком: что стало доступно, что исправлено, затронутые источники/доступы, совместимость и действие сотрудника. Если действий нет, не вынуждать его перенастраивать аккаунты. Подробности/source receipts остаются у сопровождающего; помощь сотруднику — [здесь](../docs/HELP.md).

[Git archive](https://git-scm.com/docs/git-archive), [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository), [native CLI draft option](https://cli.github.com/manual/gh_release_create).

Source/dependency review preparation: report-kit-skills/THIRD-PARTY-DEPENDENCIES.md и dependencies/REVIEW.json содержат declared labels/integrity/engines, не автоматический license PASS. При изменении frozen dependency graph/поставки повторить проверку; current Node20/transitive Python/esbuild/platform ограничения не скрывать в release notes.

## Проверка скачанного тестового выпуска

Передать пользователю именно архивы проверенной пары. В репозиториях сопровождающего проверить историю через check_package.py --history; prepare_release.py делает это обязательно. После распаковки вне любого Git-репозитория выполнить обычную проверку состава/версий/зависимости без --history. NOT_CHECKED_ARCHIVE не означает проверку Git-истории или доверенность источника: origin, commit и SHA256SUMS сверяются с согласованным выпуском отдельно. Не создавать .git и не копировать чужую историю для обхода проверки. Тестовая публикация требует отдельного разрешения; пользовательская проверка скачанного выпуска предшествует решению о поддержке Windows/рабочем выпуске.

## Доставка по одной ссылке

Перед публикацией сопровождающий заполняет **оба** реальных repository URLs в assets/update-source.example.json поставляемого agent (и согласованный channel); сотруднику не поручается этот выбор. Источник находится в первоначально доверенной поставке agent, не берётся из случайного сообщения или main. После изменения metadata пересчитать identity, commit и архив штатным prepare_release. Публичная ссылка пользователю ведёт только на report-kit-agent.

prepare_release теперь дополнительно создаёт draft-delivery.json из точных tar SHA256, размеров, tag v<VERSION> и source commits. --source принимает утверждённый record; без него URLs null и доставка заблокирована. Draft всегда published false, даже при заполненных URLs. Публикация отдельно: разрешённый сопровождающий размещает оба immutable assets в соответствующих releases, сверяет tags/full commits и downloaded asset readback, затем публикует delivery.json и release index **как assets agent release**. Из main их для установки не читать. Запись published true делается только после фактического опубликования; локальный build этого не утверждает. Релиз пары не подменять по старому номеру. Неизменный skills пакет может переиспользоваться из прежнего опубликованного exact release.

До внешнего теста отдельно проверить настоящий native download/redirects, install по точному source, loaded identities, update/rollback и сотрудника/Windows. Локальная подготовка не требует устанавливать комплект у разработчика. Старые семь исправлений аудита остаются в test/regression scope; source-skills не обновлять ради одного изменения orchestration.

## Отдельные файлы переносимой среды

[Runtime workflow](runtime.md) — принятый расширенный состав поставки. prepare_runtime собирает проверенные upstream files, prepare_release --runtime-assets включает exact assets в общий local draft, delivery и SHA256SUMS. Не класть binaries в исходный Git и не ослаблять source scanner. Before publication: новая полная проверка licenses/notices/platform binaries, independent controls и native employee tests. Текущая подготовка этого не заменяет.

## Проверка метаданных приложения перед внешним тестом

Местный check_package.py проверяет состав и собственные контракты, а не всю схему установщика Codex. По [официальному описанию метаданных OpenAI](https://developers.openai.com/plugins/deploy/submission#icons-and-screenshots) нужны logo/composerIcon: оба пути теперь указывают на включённый собственный квадратный SVG в assets. В текущей поставке используются только текстовые SVG; добавление иных форматов потребует отдельной узкой проверки и исключения из запрета бинарных файлов. Проверяются наличие, граница пути, XML/viewBox и размер; это не независимый анализ любого SVG. Штатная проверка и установка здесь не выполнялись. Не объявлять успешный source checker проверкой установки. Публикация в общий каталог и частное подключение имеют отдельные условия.

Для включения уже проверенных архивов среды передать prepare_release.py дополнительный аргумент `--runtime-assets <prepared-runtime-folder>`. В этой папке нужны неизменённые восемь архивов и runtime-build.json, который создал prepare_runtime.py. Рецепт сборки: `python3 scripts/prepare_runtime.py --recipe assets/runtime-recipe.json --downloads <verified-downloads-folder> --output <new-runtime-folder>`. Это команды сопровождающего, не сотрудника; загрузки предварительно сверяются с recipe. Повторно собирать и скачивать ту же среду только ради документной правки не нужно: повторное использование разрешено после проверки каждого размера/hash и сохранения первоначальных результатов в их версиях. Новая delivery запись всё равно связывается с новой парой пакетов.
