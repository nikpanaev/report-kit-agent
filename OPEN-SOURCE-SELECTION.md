# Capability selection — offline preparation

| Capability | Selected level/source | Reason / boundary |
|---|---|---|
| Agent/runtime | Existing Codex instruction and native plugin mechanism | No new app/model SDK/runner; actual host install deferred |
| Plugin distribution/setup | Official native plugin manifest/local marketplace/onboarding skill | Portable package prepared; no custom installer/updater or public URL |
| Native Docs/Sheets/Slides | Available connected Google plugin and artifact skills | Employee connects own account; source not copied/vendored; current access checked at use |
| Reporting workflows | Owner-maintained process + generic skill adaptation | Separate future-client product; private profiles/history/source Git excluded |
| Template pre-copy/history checks | Existing offline check_report_templates.py | Reused complete schema3 guard and its synthetic suite; no weakened role/history/approval tests |
| Basic package/workspace checks | Python standard library | Minimal own project-specific inventory/path/dependency checks; not installer, security scanner or permission sandbox |
| Maintenance routing / incident evidence | Native Codex thread tools plus readonly stdlib contract guard | No custom dispatcher/server; exact role/authority and append-only receipt consistency are domain-specific. Human/native source verification remains separate |
| Source capabilities | Separate report-kit-skills package | One canonical public-pair source; exact version/content pin, not main |

Official plugin package reference: https://developers.openai.com/plugins/build/plugins . Documentation checked2026-10-14. Native host/schema loading and distribution integration remain unverified until target runtime tests.

Tooling versions used are recorded in local evidence, not vendored. Owner-maintained adaptations use MIT, copyright Report Kit; third-party notices/compatibility review remains pending. No download/install authority implied by selection. All future third-party upgrades require canonical version/license/provenance, permission/data review and compatibility test; stars/popularity are not acceptance.

## Bootstrap и обновления по одной ссылке

Повторно использовать scripts/updates.py, check_package.py, prepare_release.py и штатные native GitHub/HTTP/plugin tools. Python stdlib tarfile/hashlib нужны только для проверки и инертного staging по exact public inventory; downloaded code не запускается. Отдельный package manager/installer, daemon или сторонняя auto-update библиотека отклонены: они дублируют имеющийся native путь и добавляют границы доверия. Native шаг доступен не на каждой поверхности: подготовить минимальное подтверждение в приложении, не обходить его. Реальная совместимость штатной активации/возврата ещё требует device test.

## Диагностика для поддержки

Повторно используются существующие переходы request/retry/queue/maintenance/check. Их raw logs не пересылаются. Python stdlib json/uuid/zipfile/pathlib и Node fs/crypto достаточны для фиксированных полей и ZIP. Сторонняя telemetry/crash-reporting библиотека, сервер или универсальный сборщик компьютера не нужны и добавили бы передачу данных/зависимости. Два языка пишут один versioned allowlist; collector/policy экспортируются в agent побайтно, а не сопровождаются как две реализации. Запасной способ — тот же collector из новой выбранной private папки, без агента, сети или реальной установки.

## Переносимая среда — принято 15.10.2026

Используется готовая CPython3.12.15 python-build-standalone20261013, exact wheels и официальный Node24.21.0. Recipe/платформенные assets сопровождаются report-kit-agent; нового package manager/daemon/второго установщика нет. Для первой подготовки без Python — нативные shell/PowerShell helper, только проверенная inert распаковка. Зависимости собираются без pip/lifecycle execution, internal vendor links нормализуются в обычные файлы и проходят прежнюю archive path/collision проверку. Source archives по умолчанию остаются strict UTF-8; отдельный binary mode только для проверенного runtime. Native browser installation оставлена штатному Playwright после отдельного согласия. Полный license/NOTICE inventory в agent/assets/runtime-notices.json и самих runtime assets; независимое решение о распространении не подменяется сборкой.
