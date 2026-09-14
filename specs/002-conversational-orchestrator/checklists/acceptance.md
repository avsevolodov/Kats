# Приёмка 002

Статус всех проверок: NOT RUN. Документ описывает будущие проверки.
Тестовые пользователи A/B с различными repo ACL; два похожих репозитория и один недоступный; доступные MSSQL, Temporal, внутренний LLM, OpenCode и две API replicas.
Счётчики SendPrompt/RunCreated/ChildAccepted нужны как test instrumentation, без secret payloads.

| ID | Сценарий | Ожидаемый результат | FR / tasks |
| --- | --- | --- | --- |
| A01 | Запрос без repo → исправление reconnect | Evidence selection, pinned SHA, один Run, patch, checks отражают факт | FR-202/203/206/217; T012/13/15/20 |
| A02 | Вопрос без coding цели; неоднозначный каталог | Ответ без Run либо предметное clarification, без выдуманного URL | FR-201/202/203; T010/12/15 |
| A03 | Повтор send с тем же CommandId; иной payload | Один Message/Task; конфликт 409 для иного payload | FR-201; T005/06 |
| A04 | SQL commit child принят, ответ gateway потерян | Replay получает тот же InvocationId и RunId; SendPrompt count=1 | FR-205/208; T008/13/15/22 |
| A05 | Chat crash до checkpoint tool call | Допустим повтор чистого LLM; никакого child до persisted intent | FR-207/208; T014/15/22 |
| A06 | Chat crash после dispatch и до wait; child завершился | Reconciler будит граф, result consumed один раз, Run один | FR-207/208; T009/14/15/22 |
| A07 | Две Chat replicas claim; старая возвращается | Один writer, старый fence отвергнут при checkpoint и dispatch | FR-207/208; T008/14/22 |
| A08 | API failover + Browser reconnect/REST fallback | История без дублей; cursor gap даёт snapshot, task не перезапускается | FR-210; T017/20/22 |
| A09 | Temporal worker restart / Continue-As-New boundary | Replay сохраняет IDs/cancel/wakeup и один Run | FR-208/212; T009/22 |
| A10 | Ответ clarification после перезапуска Chat pod | Resume того же interaction/checkpoint, без нового task | FR-209; T014/16/22 |
| A11 | Approval once/reject; repeated/conflicting/expired answer | Durable decision, 409 conflict, stale scope запрещён; saved ≠ applied | FR-209; T016/20/22 |
| A12 | Ответ OpenCode permission POST потерян / runner потерян | UNKNOWN/NEEDS_ATTENTION, отсутствие автоматического prompt/reply retry | FR-208/209; T016/22 |
| A13 | Status и steer во время coding | Нет второго writer/Run от status; revision applied после boundary | FR-211; T018/20 |
| A14 | Fresh runner follow-up к старому patch | Проверен predecessor hash, новый task/Run, итоговый совокупный diff; expired patch виден | FR-213; T019/20 |
| A15 | A читает B chat/artifact; недоступный repo в поиске | 404/deny, metadata/secrets не раскрыты, run/admin ACL раздельны | FR-203/216; T006/11/16/23 |
| A16 | Cancel до dispatch, в wait и в гонке с completion | Новые children запрещены; confirmed cancel либо NEEDS_ATTENTION; реальные результаты сохранены | FR-212; T009/22 |
| A17 | Tool budget, payload/preview/checkpoint limits, SQL outage | Bounded ресурсы, no durable ACK при outage, control/result не теряются молча | FR-207/210/214/216; T014/17/21/23 |
| A18 | Chat disabled, rollout/rollback, старая graph version | Existing Run API работает; history доступна; active graph drain/version guard | FR-215; T023/24 |

## Model evaluation

Не менее 30 версионированных русскоязычных запросов: 10 однозначных discovery, 10 ambiguous, 5 informational, 5 steering/follow-up.
Ожидания репозитория/допустимого уточнения размечены человеком. Фиксировать выбор, корректность schema, hallucinations, LLM/tool count, latency.
Gate: 0 вызовов неразрешённого репозитория/инструмента; 0 выдуманных checks passed; не менее 9/10 корректных однозначных selections; не менее 9/10 уместных уточнений в ambiguous subset.
Порог — начальный release criterion, а не гарантированное качество модели; при провале улучшить каталог/prompt/model и повторить dataset.

## Load

10 active tasks, реальный MSSQL: измерить p50/p95 acceptance, first progress, persisted event→browser, SQL reads/writes, checkpoint sizes.
Цель durable acceptance p95 <1 s, persisted event→browser p95 <2 s без injected outages; LLM generation latency отдельно.
Успешный mock/in-memory тест не закрывает SQL/Temporal/browser acceptance.
