IF OBJECT_ID(N'dbo.RunnerSessions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.RunnerSessions (
        BootId nvarchar(36) NOT NULL PRIMARY KEY,
        WorkloadSubject nvarchar(200) NOT NULL,
        Version nvarchar(200) NOT NULL,
        LastSeenAt datetime2 NOT NULL
    );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.RunnerSessions') AND name = N'IX_RunnerSessions_LastSeenAt')
    CREATE INDEX IX_RunnerSessions_LastSeenAt ON dbo.RunnerSessions(LastSeenAt);
