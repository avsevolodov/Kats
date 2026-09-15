-- Invocations, dispatch intents, executions, interactions, events (T008/T016/T017).
SET XACT_ABORT ON;
GO
BEGIN TRANSACTION;
DECLARE @lock int; EXEC @lock=sp_getapplock @Resource=N'agent-platform-schema-v1',@LockMode='Exclusive',@LockOwner='Transaction';
IF @lock<0 THROW 51000,'Schema lock failed',1;

IF OBJECT_ID(N'dbo.Invocations',N'U') IS NULL
  CREATE TABLE dbo.Invocations(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    TaskId uniqueidentifier NOT NULL REFERENCES dbo.AgentTasks(Id),
    ParentId uniqueidentifier NULL,
    Kind nvarchar(32) NOT NULL,
    Capability nvarchar(100) NOT NULL,
    Version nvarchar(16) NOT NULL,
    RequestHash nvarchar(64) NOT NULL,
    Status nvarchar(32) NOT NULL,
    RunId uniqueidentifier NULL,
    ResultJson nvarchar(max) NULL,
    CancelDesired bit NOT NULL CONSTRAINT DF_Invocations_Cancel DEFAULT(0),
    CreatedAt datetime2 NOT NULL,
    UpdatedAt datetime2 NOT NULL
  );
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name=N'UQ_Invocations_RunId' AND object_id=OBJECT_ID(N'dbo.Invocations'))
  CREATE UNIQUE INDEX UQ_Invocations_RunId ON dbo.Invocations(RunId) WHERE RunId IS NOT NULL;

IF OBJECT_ID(N'dbo.DispatchIntents',N'U') IS NULL
  CREATE TABLE dbo.DispatchIntents(
    TaskId uniqueidentifier NOT NULL,
    CheckpointId nvarchar(200) NOT NULL,
    GraphTaskPath nvarchar(200) NOT NULL,
    ToolCallId nvarchar(200) NOT NULL,
    InvocationId uniqueidentifier NOT NULL REFERENCES dbo.Invocations(Id),
    InputHash nvarchar(64) NOT NULL,
    CreatedAt datetime2 NOT NULL,
    CONSTRAINT PK_DispatchIntents PRIMARY KEY (TaskId, CheckpointId, GraphTaskPath, ToolCallId)
  );

IF OBJECT_ID(N'dbo.AgentExecutions',N'U') IS NULL
  CREATE TABLE dbo.AgentExecutions(
    InvocationId uniqueidentifier NOT NULL PRIMARY KEY REFERENCES dbo.Invocations(Id),
    BootId uniqueidentifier NOT NULL,
    Fence bigint NOT NULL,
    LeaseUntil datetime2 NOT NULL,
    CheckpointId nvarchar(200) NULL,
    Status nvarchar(32) NOT NULL
  );

IF OBJECT_ID(N'dbo.InteractionRequests',N'U') IS NULL
  CREATE TABLE dbo.InteractionRequests(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    TaskId uniqueidentifier NOT NULL REFERENCES dbo.AgentTasks(Id),
    OriginInvocationId uniqueidentifier NULL,
    ExternalRequestId nvarchar(200) NULL,
    Kind nvarchar(32) NOT NULL,
    PayloadJson nvarchar(max) NOT NULL,
    PayloadHash nvarchar(64) NOT NULL,
    Status nvarchar(32) NOT NULL,
    ExpiresAt datetime2 NOT NULL,
    DeliveryStatus nvarchar(32) NOT NULL,
    CreatedAt datetime2 NOT NULL
  );

IF OBJECT_ID(N'dbo.InteractionDecisions',N'U') IS NULL
  CREATE TABLE dbo.InteractionDecisions(
    InteractionId uniqueidentifier NOT NULL PRIMARY KEY REFERENCES dbo.InteractionRequests(Id),
    CommandId uniqueidentifier NOT NULL,
    Decision nvarchar(32) NOT NULL,
    AnswersJson nvarchar(max) NULL,
    ActorSubject nvarchar(200) NOT NULL,
    DecidedAt datetime2 NOT NULL,
    DecisionHash nvarchar(64) NOT NULL
  );

IF OBJECT_ID(N'dbo.ConversationEvents',N'U') IS NULL
  CREATE TABLE dbo.ConversationEvents(
    ConversationId uniqueidentifier NOT NULL,
    Sequence bigint NOT NULL,
    EventId uniqueidentifier NOT NULL,
    TaskId uniqueidentifier NULL,
    InvocationId uniqueidentifier NULL,
    Kind nvarchar(64) NOT NULL,
    Payload nvarchar(max) NOT NULL,
    SourceEventKey nvarchar(200) NOT NULL,
    CreatedAt datetime2 NOT NULL,
    CONSTRAINT PK_ConversationEvents PRIMARY KEY (ConversationId, Sequence),
    CONSTRAINT UQ_ConversationEvents_Source UNIQUE(SourceEventKey)
  );

IF OBJECT_ID(N'dbo.ContextBindings',N'U') IS NULL
  CREATE TABLE dbo.ContextBindings(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    TaskId uniqueidentifier NOT NULL REFERENCES dbo.AgentTasks(Id),
    RepositoryId uniqueidentifier NOT NULL,
    BaseCommit nvarchar(64) NOT NULL,
    EvidenceRefsJson nvarchar(max) NOT NULL,
    CatalogVersion nvarchar(64) NOT NULL,
    SelectedAt datetime2 NOT NULL,
    TaskRevision int NOT NULL
  );

IF OBJECT_ID(N'dbo.RepositoryMetadata',N'U') IS NULL
  CREATE TABLE dbo.RepositoryMetadata(
    RepositoryId uniqueidentifier NOT NULL PRIMARY KEY REFERENCES dbo.Repositories(Id),
    Description nvarchar(max) NOT NULL CONSTRAINT DF_RepoMeta_Desc DEFAULT(N''),
    AliasesJson nvarchar(max) NOT NULL CONSTRAINT DF_RepoMeta_Aliases DEFAULT(N'[]'),
    ServiceNamesJson nvarchar(max) NOT NULL CONSTRAINT DF_RepoMeta_Services DEFAULT(N'[]'),
    ComponentsJson nvarchar(max) NOT NULL CONSTRAINT DF_RepoMeta_Components DEFAULT(N'[]'),
    DefaultRef nvarchar(200) NOT NULL CONSTRAINT DF_RepoMeta_Ref DEFAULT(N'main'),
    SourceRefs nvarchar(max) NOT NULL CONSTRAINT DF_RepoMeta_Src DEFAULT(N'[]'),
    UpdatedAt datetime2 NOT NULL,
    CatalogVersion nvarchar(64) NOT NULL
  );

IF OBJECT_ID(N'dbo.RepositoryAccess',N'U') IS NULL
  CREATE TABLE dbo.RepositoryAccess(
    RepositoryId uniqueidentifier NOT NULL REFERENCES dbo.Repositories(Id),
    PrincipalKind nvarchar(16) NOT NULL,
    PrincipalId nvarchar(200) NOT NULL,
    Action nvarchar(16) NOT NULL,
    CONSTRAINT PK_RepositoryAccess PRIMARY KEY (RepositoryId, PrincipalKind, PrincipalId, Action)
  );

COMMIT;
GO
