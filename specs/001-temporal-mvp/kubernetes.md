# Kubernetes deployment specification

## Ограничения

Ни один rendered manifest application/optional Temporal profile не создаёт PVC/PV, hostPath, in-cluster PostgreSQL/MSSQL/Cassandra/MySQL/Redis. emptyDir допускается с sizeLimit. Secrets/ConfigMaps/projected service account volumes не являются persistent storage.

## Workloads

| Workload | Начальная конфигурация |
| --- | --- |
| platform-api | Deployment 2 replicas; HTTP/WS port и отдельный internal gRPC HTTP/2 port |
| platform-worker | Deployment 2 replicas; Temporal worker + dispatcher/reaper с SQL concurrency protection |
| agent-runner | Deployment, initial 2 replicas; Python + OpenCode sidecar, one active operation per pod |
| schema migration | Namespaced Job, явный release step до app rollout; отдельный DDL secret |

Runner не создаёт Jobs/Pods и не требует Kubernetes API. ServiceAccount automount token false, если не нужен. Нет ClusterRole. Не создавать ingress controller; использовать существующий ingress для HTTP/WebSocket. gRPC runner→API идёт внутри cluster Service и не требует изменения ingress controller.

Pod security: runAsNonRoot, allowPrivilegeEscalation false, capabilities drop ALL, readOnlyRootFilesystem, seccomp RuntimeDefault. emptyDir workspace 2 GiB, отдельные temp dirs, ephemeral-storage requests/limits. CPU/memory requests/limits для обоих runner containers; исчерпание приводит к наблюдаемому UNKNOWN/NEEDS_ATTENTION.

OpenCode sidecar health проверяется Python startup gate. Не зависеть от порядка старта обычных containers. Python ожидает health с timeout. Liveness не убивает worker из-за краткой недоступности внешней БД; readiness выводит из обслуживания. Graceful shutdown прекращает новые claims, пытается завершить/abort текущий operation; не обещает уложить 20-минутный Run в terminationGracePeriod.

## External dependencies и Secret keys

`platform-db`: connectionString (runtime DML); `platform-db-migration`: connectionString (DDL).

`temporal-client`: endpoint/namespace в ConfigMap, client cert/key и CA в Secret.

`runner-client`: workload mTLS cert/key и CA; только Python container.

`oidc-client`: client secret для ASP.NET Core OIDC flow; API cookie keys должны быть общими для replicas. В MVP хранить ASP.NET Core Data Protection key ring в MSSQL через поддерживаемый EF persistence и защищать ключи сертификатом из Secret; никакого ephemeral key ring/PVC. Это отдельная таблица служебного auth storage, не workflow state.

`repository-read`: read-only Git credentials, только Python; `llm-provider`: scoped model credential, только OpenCode. Endpoint/model ID из trusted ConfigMap. Секреты не включаются в values и logs.

## Optional Temporal profile

По умолчанию chart принимает готовый endpoint и не устанавливает Temporal. Для self-host profile создать отдельную pinned values overlay официального chart с external PostgreSQL/default+visibility, отключив bundled databases, Elasticsearch и monitoring subcharts с persistent storage. Не угадывать имена values: проверить выбранный chart schema и rendered manifests. Schema preparation отдельным контролируемым шагом, не auto-setup в каждом service pod.

INF-001 не закрывается пустым values: нужны рабочие endpoint/DB/TLS и live test. Внешнюю PostgreSQL не provisioning-ить без решения владельца инфраструктуры.

## Helm acceptance

- `helm lint` и `helm template` с двумя API replicas.
- Рекурсивная проверка всех manifest kinds, volumes и dependency images на запрещённые компоненты.
- `kubectl apply --dry-run=server` только при доступном авторизованном тестовом namespace.
- No cluster-scoped resources; network policies для ingress, internal gRPC, DNS, MSSQL, Temporal, allowlisted Git/LLM. Ограничение FQDN зависит от CNI; стандартный NetworkPolicy сам по себе FQDN allowlist не реализует — использовать согласованный egress proxy/IP rules.
- Rollout/API pod deletion не создаёт повторный prompt.

Ни kubectl команды, ни deployment агент не выполняет в неизвестном production namespace. Артефакты chart и инструкция должны быть готовы даже без cluster credentials.

Документация Data Protection key persistence: [Microsoft](https://learn.microsoft.com/en-us/aspnet/core/security/data-protection/implementation/key-storage-providers?view=aspnetcore-10.0).
