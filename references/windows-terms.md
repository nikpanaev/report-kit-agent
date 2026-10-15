# Условия компонентов Microsoft в Windows-среде Report Kit

Эта страница относится только к компонентам Microsoft внутри поставляемого Python для Windows. Report Kit и ваши отчёты не становятся собственностью Microsoft. Устанавливать Visual Studio или Python самостоятельно не нужно.

Для работы используется Python с сохранёнными исходными условиями. Агент покажет полный текст и спросит: **«Разрешаете подготовку компонентов Report Kit и принимаете эти условия?»** Достаточно ответить **«да»**. Если ответ — «нет» или условия не подходят, агент сохранит выполненные шаги и не запустит эту среду. При неизвестном ответе он уточнит вопрос. Согласие с автоматическими обновлениями не заменяет это подтверждение.

При использовании и дальнейшей передаче компонентов Microsoft вы соглашаетесь соблюдать исходные условия: сохранять уведомления о правах, не создавать впечатление одобрения Microsoft, использовать эти компоненты только на платформах Microsoft и не включать их во вредоносные, обманные или незаконные программы. При дальнейшей передаче получатель также должен согласиться с условиями, защищающими компоненты Microsoft не меньше, чем исходные требования. Не распространяйте DLL отдельно от поставляемого Python. Лицензии остальных частей Python остаются в его LICENSE.txt; собственный код Report Kit — под MIT.

## Исходный текст из Python

[CPython 3.12.15, PC/crtlicense.txt](https://github.com/python/cpython/blob/v3.12.15/PC/crtlicense.txt). Текст ниже сохранён без изменения; весь LICENSE.txt входит в Windows-архив среды.

```text


Additional Conditions for this Windows binary build
---------------------------------------------------

This program is linked with and uses Microsoft Distributable Code,
copyrighted by Microsoft Corporation. The Microsoft Distributable Code
is embedded in each .exe, .dll and .pyd file as a result of running
the code through a linker.

If you further distribute programs that include the Microsoft
Distributable Code, you must comply with the restrictions on
distribution specified by Microsoft. In particular, you must require
distributors and external end users to agree to terms that protect the
Microsoft Distributable Code at least as much as Microsoft's own
requirements for the Distributable Code. See Microsoft's documentation
(included in its developer tools and on its website at microsoft.com)
for specific details.

Redistribution of the Windows binary build of the Python interpreter
complies with this agreement, provided that you do not:

- alter any copyright, trademark or patent notice in Microsoft's
Distributable Code;

- use Microsoft's trademarks in your programs' names or in a way that
suggests your programs come from or are endorsed by Microsoft;

- distribute Microsoft's Distributable Code to run on a platform other
than Microsoft operating systems, run-time technologies or application
platforms; or

- include Microsoft Distributable Code in malicious, deceptive or
unlawful programs.

These restrictions apply only to the Microsoft Distributable Code as
defined above, not to Python itself or any programs running on the
Python interpreter. The redistribution of the Python interpreter and
libraries is governed by the Python Software License included with this
file, or by other licenses as marked.

```
