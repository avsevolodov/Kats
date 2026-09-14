-- Additive: OperationConfirmations for OpenCode server HITL (permission/question).
-- Safe to re-run.
SET XACT_ABORT ON;
GO
BEGIN TRANSACTION;
DECLARE @lock int; EXEC @lock=sp_getapplock @Resource=N'agent-platform-schema-v1',@LockMode='Exclusive',@LockOwner='Transaction';
IF @lock<0 THROW 51000,'Schema lock failed',1;
IF OBJECT_ID(N'dbo.OperationConfirmations',N'U') IS NULL
  CREATE TABLE dbo.OperationConfirmations(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    OperationId uniqueidentifier NOT NULL REFERENCES Operations(Id),
    RequestId nvarchar(200) NOT NULL,
    Kind nvarchar(32) NOT NULL,
    PayloadJson nvarchar(max) NOT NULL,
    Status nvarchar(32) NOT NULL,
    Decision nvarchar(32) NULL,
    AnswersJson nvarchar(max) NULL,
    CommandId uniqueidentifier NULL,
    CreatedAt datetime2 NOT NULL,
    AnsweredAt datetime2 NULL,
    CONSTRAINT UQ_OperationConfirmations_Request UNIQUE(OperationId, RequestId));
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name=N'IX_OperationConfirmations_Pending' AND object_id=OBJECT_ID(N'dbo.OperationConfirmations'))
  CREATE INDEX IX_OperationConfirmations_Pending ON dbo.OperationConfirmations(OperationId, Status) INCLUDE(CreatedAt);
COMMIT;
GO
