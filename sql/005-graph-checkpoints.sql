-- Additive spike for feature 002 LangGraph checkpoints (T004).
-- Safe to re-run. Unique name after dual sql/004-* audit.
SET XACT_ABORT ON;
GO
BEGIN TRANSACTION;
DECLARE @lock int; EXEC @lock=sp_getapplock @Resource=N'agent-platform-schema-v1',@LockMode='Exclusive',@LockOwner='Transaction';
IF @lock<0 THROW 51000,'Schema lock failed',1;

IF OBJECT_ID(N'dbo.GraphCheckpoints',N'U') IS NULL
  CREATE TABLE dbo.GraphCheckpoints(
    ThreadId uniqueidentifier NOT NULL,
    Namespace nvarchar(200) NOT NULL CONSTRAINT DF_GraphCheckpoints_Ns DEFAULT(N''),
    CheckpointId nvarchar(200) NOT NULL,
    ParentCheckpointId nvarchar(200) NULL,
    DefinitionVersion nvarchar(64) NOT NULL CONSTRAINT DF_GraphCheckpoints_Def DEFAULT(N'chat-v1'),
    CodecVersion nvarchar(64) NOT NULL,
    Payload nvarchar(max) NOT NULL,
    Metadata nvarchar(max) NOT NULL,
    CreatedAt datetime2 NOT NULL,
    CONSTRAINT PK_GraphCheckpoints PRIMARY KEY (ThreadId, Namespace, CheckpointId)
  );

IF OBJECT_ID(N'dbo.GraphPendingWrites',N'U') IS NULL
  CREATE TABLE dbo.GraphPendingWrites(
    ThreadId uniqueidentifier NOT NULL,
    Namespace nvarchar(200) NOT NULL CONSTRAINT DF_GraphPendingWrites_Ns DEFAULT(N''),
    CheckpointId nvarchar(200) NOT NULL,
    GraphTaskId nvarchar(200) NOT NULL,
    WriteIndex int NOT NULL,
    Channel nvarchar(200) NOT NULL,
    ValueJson nvarchar(max) NOT NULL,
    CONSTRAINT PK_GraphPendingWrites PRIMARY KEY (ThreadId, Namespace, CheckpointId, GraphTaskId, WriteIndex)
  );

COMMIT;
GO
