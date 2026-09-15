-- Additive conversation / task schema for feature 002 (T005).
SET XACT_ABORT ON;
GO
BEGIN TRANSACTION;
DECLARE @lock int; EXEC @lock=sp_getapplock @Resource=N'agent-platform-schema-v1',@LockMode='Exclusive',@LockOwner='Transaction';
IF @lock<0 THROW 51000,'Schema lock failed',1;

IF OBJECT_ID(N'dbo.Conversations',N'U') IS NULL
  CREATE TABLE dbo.Conversations(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    OwnerSubject nvarchar(200) NOT NULL,
    Title nvarchar(200) NOT NULL,
    CreatedAt datetime2 NOT NULL,
    UpdatedAt datetime2 NOT NULL,
    NextEventSequence bigint NOT NULL CONSTRAINT DF_Conversations_NextSeq DEFAULT(0),
    SummaryCursor bigint NOT NULL CONSTRAINT DF_Conversations_Summary DEFAULT(0),
    RowVersion rowversion NOT NULL
  );
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name=N'IX_Conversations_Owner_Updated' AND object_id=OBJECT_ID(N'dbo.Conversations'))
  CREATE INDEX IX_Conversations_Owner_Updated ON dbo.Conversations(OwnerSubject, UpdatedAt DESC);

IF OBJECT_ID(N'dbo.AgentTasks',N'U') IS NULL
  CREATE TABLE dbo.AgentTasks(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    ConversationId uniqueidentifier NOT NULL REFERENCES dbo.Conversations(Id),
    Goal nvarchar(max) NOT NULL,
    GoalRevision int NOT NULL CONSTRAINT DF_AgentTasks_Rev DEFAULT(1),
    Status nvarchar(32) NOT NULL,
    RootInvocationId uniqueidentifier NULL,
    WorkflowId nvarchar(200) NOT NULL,
    WallDeadline datetime2 NOT NULL,
    CancelDesired bit NOT NULL CONSTRAINT DF_AgentTasks_Cancel DEFAULT(0),
    DefinitionVersion nvarchar(64) NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_AgentTasks_Active DEFAULT(1),
    CreatedAt datetime2 NOT NULL,
    UpdatedAt datetime2 NOT NULL
  );
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name=N'UQ_AgentTasks_ActiveConversation' AND object_id=OBJECT_ID(N'dbo.AgentTasks'))
  CREATE UNIQUE INDEX UQ_AgentTasks_ActiveConversation ON dbo.AgentTasks(ConversationId) WHERE IsActive=1;

IF OBJECT_ID(N'dbo.Messages',N'U') IS NULL
  CREATE TABLE dbo.Messages(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    ConversationId uniqueidentifier NOT NULL REFERENCES dbo.Conversations(Id),
    Role nvarchar(32) NOT NULL,
    Content nvarchar(max) NOT NULL,
    TaskId uniqueidentifier NULL REFERENCES dbo.AgentTasks(Id),
    SourceKey nvarchar(200) NULL,
    ReplyToInteractionId uniqueidentifier NULL,
    CreatedAt datetime2 NOT NULL
  );
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name=N'IX_Messages_Conversation_Created' AND object_id=OBJECT_ID(N'dbo.Messages'))
  CREATE INDEX IX_Messages_Conversation_Created ON dbo.Messages(ConversationId, CreatedAt);

IF OBJECT_ID(N'dbo.ConversationCommands',N'U') IS NULL
  CREATE TABLE dbo.ConversationCommands(
    CommandId uniqueidentifier NOT NULL,
    OwnerSubject nvarchar(200) NOT NULL,
    ConversationId uniqueidentifier NOT NULL,
    RequestHash nvarchar(64) NOT NULL,
    AcceptedResourceId uniqueidentifier NOT NULL,
    Status nvarchar(32) NOT NULL,
    Kind nvarchar(32) NOT NULL,
    CreatedAt datetime2 NOT NULL,
    CONSTRAINT PK_ConversationCommands PRIMARY KEY (OwnerSubject, CommandId)
  );

IF OBJECT_ID(N'dbo.TaskInputs',N'U') IS NULL
  CREATE TABLE dbo.TaskInputs(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    TaskId uniqueidentifier NOT NULL REFERENCES dbo.AgentTasks(Id),
    MessageId uniqueidentifier NOT NULL,
    Revision int NOT NULL,
    Disposition nvarchar(32) NOT NULL,
    AppliedAt datetime2 NULL,
    CONSTRAINT UQ_TaskInputs_Message UNIQUE(MessageId)
  );

COMMIT;
GO
