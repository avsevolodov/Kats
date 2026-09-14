# Требования

Статус: готово для декомпозиции и compatibility gates; не свидетельство runtime готовности.

## Пользовательские истории

US1. Пользователь спрашивает об архитектуре или обсуждает идею, не выбирая репозиторий.
US2. Пользователь описывает проблему; агент находит доступный репозиторий, проверяет контекст, фиксирует SHA и поручает изменение Coding Agent.
US3. При неоднозначности агент задаёт понятный предметный вопрос и продолжает после ответа.
US4. Пользователь видит прогресс, отвечает на permission, закрывает браузер и возвращается к тому же результату.
US5. Пользователь спрашивает статус или уточняет цель во время выполнения.
US6. Перезапуск Chat Agent/API/worker не создаёт повторный coding invocation.
US7. Отмена прекращает новые дочерние действия и запрашивает остановку текущих.

## Functional requirements

| ID | Требование |
| --- | --- |
| FR-201 | Conversation и Message не требуют RepositoryId; MessageId/CommandId устойчивы при повторе |
| FR-202 | Chat Agent выбирает ответ, уточнение или делегирование; UI не строит prompt исполнителя |
| FR-203 | Каталог возвращает только доступные репозитории; selection содержит evidence и immutable commit |
| FR-204 | Все внешние tools и дочерние agents Chat Agent вызываются через авторизованную шину |
| FR-205 | Invocation имеет parent, стабильный ключ дедупликации, версию capability и структурированный result |
| FR-206 | coding.execute адаптируется к существующему Run; один invocation соответствует не более одному Run |
| FR-207 | LangGraph checkpoints и pending writes сохраняются вне pod; single writer защищён fence/CAS |
| FR-208 | Повтор восстановления не повторяет уже принятый дочерний вызов; неопределённый исход не скрывается |
| FR-209 | Interaction различает clarification и approval; решение связано с точным request и его hash |
| FR-210 | Conversation stream имеет собственный cursor; result durable, preview bounded |
| FR-211 | Одна активная task на conversation; новые сообщения имеют явный disposition и revision |
| FR-212 | Cancel cascade, completion race и deadlines имеют однозначную семантику |
| FR-213 | Follow-up после завершения создаёт новую task; контекст/patch передаются явно, workspace не предполагается живым |
| FR-214 | Выбор модели конфигурируемый, версии закреплены; тестируется реальное tool calling внутренних моделей |
| FR-215 | Existing Run API и artifacts доступны при отключённом новом chat flow |
| FR-216 | On-prem, MSSQL, Temporal, mTLS/OIDC; секреты не входят в prompt/checkpoint/stream |
| FR-217 | Chat Agent принимает terminal tool result как данные; финал различает changes prepared, checks passed, checks not run |

## Начальные ограничения

Значения конфигурации, а не обещание производительности:
- 10 активных tasks на окружение, 1 активная task и 1 writer графа на conversation.
- Не более 1 одновременно исполняемого coding child на task; до 3 последовательных coding вызовов.
- До 30 tool invocations и 40 model calls на task, лимит длительности model call 120 s.
- Иерархия первой поставки: Chat Agent → registered tool/Coding Agent. Произвольная рекурсия выключена.
- Пользовательское сообщение ≤32 KiB UTF-8; tool input ≤64 KiB; большие результаты через artifact references.
- Task wall deadline 24 h; clarification TTL 24 h, но не позже deadline task.
- Coding Run сохраняет baseline deadline 20 min, включая OpenCode approval; approval TTL ≤5 min и остатка Run.
- Chat preview ≤2 MiB на task; bounded artifacts и patch limits baseline 001 сохраняются.
- Лимиты enforcement на сервере, превышение даёт BUDGET_EXCEEDED и известный итог либо NEEDS_ATTENTION при неизвестном эффекте.

## Первая приёмка

Фраза «В Kats после переподключения пропадает прогресс. Найди причину и подготовь исправление» без RepositoryId приводит к выбору Kats с evidence, фиксации SHA, одному coding Run, patch и честному отчёту о проверках.
Второй репозиторий с похожим именем вызывает уточнение, если evidence не позволяет выбрать.
Запрос «Как работает доставка событий?» может завершиться ответом без coding Run.
