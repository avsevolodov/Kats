-- Additive: RunnerSessions for connected OpenCode runner presence (auth binding, not affinity).
-- Safe to re-run.
SET XACT_ABORT ON;
GO
BEGIN TRANSACTION;
DECLARE @lock int; EXEC @lock=sp_getapplock @Resource=N'agent-platform-schema-v1',@LockMode='Exclusive',@LockOwner='Transaction';
IF @lock<0 THROW 51000,'Schema lock failed',1;
IF OBJECT_ID(N'dbo.RunnerSessions',N'U') IS NULL
BEGIN
    CREATE TABLE dbo.RunnerSessions (
        BootId nvarchar(36) NOT NULL PRIMARY KEY,
        WorkloadSubject nvarchar(200) NOT NULL,
        Version nvarchar(200) NOT NULL,
        LastSeenAt datetime2 NOT NULL
    );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.RunnerSessions') AND name = N'IX_RunnerSessions_LastSeenAt')
    LastSeenAt datetime2 NOT NULL);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name=N'IX_RunnerSessions_LastSeenAt' AND object_id=OBJECT_ID(N'dbo.RunnerSessions'))
  CREATE INDEX IX_RunnerSessions_LastSeenAt ON dbo.RunnerSessions(LastSeenAt);
COMMIT;
GO
