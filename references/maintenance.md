# Сопровождение без переноса чужих чатов

## Роли и настройка

Клиентский чат владеет своим отчётом/профилем. Координатор сопровождает общий процесс. Сопровождающий скилла отвечает за указанную capability и затронутые зависимости. Один связанный patch имеет одного редактора; не давать двум чатам одновременно править общий engine или Git index. Native thread tools и существующая единая UI-очередь — исполнительный контур, нового dispatcher/daemon нет.

Setup получает прямое поручение до создания чатов и ограниченное человеческое разрешение на конкретные двусторонние маршруты. Записывает только в выбранную private workspace `maintenance.json`, bindings, оригинальные locators человеческих поручений и receipts. Скиллы/чаты создаются по необходимости. Шаблон assets/maintenance.example.json пуст: он не готовая конфигурация и не authority. Никаких старых IDs, учётных записей или разрешений.

Реестр содержит `coordinator`, `maintainers` по exact skill ID, `clients` по client ID и `grants`. Client inventory должен совпадать с settings.json; неизвестный skill отсутствует до подключения. Binding: thread_id/host_id/project_id/receipt. Role receipt: exact role (`coordinator`, `skill:<id>`, `client:<id>`), те же три identity fields, source_kind=native_thread_read и source_locator. Оригинальный tool read подтверждает текущий чат/host/project и scope, а не одно название. Разные роли не привязывать к одному случайному чату. Комментарии VK и личные сообщения имеют отдельные роли.

Grant: id/origin/target/origin_binding/target_binding/actions/authority_ref/revoked. actions только request/callback/replay. В authority_ref сохраняется record с теми же fields кроме authority_ref, source_kind=human_message и source_locator прямого поручения. Пересылка другого агента не разрешает отправку обратно. Сверить оригинальный человеческий источник доступным native read, exact endpoints, scope и отзыв; JSON поля или PASS_LIMITED сами не доказательство. Полномочие на сообщения не разрешает редактуру общих исходников, установку, публикацию, новые credentials, расходы или снятие паузы. Для candidate patch нужен отдельный прямой write scope сопровождающего; его можно согласовать ограниченно при setup, не спрашивая вновь для того же scope.

## Как работать с проблемой

1. Определить bug/configuration/access/data_limit/capability. Сверить версии/контракт/вход/права/среду минимальным различающим тестом; ограничение данных или отсутствие доступа не чинить сменой метрики/движка. Клиентский агент не правит общую установленную копию.
2. Подготовить incident в private workspace: schema_version1, incident_id, origin/target roles, grant_id, classification, case_ref/case_sha256, source_sha256, budget {cap,started}, assets и events. Case содержит только expected/actual/reproducer/allowed_scope: короткие обезличенные технические данные. cap/started берутся из действующей задачи/ledger; максимум200 — технический потолок, не разрешение потратить200. Для операций без API оба значения могут быть0. Никаких новых ledgers ради обхода лимита.
3. Проверить registry и exact route. `python3 -B scripts/maintenance.py <workspace> --skills-root <skills-root> --origin <role> --target <role> --grant <id> --action request` даёт recipient и ограничения. Перед native send повторно сверить binding/человеческий источник и допустимый payload. Отправлять одну минимальную заявку, не corpus, ключи, cookies, профиль браузера, всю переписку или исходные личные обращения.
4. До send сохранить request_started в исходной истории. После завершённого tool result записать request_sent и ACK отдельно. При uncertain delivery/read timeout сначала читать исходный turn/receipt и ждать тот же handle; не пересылать дубликат и не создавать новый incident. Если адресат unknown/unavailable/busy, prepared/blocked/wait; не искать запасной чат. Дубли по incident_id сверять с историей, продолжать ту же заявку.
5. Сопровождающий проверяет полномочие и current source identity, сохраняет failure, готовит minimal candidate в разрешённом clone/task branch. Reproducer и affected regression обязательны; общие dependencies расширяют affected scope. Не менять oracle/threshold ради green. Git staging точный, чужие bytes/index сохраняются; несколько source repositories брать в согласованном порядке. Installed/cache файлы во время отчёта не targets.
6. Callback передаёт incident_id, cause, exact candidate commit/component SHA, checks, ограничения, budget и шаг повтора. `--action callback` выбирает recipient исходного чата, не сопровождающего. Общий candidate не активировать в обход [updates](updates.md): compatibility/approval/native install/loaded identity отдельно. Доставка callback оставляет awaiting origin verification.
7. Исходный чат перечитывает relevant SKILL, сверяет реально установленную identity, сохраняет старую историю и повторяет только проблемный шаг в текущем разрешённом scope/budget. Пауза сохраняется; исчерпанный бюджет требует решения человека. Successful replay закрывает incident, failed replay оставляет его открытым. Реплика «fixed», зелёные tests сопровождающего или совпавший hash не заменяют фактический replay.

## Записи и проверка

Event: id/kind/actor/receipt/receipt_sha256. Receipt содержит kind/incident_id/actor/source_kind/source_locator и только дополнительные fields своего kind. Не подделывать tool/human provenance; сохранять raw native outputs приватно по locators. Hash фиксирует bytes, не доверенность отправителя.

| kind | actor | additional receipt fields / requirement |
|---|---|---|
| request_started, request_sent | origin | none; STARTED перед native send, source_kind=local_attempt_ledger; sent после actual native result |
| acknowledged | target | none; actual ACK, не delivery |
| candidate_ready | target | fix_sha256, checks containing reproducer/affected_regression |
| callback_received | target sender | matching fix_sha256; origin прочитал actual callback |
| replay | origin | result PASS/FAIL, matching loaded_sha256, origin_paused=false, started_before/started_after |
| blocked, unblocked | origin | blocked: reason TARGET_BUSY/TARGET_UNAVAILABLE/PERMISSION_REQUIRED/OWNER_PAUSED; human unblocked для permission/pause |
| assets_received, assets_accepted | origin | exact assets inventory; acceptance source_kind=human_message после получения |

Case/receipt paths относительны workspace, не escape/symlink за её пределы; записи ограничены1MiB. Прошлый incident snapshot сохраняется неизменным. При каждом обновлении выполнить `python3 -B scripts/maintenance.py <workspace> --skills-root <skills-root> --incident <private-incident> --previous <previous-snapshot>`: неизменная основа и prefix events обязательны. Sealed case/receipt hashes защищают историю от незаметной замены. Добавление нового replay проверяется и против текущей pause registry. Старый завершённый replay не повторять из-за нового turn.

Read-only checker выдаёт consistency/state/next_action; ничего не отправляет, не меняет права, не устанавливает и не выполняет replay. Его PASS_LIMITED не верифицирует истину source_kind, полноту native history, grant authority, реальный бюджет, source loading или OS isolation. Эти проверки агент выполняет по первоисточникам до действия. Без actual native messaging на выбранном устройстве подготовить обращение и явно показать ограничение.

## Файлы, удобство и внешний канал

Asset fields: path/sha256/purpose (`proof` или `report`). Report asset должен существовать с exact hash до подтверждённого получения и человеческой приёмки; proof-only receipt с hash удалённого PNG не материал отчёта. Не выдавать недоступные paths как готовый результат. После приёмки очистить только известные task temporaries с receipt/hash; источник, финал, raw проверки и нужные recovery данные сохраняются.

Пользователю показывать существенный итог и один конкретный вопрос, если он нужен. При known разрешённом маршруте не спрашивать повторно. При необходимости нового permission/budget/install показать подготовленный результат и точную причину остановки. Local incident/technical receipts не выгружать на GitHub. Перед отдельным upstream issue получить прямое разрешение на конкретный обезличенный payload; чужой аккаунт и ваши старые чаты не native получатели сотрудника. Новый source skill добавляется в catalog и локальный role registry после выбора, без рассылки всем чатам.

Для VK повтор содержит bounded stage/error_type (preflight/navigation/browser_setup/capture) без сообщения exception. Сверять исходную строку с разрешённым private log; классифицировать этап, не восстанавливать старую причину по догадке. Терминальные сообщения/прочие logs не объявлять очищенными: incident по-прежнему минимальный и обезличенный, секреты/корпус не отправлять. Наличие этапа не source authority, root-cause closure, callback или успешный origin replay.

## Передача сведений владельцу Report Kit

По просьбе пользователя готовить один local ZIP по [support](support.md), без native send и без raw incident/receipts. При actual request/acknowledgement/replay/recovery сохранять безопасный служебный переход существующей истории: фиксированный stage/result/error, случайный support operation UUID. Binding, incident ID, адресат, grants, source locators и свободный case text в этот store не передавать. Не записывать success до native readback; неизвестный результат — unknown. Старый incident journal остаётся локальным recovery record; задним числом его в архив не импортировать.
