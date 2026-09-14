# MSSQL data model

Ниже нормативная логическая схема; EF Core migrations создаёт агент. Все времена UTC datetime2, идентификаторы приложения UUID, sequence/fence bigint, owner получен из auth, JSON валидируется. MSSQL — внешний сервис.

## Таблицы и ключи

| Таблица | Основные поля | Уникальность/индексы |
| --- | --- | --- |
| Repositories | RepositoryId, DisplayName, CloneUrl, AllowedRefPolicy, CredentialRef, Enabled | PK RepositoryId; URL только из admin configuration |
| Runs | RunId, OwnerSubject, RepositoryId, BaseCommit, Prompt, DefinitionVersion, WorkflowId, OperationId, ProjectedStatus, CancelDesired, CreatedAt, UpdatedAt, NextEventSequence, EarliestAvailableSequence, RowVersion | PK RunId; unique WorkflowId; owner/created index |
| Commands | OwnerSubject, CommandId, Kind, RunId, RequestHash, PayloadJson, Status, AcceptedAt, DispatchLeaseUntil, DispatchAttempt, LastError | unique(OwnerSubject,CommandId); status/lease index |
| Operations | OperationId, RunId, Kind, Status, RunnerBootId, Fence, LeaseUntil, BeginCommittedAt, OpenCodeSessionId, CancelDesired, ResultManifestId, ErrorCode, CreatedAt, UpdatedAt, RowVersion | PK OperationId; unique(RunId,Kind) MVP; status/lease index |
| RunnerSessions | BootId, WorkloadSubject, Version, LastSeenAt | PK BootId; auth binding, не affinity map |
| ProducerReceipts | OperationId, ProducerSequence, MessageId, PayloadHash, EventSequenceFrom, EventSequenceTo | unique(OperationId,ProducerSequence); unique(OperationId,MessageId) |
| RunEvents | RunId, Sequence, EventId, Kind, OperationId, PayloadJson, CreatedAt | PK(RunId,Sequence); unique EventId |
| Artifacts | ArtifactId, RunId, OperationId, Kind, MediaType, SizeBytes, Sha256, Content varbinary(max), CreatedAt, ExpiresAt | PK ArtifactId; unique(OperationId,Kind) |
| ResultManifests | ManifestId, OperationId, SummaryArtifactId, PatchArtifactId, ResultHash | PK ManifestId; unique OperationId |
| DataProtectionKeys | Служебные EF Data Protection key records | Стандартная схема provider; encrypted key XML |
| WorkflowPublications | RunId, PublicationKey, PayloadHash | unique(RunId,PublicationKey) |

Runs.ProjectedStatus — проекция Temporal workflow. Operations.Status — authoritative состояние доставки/исполнения отдельного OpenCode operation. Поля CancelDesired фиксируют намерение, не объявляют Run CANCELLED.

## State machines

Run projection: ACCEPTED → STARTING → QUEUED → RUNNING → SUCCEEDED / FAILED / CANCELLED / NEEDS_ATTENTION. CANCEL_REQUESTED — промежуточное состояние для активного Run. ACCEPTED означает commit inbox, до Temporal start. Terminal status публикует workflow activity. Command rejection до workflow может отображаться отдельно как start error, не выдуманный Temporal completion.

Operation: QUEUED → LEASED → RUNNING → SUCCEEDED / FAILED / CANCELLED / UNKNOWN.

- LEASED означает reserved, prompt ещё не разрешён.
- BeginCommitted переводит LEASED → RUNNING; только после ACK runner может отправить prompt.
- Lease истёк в LEASED/RUNNING: UNKNOWN, никакого возврата в QUEUED. Это консервативная политика MVP даже если prompt ещё не был отправлен.
- Same BootId reconnect в пределах lease сохраняет Fence и operation. Новый BootId не получает начатую operation.
- После UNKNOWN старые результаты отвергаются как fenced; возможна ручная диагностика, автоматическое возобновление отсутствует.
- Cancel queued operation → CANCELLED. Cancel running → intent и AbortRequested; terminal только после известного abort/result outcome.

## Транзакции

### Accept Start

В одной транзакции: dedup ключ → insert Runs(ACCEPTED) → insert Command(PENDING) → RunAccepted event. RequestHash SHA-256 canonical DTO (порядок свойств задан контрактом, UTF-8, prompt сохраняется без незаявленной нормализации). Повтор identical возвращает RunId, conflict — 409. RunId может генерироваться до транзакции; победитель unique constraint определяет итог.

OperationId генерируется вместе с RunId до принятия и хранится в Runs/command payload. Atomic admission до insert использует короткую SQL application lock или отдельную capacity row: nonterminal accepted Run ≤10 во всём окружении, а не в каждой API replica. Повтор уже принятого CommandId не расходует слот и не отвергается из-за заполненного лимита.

### Claim

Atomic compare-and-update QUEUED → LEASED с увеличением Fence и назначением BootId. Использовать доказанный SQL locking pattern, проверенный при двух API replicas; не read-then-update вне транзакции. CancelDesired исключает claim. Транзакция короткая, без сетевых вызовов.

### Begin и Cancel race

Begin проверяет Fence, lease, BootId, Operations.CancelDesired и Runs.CancelDesired под lock. При cancel не разрешает prompt. Accept Cancel записывает command и desired flag в той же транзакции; это fencing намерения, не переход Run в terminal. Если Begin успел раньше, prompt мог начаться; применяется running cancellation, а не обещание «ничего не запускалось».

### Append events

ProducerSequence строго возрастает для operation начиная с 1; повтор same seq/hash ACK, mismatch конфликт. Новая последовательность должна быть следующей после последней committed, иначе EXPECTED_SEQUENCE. В одной транзакции: проверить lease/fence → dedup → блокировать Runs.NextEventSequence → выделить номера → insert events/receipt → update next counter. Это предотвращает пропуск событий при commit-order race; не использовать identity как cursor без гарантии видимости предыдущих commits.

### Complete

Проверить producer sequence/fence, размер/hash result; атомарно вставить artifacts, operation terminal, receipt и OperationCompleted event. Lost ACK повтор возвращает тот же результат. Workflow позже публикует RunSucceeded/Failed и ссылки отдельной идемпотентной activity; UI различает operation completion и run projection.

Исключение для повторов: после проверки workload identity и соответствия исходным BootId/Fence сначала искать committed receipt. Идентичный повтор уже зафиксированного Complete возвращает ACK даже после terminal/истечения lease; он ничего не изменяет и lease не продлевает. Новые сообщения после terminal/UNKNOWN или с иным payload отвергаются. Это необходимо для потерянного completion ACK.

### Workflow publication

PublicationKey детерминирован из логического перехода workflow, а не activity attempt. Unique key + payload hash исключает повтор событий при потерянном activity completion. Вставка publication, изменение RunView и event — одна SQL transaction.

## Retention

Active данные не удаляются. Terminal preview и artifacts: 7 дней (UI показывает expiry). Commands/receipts/tombstones: 30 дней; API принимает повторный ключ только внутри этого окна и запрещает reuse известных expired identifiers. После удаления dedup history для неизвестного старого UUID нет магической вечной гарантии: клиенты обязаны не retry после 30 дней, сервер проверяет signed/recorded accepted timestamp при соответствующем recovery flow. Не обещать бессрочную дедупликацию произвольного ключа.

Temporal history retention согласовать с диагностическим окном; завершённый API Run не перезапускается, даже если history уже удалена: Commands/Runs препятствуют повторному Start. Cleanup events обновляет EarliestAvailableSequence и выдаёт cursor-expired; это поле/служебный watermark добавить миграцией.
