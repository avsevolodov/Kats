# Задание реализатору

Реализуй feature 002 Conversational Orchestrator по текущему пакету. Пользователь общается через чат, агент самостоятельно выбирает repository/tools и поручает coding через шину.

1. Прочитай корневые AGENTS.md и constitution, затем README/spec/architecture/research, model/workflow/contracts, tasks/acceptance.
2. Сверь HEAD с baseline из README; не перезаписывай новые пользовательские изменения. Запиши изменения базы в status.
3. Начни с T001–T004. Исправь подтверждённые несовместимости в рамках scope и закрепи released зависимости после smoke.
4. Следуй dependencies tasks.md. Создавай additive migrations с уникальными именами после аудита sql/004 файлов.
5. Сохрани C# владение платформой/Temporal, Python Chat Agent и existing Coding runner. Не вызывай LLM из workflow.
6. Не допускай повторного child dispatch при checkpoint replay. Сначала persisted intent, затем EnsureInvocation с устойчивым ключом.
7. Реализуй полный checkpointer contract закреплённого LangGraph release, включая pending writes; fake serializer не доказывает recovery.
8. Все внешние tools Chat Agent идут через bus. Встроенное локальное делегирование/shell не должно обходить scope.
9. Не добавляй продуктовые push/PR/CI side effects, новую прикладную БД, Redis, обязательный S3/PVC.
10. Не выдавай восстановление Chat Agent за восстановление OpenCode workspace. UNKNOWN должен быть честным итогом.
11. UI по умолчанию — диалог без обязательного выбора repo. Legacy Run detail оставь диагностическим.
12. Тестируй per-task acceptance; evidence отдельно по unit/SQL/Temporal/LLM/browser/crash. Не отмечай live gate по mock.
13. Обновляй docs/implementation-status.md и tasks.md. При отсутствии инфраструктуры продолжай доступную работу, перечисли непроведённые проверки.
14. Перед завершением проверь FR-201–FR-217 и A01–A18. Завершение docs package не равно завершению реализации.
