# Передача сотруднику

## Что уже подготовлено

Два локальных package/plugin репозитория с отдельными VERSION и чистой исходной историей. Здесь общие инструкции и setup, в report-skills reusable source modules. Существующих клиентов/аккаунтов/чатов/готовых отчётов внутри нет.

## Будущий путь сотрудника

1. Получить настоящий утверждённый distribution link report-agent после публикации; сейчас public URL отсутствует.
2. В поддерживаемом Codex попросить подключить report-agent. Агент читает README/manifest и запрашивает разрешение до установки; не запускает скачанный shell автоматически.
3. Setup проверяет compatible report-skills version/content identity, рабочую область вне пакетов, доступные tools и показывает только действительно missing inputs. Способ установки проверить на целевом устройстве.
4. Выбрать private workspace. Google/LiveDune/соцсети подключать при первой необходимости под своими разрешёнными аккаунтами. Никаких импортированных keys/cookies/sessions.
5. Подключить первого нового клиента: папка/образец/источники/период, agreed profile, pilot и отдельная base-template acceptance. Затем отдельный новый чат только по прямому поручению.
6. Проверить полный control report и принять результат. Только это подтверждает end-to-end перенос для выбранного устройства/account.

## До публикации

- Выбрать distribution license, подтвердить права на исходники и dependency notices.
- Разобрать нестабильную синтетическую проверку VK rate limit: cold full run failed, isolated pass не отменяет failure. Не ослаблять pacing/no-retry/partial-source oracle.
- Independent QA/security, current plugin schema/host install, target-device/account/capability/permission checks, controlled update/rollback и cleanup drill.
- Задать real public URLs/exact release identities; повторно проверить весь Git payload/history на личные данные, secrets и raw artifacts. Не публиковать эту preparation автоматически.

## Обновление / поддержка

Сначала reviewed agent+skills pair, потом разрешённое обновление между заданиями. Client workspace сохраняется, no automatic migration. Exact old identity для отката; source snapshot не переписывать ради успешной проверки. При полномочиях на employee disconnect отзыв service grants/key и удаление его локальной сессии выполняются отдельно, не Git update.

Эти инструкции не обещают отсутствие технических настроек на ещё неизвестной ОС. Устройство, account permissions и живые сервисы остаются проверяемыми входами.
