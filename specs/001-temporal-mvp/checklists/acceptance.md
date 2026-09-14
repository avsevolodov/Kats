# Acceptance checklist

Все пункты изначально не выполнены: пакет описывает работу, не подтверждает реализацию.

- [ ] A01 Реальный C# workflow/activities собраны и работают с выбранным Temporal (.NET не mock).
- [ ] A02 External MSSQL migrations/transactions проверены; Temporal использует supported persistence/готовый endpoint.
- [ ] A03 Duplicate Start same hash возвращает RunId; conflicting payload →409; два API не создают две операции.
- [ ] A04 Lost Temporal start response не создаёт второй workflow.
- [ ] A05 Begin и cancel сериализованы: отменённый до Begin operation не отправляет prompt.
- [ ] A06 Python/OpenCode реальный round-trip, final patch применим на base commit, новые файлы включены.
- [ ] A07 WebSocket reconnect на другую API replica не теряет committed events и не дублирует отображение.
- [ ] A08 C# worker restart не повторяет prompt живого Python operation.
- [ ] A09 SQL completion commit + lost ACK возвращает прежние artifacts.
- [ ] A10 Python/OpenCode pod loss →UNKNOWN/NEEDS_ATTENTION, нет автоматического retry.
- [ ] A11 Cancel outcome и completion race соответствуют workflow.md; неизвестность не маскируется.
- [ ] A12 Event commit order test исключает пропуск более раннего sequence.
- [ ] A13 Preview/result/queue/buffer limits работают без OOM и без ложного SUCCEEDED.
- [ ] A14 Cross-owner REST/WS/artifacts запрещены; cookie работает на обеих replicas без sticky sessions.
- [ ] A15 Workload identity/fence проверяются; stale runner не пишет результат.
- [ ] A16 Secret scan и OpenCode permission tests проходят; repo config не повышает права.
- [ ] A17 Helm render не содержит PVC/PV/hostPath/Redis и in-cluster DB; images pinned.
- [ ] A18 10-run нагрузка измерена и цели/отклонения записаны.
- [ ] A19 Cleanup не удаляет active state, expired cursor и artifact expiry видны пользователю.
- [ ] A20 Финальный отчёт отделяет unit/fake/live проверки, INF-001 закрыт или deployment честно blocked.

## Traceability

| Requirement | Tasks | Acceptance |
| --- | --- | --- |
| FR-001 | T001,T005,T012 | A01 |
| FR-002 | T022–T025 | A06,A07,A11 |
| FR-003 | T003,T026,T028,T042 | A06 |
| FR-004 | T007,T013,T039 | A03,A04 |
| FR-005 | T008,T012,T016 | A04,A08 |
| FR-006 | T004,T019,T026,T038 | A07,A15 |
| FR-007 | T009,T018,T023 | A07,A12 |
| FR-008 | T009,T029,T043 | A12,A13,A18 |
| FR-009 | T010,T029,T042 | A06,A09 |
| FR-010 | T014,T030,T041 | A05,A11 |
| FR-011 | T015,T030,T040 | A10,A15 |
| FR-012 | T027,T031,T042 | A06,A16 |
| FR-013 | T021,T031,T044 | A14,A15,A16 |
| FR-014 | T032,T033,T035,T044 | A17 |
| FR-015 | T002,T034,T044 | A02,A17,A20 |
| FR-016 | T037–T044 | A07–A18 |
| FR-017 | T001,T003,T028,T045 | A01,A06,A20 |
| FR-018 | T006,T010,T036,T045 | A09,A19 |
