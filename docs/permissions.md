# Согласование действий OpenCode через UI

Этап после MVP: владелец Run отвечает «Разрешить один раз» (`once`) или
«Отклонить» (`reject`). Решение сохраняется в MSSQL до передачи OpenCode.
Нет blanket allow, `always`, повторного prompt и автоматического повтора неизвестного
результата permission reply. Статус «решение сохранено» отличается от «ответ передан».

## Обновление существующего стенда

1. Остановите API/Worker/runner после завершения активных задач.
2. Выполните `sql/004-permissions.sql` в прикладной базе KatsDev через SSMS/Rider.
   Скрипт повторяемый, данные не удаляет. Новая установка через 001 включает таблицу.
3. Пересоберите API и Worker в Windows/Rider. Сохраните ваши Windows appsettings.
4. На стороне runner (WSL) выполните `uv sync --locked` и смените в используемом
   `.local/test-settings.json` (или settings.json) только `runner.backend` на `local`.
   Для настоящего OpenCode `runner.mode` должен быть `real`; fake не вызывает модель.
5. Запустите `uv run --locked scripts/test_env.py run runner` (либо dev.py run runner
   для settings.json). `local.opencode` — путь к установленному в WSL executable.

Не нужно повторно запускать configure: это перезаписало бы вручную настроенные
Windows-пути C# проектов. MSSQL/Temporal остаются в Compose. API слушает Windows;
runner использует уже настроенные PLATFORM_GRPC и сертификаты.

`local` запускает установленный `opencode serve` на приватном 127.0.0.1 порту
со случайным Basic-auth паролем, завершает дочерний процесс вместе с wrapper.
Это обычный локальный OpenCode, не новый контейнер. Старый `cli` (`opencode run`)
остаётся доступен, но интерактивные permissions через UI не поддерживает.
Для контейнерного OpenCode используйте `server` и настройте permission policy в его
конфигурации: действия `deny` не создают вопросов и не могут быть разрешены из UI.

В local политика: read/glob/grep разрешены; остальные действия спрашивают;
task и question запрещены (дочерние агенты и анкеты не реализованы).
Одобрение bash допускает ровно запрошенный вызов: внимательно проверяйте команду
в patterns. Локальный процесс работает с правами пользователя WSL, permission UI
не заменяет ОС sandbox. Git clone credentials по-прежнему удаляются до prompt.

## Контракт и поведение

- `GET /api/v1/runs/{id}/permissions`: история запросов, только для владельца Run.
- `POST /api/v1/runs/{id}/permissions/{requestId}/decision`, JSON
  `{"decision":"once"}` или `{"decision":"reject"}`; cookie + antiforgery.
- gRPC PermissionExchange: OperationKey (BootId/Fence), SessionId, RequestId,
  Description, Phase; ответ PermissionResult(Status, Decision).
- Состояния: pending → decided → applied/unknown/expired. Исчезнувший из OpenCode
  запрос закрывается; после отмены, deadline или потери lease UI показывает expired.
- Одинаковый повтор решения идемпотентен, конфликтующее решение возвращает 409.
  Повтор запроса runner с изменённым описанием также отклоняется.
- SQL сохраняет автора и время решения; PermissionRequested/Decided/Delivery
  добавляются транзакционно в журнал Run. UI получает актуальные карточки через
  существующий REST polling, поэтому обновление страницы или смена API не теряет их.
- Runner читает GET /permission с directory, фильтрует SessionId. SSE не является
  единственным источником запросов, раннее permission.asked не теряется.
- Ответ POST /permission/{requestID}/reply содержит только reply once/reject.
  Потеря ответа означает unknown и остановку с NEEDS_ATTENTION; prompt не повторяется.
- Сертификат runner, BootId, Fence, lease, SessionId, deadline и отмена проверяются
  перед возвращением решения. Уже отправленный внешний запрос отмена не откатывает.
- До 100 запросов на операцию, описание до 8192 символов; в UI только permission и
  patterns, без произвольного metadata, reasoning и автоматической HTML-разметки.

Ожидание входит в прежний 20-минутный deadline. Worker продолжает Temporal polling,
runner поддерживает heartbeat. Ожидание через сутки и восстановление процесса
OpenCode не входят в этот этап. После потери процесса создайте новую задачу после проверки.

Контракт сверён с OpenCode v1.2.27:
[permission routes](https://github.com/anomalyco/opencode/blob/v1.2.27/packages/opencode/src/server/routes/permission.ts),
[permission service](https://github.com/anomalyco/opencode/blob/v1.2.27/packages/opencode/src/permission/service.ts).

## Приёмка на живом стенде

Запросите изменение файла: дождитесь карточки edit, обновите страницу, разрешите once.
Должны появиться applied и дальнейший вывод без второй отправки prompt.
Повторите с reject; OpenCode получает отказ и может выбрать другой путь.
Проверьте 404 для другого пользователя, 409 для противоположного ответа,
потерю соединения API после сохранения решения, отмену во время ожидания,
истечение lease и отсутствие кнопок у завершённой задачи.

Автоматические mock-тесты проверяют HTTP-контракт адаптера и отсутствие слепого
повтора. Они не заменяют SQL/mTLS/Rider/OpenCode/LLM live acceptance.
