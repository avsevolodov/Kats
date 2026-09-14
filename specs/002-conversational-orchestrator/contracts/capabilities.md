# Registered capabilities v1

Все inputs/results schema-validated. Registry — фиксированная конфигурация deployment: name, version, handler, input/output schema, allowed callers, timeout, resource scope.
Нет user-provided executable handlers. Capability availability контролируется deployment, а не LLM.

| Capability | Input | Output | Поставка |
| --- | --- | --- | --- |
| catalog.search@1 | query, limit ≤10 | candidates: repositoryId, displayName, description, matchedFields, evidenceRefs, catalogVersion | обязательна |
| repositories.describe@1 | repositoryId | components, serviceAliases, defaultRef, sourceRefs, freshness | обязательна |
| repositories.resolve_ref@1 | repositoryId, ref? | fullCommitSha, resolvedRef, resolvedAt | обязательна |
| code.search@1 | repositoryId, commit, query, paths?, limit ≤20 | matches: path, line, excerpt, commit, truncated | обязательна |
| coding.execute@1 | см. ниже | status, summary, patchRef, baseCommit, checks[], unresolvedQuestions[] | обязательна |
| documents.search@1 | query, scope?, limit | authorized excerpts + source/version refs | после 002 |
| research.execute@1 | question, sourceScopes, expectedOutput | reportRef, findings, citations, gaps | после 002 |

## Discovery

MVP: управляемые описания каталога + простой текстовый поиск по aliases/services/components. Vector DB не требуется.
Проверка гипотезы через describe и code.search; agent фиксирует evidence вместо неподтверждённого confidence score.
Если evidence не выделяет кандидата, clarification. Нет репозитория — честный вопрос/ответ, не выдуманный URL.
code.search в первой реализации — bounded read-only snapshot/checkout на worker с allowed host и path traversal checks. Поиск на одном immutable SHA. Credentials удаляются до передачи данных модели.

## coding.execute input

```json
{
  "repositoryId": "40000000-0000-0000-0000-000000000001",
  "baseCommit": "0123456789abcdef0123456789abcdef01234567",
  "goal": "Исправить восстановление прогресса после reconnect",
  "taskRevision": 1,
  "contextReferences": [],
  "acceptanceCriteria": [
    "Повторное подключение отображает сохранённые события без дублей"
  ],
  "constraints": ["Подготовить patch в существующей архитектуре"],
  "expectedArtifacts": ["summary", "patch"],
  "predecessorPatch": null
}
```

predecessorPatch при follow-up: artifactId, sha256, baseCommit. Проверки hash, ownership, baseCommit и clean apply обязательны до prompt.
Server scope разрешает только registered RepositoryId; prompt не назначает host, credentials или policy.
Адаптер формирует bounded prompt с явно разделёнными goal/criteria/context. Репозиторные инструкции соблюдаются в рамках выданных платформой полномочий.

## coding.execute result

```json
{
  "status": "SUCCEEDED",
  "summary": "Подготовлено изменение восстановления cursor.",
  "baseCommit": "0123456789abcdef0123456789abcdef01234567",
  "patchRef": {"artifactId": "50000000-0000-0000-0000-000000000001"},
  "checks": [
    {"name": "browser reconnect", "outcome": "not_run", "explanation": "Нет live browser evidence"}
  ],
  "unresolvedQuestions": []
}
```

При baseline summary/patch без structured evidence checks=not_run. Нельзя извлекать passed из произвольного убедительного текста.
В последующей реализации runner возвращает проверяемые test evidence refs; raw logs проходят redaction/bounds.
Result status отражает execution исход; NEEDS_ATTENTION task может ссылаться на UNKNOWN child и частичные artifacts.

## ACL

Для search/read нужен read; для coding.execute — run на repository плюс owner task. Scope parent передаётся сервером и может только сужаться.
Repository administration отдельно от run. Существующий authenticated CRUD каталога требует role/ACL audit, чтобы обычный chat caller не менял repository URL и credentials.
Read-only Git credential означает запрет push. Изменение локального checkout и сборка регулируются permission/sandbox, не Git credential.
