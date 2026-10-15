#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if [ -f ./runtime-python.txt ]; then
  IFS= read -r rk_support_python < ./runtime-python.txt
  "$rk_support_python" -B ./scripts/support_bundle.py --saved-state --open-folder
elif command -v python3 >/dev/null 2>&1; then
  python3 ./scripts/support_bundle.py --saved-state --open-folder
else
  printf '%s\n' 'Не найден компонент для сбора файла. Сообщите поддержке код SUPPORT_PYTHON_MISSING. Ничего не отправлено.'
fi
