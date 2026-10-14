---
name: report-release-prep
description: "Подготовить локальный черновик выпуска общих report-agent/report-skills: exact committed pair, проверенный состав архива и понятные заметки. Не сборка клиентского отчёта; публикацию и установку не разрешает."
---

# Черновик выпуска

Прочитай [release preparation](../../references/releases.md), текущие VERSION/dependencies/CHANGELOG и EVIDENCE-INDEX обоих выбранных source packages. Не изменять существующих клиентов или installed copies. Сверить direct scope, diff и pending/failed evidence; не принимать risk/review за владельца.

Использовать scripts/prepare_release.py с exact clean committed pair и новым external task-owned output. Никаких secrets/raw client data, source self-modification при сборке или перехода на main. Сначала применимые реальные проверки; формальные hashes/JSON/schema не approval. Черновик всегда published:false, blocker/limitations сохранить.

Показать сотруднику короткие notes и что осталось перед выпуском. Отдельное разрешение на native GitHub draft/publication, tag/push/remote/install/расписание не выводить из подготовки. Uncertain external writes не повторять без readback. Ненужные local build exports удалить после receipt, материалы текущего review/rollback сохранить.
