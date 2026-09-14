# UX диалогового Kats

Главная страница — список диалогов и выбранный чат. Поля Repository/Commit/Runner не являются обязательной формой входа.

## Компоненты

- ConversationsList: заголовок, last activity, unread/pending indicator.
- MessageList: user/assistant, draft answer, final response, ссылки на источники.
- Composer: текст, send, остановка активной задачи; idempotent retry после network error.
- TaskProgressCard: текущая цель, краткий план, статус, дочерние действия.
- ContextCard: выбранный сервис/репозиторий и основание; SHA в раскрываемых деталях.
- InteractionCard: предметный вопрос либо точное действие с once/reject.
- ArtifactCard: summary/patch, checks passed/failed/not_run, expiry.
- DiagnosticsDrawer: RunId/InvocationId и технические события для диагностики.

Существующую Run detail оставить доступной из DiagnosticsDrawer. Каталог репозиториев — отдельный административный экран с правами.

## Поведение

Агент пишет понятные статусы: «Проверяю обработку переподключения», «Передал задачу исполнителю».
Каждый token child не превращается в отдельное сообщение; progress карточки обновляются.
Финальный ответ содержит что сделано, что проверено и ссылку на результат. SUCCEEDED не маскирует not_run checks.
Чат доступен после закрытия страницы. Reconnect banner не предлагает запускать задачу снова.
При queued/steer_pending сообщение помечено «Учту после текущего шага»; после InputApplied отметка меняется.
При нескольких approvals каждая карточка имеет собственное действие; group approve отсутствует.
Неизвестный исход: «Связь с исполнителем потеряна; результат действия не подтверждён». Кнопка нового запуска не создаётся автоматически.
Отмена показывает CANCEL_REQUESTED до подтверждённого результата, а не мгновенный CANCELLED.

## Первые сценарии browser acceptance

1. Отправить запрос без выбора repo; увидеть evidence и coding progress.
2. Ответить на clarification, обновить страницу, увидеть тот же decision.
3. Разрешить once, получить saved и applied как разные состояния.
4. Открыть чат во второй вкладке: один execution, идентичная история.
5. Обрыв WebSocket: REST fallback, восстановление cursor без duplicate messages.
6. Follow-up к patch после потери runner: новый task с явным predecessor artifact.
7. Keyboard navigation/focus к вопросу, текстовые labels статусов, экранирование markdown/HTML.
