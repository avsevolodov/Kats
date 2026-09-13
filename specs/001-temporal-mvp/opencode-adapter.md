# Python/OpenCode adapter

## Размещение

Один runner pod: Python container и OpenCode server container, общий ограниченный emptyDir `/workspace`. Server слушает только pod-local localhost HTTP. Python управляет session через API; перенос OpenCode в sidecar изолирует runner mTLS/Git secrets от OpenCode filesystem. Sidecar не имеет runner certificate, MSSQL credentials и Git credentials. Python делает read-only clone до prompt. Platform workload токены не доступны OpenCode tools.

Оба контейнера имеют отдельные UID, readOnlyRootFilesystem, свои ephemeral temp/data dirs; shared workspace writable для согласованной группы. LLM credential доступен OpenCode только в минимальном provider scope. NetworkPolicy применяется ко всему pod, а не отдельно к контейнеру: эту границу не переоценивать.

После рестарта Python в прежнем pod OpenCode sidecar может остаться жив. До нового Claim wrapper должен обнаружить и остановить прежние sessions и подтвердить quiescence; он не принимает старое исполнение под новым BootId. Если остановка не доказана, pod остаётся NotReady для новых задач. Нельзя очищать workspace под продолжающимися tools. Для разных operations directory binding задаётся и проверяется по pinned OpenCode API; server cwd не должен случайно указывать на предыдущий repo.

## Последовательность

1. Создать BootId, gRPC Hello, проверить version/health локального OpenCode.
2. Claim assignment (без секрета). Для AuthKind=Pat без legacy CredentialRef вызвать FetchGitCredential по OperationKey; для Anonymous — без askpass; legacy CredentialRef — файл из mounted dir. Подготовить чистый workspace, clone зарегистрированного repo, checkout точного commit; не получать arbitrary URL из prompt.
3. Проверить отсутствие submodules/LFS, лимит размера, запрет credentials в `.git/config`; временный askpass/файл удалить после clone.
4. Создать OpenCode session, сохранить ID в Python memory; BeginOperation и дождаться committed ACK.
5. Отправить ровно один prompt для этого operation. Сохранить локальный флаг prompt_sent; при HTTP неопределённости читать ту же session, не повторять prompt автоматически. Устойчивый message ID использовать только после проверки семантики pinned API, не считать его гарантией идемпотентности по умолчанию.
6. SSE читать независимо от gRPC output writer; coalesce preview до 1 batch/s. Heartbeat/control обрабатываются независимо от тяжёлого model response.
7. По известному завершению собрать summary, проверить рабочее дерево и сформировать patch относительно base commit, включая новые текстовые файлы. Временный локальный Git index допустим, но не изменять удалённый repo. Binary/untracked secrets/oversize дают явный отказ.
8. CompleteOperation с batch sequence; повторить тот же Complete при потерянном ACK, не запуска́ть OpenCode повторно. Только после persisted completion очистить session/workspace.

До Begin failure (clone error etc.) runner завершает LEASED operation как FAILED с текущим fence; completion разрешён из LEASED для известного pre-execution failure. Ни одной генерации при таком отказе.

## OpenCode API contract gate

Выбранная released-версия должна подтвердить: health/version; session create; prompt submit; session status/messages; event stream; abort. Tests используют fixture OpenAPI/event examples этой версии. Не парсить текст TUI или logs как статус завершения.

Idle не всегда означает success: проверить финальный assistant message/error и отсутствие pending permission/tool. Lost SSE восстанавливает presentation из message API при возможности; модель повторно не вызывается. Internal model retries OpenCode не покрываются платформенной exactly-once гарантией; конфигурацию retry задокументировать.

## Permissions и внешние действия

MVP разрешает чтение/редактирование workspace и ограниченные команды проверки в контейнере. Tool permissions задать явно; запрещены push, PR, SSH, произвольные сетевые tools, sharing, package installs без внутреннего разрешённого фида. Репозиторий рассматривается как недоверенные данные. Не загружать repo-provided plugins/config, меняющие security policy; способ отключения подтвердить smoke-тестом pinned версии. Если надёжно отключить нельзя, MVP repo allowlist ограничивается доверенными fixture/pilot repositories, это записывается как security gate, не замалчивается.

Неожиданный permission/question: abort и FAILED(PERMISSION_REQUIRED_UNSUPPORTED), без автоматического ответа «allow». HITL позже.

## Loss semantics

- Gateway reconnect: session жива, prompt_sent сохраняется, output перепосылается по sequence.
- C# worker restart: Python/OpenCode работают независимо.
- Python process restart: новый BootId, прежний operation не принимается; reaper UNKNOWN.
- OpenCode container restart: session/файлы могут частично остаться в emptyDir, но execution не доказан; UNKNOWN, а не автоматический import/continue.
- Pod deletion: workspace/session потеряны; NEEDS_ATTENTION, новый Run только явно.

Export/import не является checkpoint recovery MVP. Финальный patch в MSSQL — артефакт, а не snapshot процесса.
