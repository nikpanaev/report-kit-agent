# Обновление и откат

Обновляются package инструкции и код, не клиентские данные/отчёты. Проверка наличия новых версий не разрешает установка, выполнение downloaded hooks или переход на main.

- Между отчётами проверить утверждённый source/release, exact agent version и совместимую report-skills identity. Пока public source не задан, использовать явно выбранные локальные копии; не придумывать URL, release signature или signer trust.
- Показать diff, changed capabilities/permissions, известные ограничения, проверенные license/provenance и связанные версии. Secrets/auth/provider/updater изменения требуют отдельного review. Hash доказывает совпадение, не доверенность автора.
- Получить разрешение на exact обновление, сохранить old package identities и локальную возможность отката. Native plugin installation route предпочтительнее собственного updater. Не запускать update посередине активного run.
- Package read-only; workspace path отделён. Не делать массовый search/replace профилей. Новый общий процесс не отменяет принятые клиентские правила и не мигрирует workspace schema автоматически.
- Для явно разрешённых собственных клиентских чатов отправить context refresh только при direct human authority. Каждый адресат перечитывает common files и свой профиль, сохраняет прежний receipt, подтверждает actual new identity и blockers. Delivery не ACK. Общий update не запускает отчёт, сбор данных, browser UI или sharing.
- Откат выбрать по сохранённой identity после проверки, что нет последующих owner edits. Не изменять reports, source snapshots, Google permissions или browser sessions. После отката снова подтвердить identity и refresh собственных явно разрешённых чатов.
- При несовместимости или missing receipt результат BLOCKED/PARTIAL. Не ослаблять checks, не менять dependency pin ради green; сохранить failed attempt и исправить причину в разрешённом scope.

Distribution URLs, release signing/hosting и live update/rollback на новом устройстве ещё не проверены. После отдельного решения о публикации проверить настоящий install/update path, а не только file hashes.
