SET XACT_ABORT ON;
BEGIN TRANSACTION;
DECLARE @lock int; EXEC @lock=sp_getapplock @Resource=N'agent-platform-schema-v1',@LockMode='Exclusive',@LockOwner='Transaction';
IF @lock<0 THROW 51000,'Schema lock failed',1;
IF OBJECT_ID(N'dbo.Repositories',N'U') IS NULL
  CREATE TABLE dbo.Repositories(
    Id uniqueidentifier NOT NULL PRIMARY KEY,
    DisplayName nvarchar(max) NOT NULL,
    CloneUrl nvarchar(max) NOT NULL,
    CredentialRef nvarchar(max) NOT NULL CONSTRAINT DF_Repositories_CredentialRef DEFAULT N'',
    AuthKind nvarchar(32) NOT NULL CONSTRAINT DF_Repositories_AuthKind DEFAULT N'Anonymous',
    ProviderHint nvarchar(32) NOT NULL CONSTRAINT DF_Repositories_ProviderHint DEFAULT N'Generic',
    CredentialCipher varbinary(max) NULL,
    Enabled bit NOT NULL);
ELSE
BEGIN
  IF COL_LENGTH(N'dbo.Repositories',N'AuthKind') IS NULL
    ALTER TABLE dbo.Repositories ADD AuthKind nvarchar(32) NOT NULL CONSTRAINT DF_Repositories_AuthKind DEFAULT N'Anonymous';
  IF COL_LENGTH(N'dbo.Repositories',N'ProviderHint') IS NULL
    ALTER TABLE dbo.Repositories ADD ProviderHint nvarchar(32) NOT NULL CONSTRAINT DF_Repositories_ProviderHint DEFAULT N'Generic';
  IF COL_LENGTH(N'dbo.Repositories',N'CredentialCipher') IS NULL
    ALTER TABLE dbo.Repositories ADD CredentialCipher varbinary(max) NULL;
END
IF OBJECT_ID(N'dbo.Runs',N'U') IS NULL
  CREATE TABLE dbo.Runs(Id uniqueidentifier NOT NULL PRIMARY KEY, OperationId uniqueidentifier NOT NULL UNIQUE, RepositoryId uniqueidentifier NOT NULL REFERENCES Repositories(Id), Owner nvarchar(200) NOT NULL, BaseCommit nvarchar(max) NOT NULL, Prompt nvarchar(max) NOT NULL, Status nvarchar(max) NOT NULL, CancelDesired bit NOT NULL, CreatedAt datetime2 NOT NULL, UpdatedAt datetime2 NOT NULL, Deadline datetime2 NOT NULL, NextSequence bigint NOT NULL, EarliestSequence bigint NOT NULL, ErrorCode nvarchar(max) NULL);
IF OBJECT_ID(N'dbo.Commands',N'U') IS NULL
  CREATE TABLE dbo.Commands(Id uniqueidentifier NOT NULL, Owner nvarchar(200) NOT NULL, RunId uniqueidentifier NOT NULL REFERENCES Runs(Id), Kind nvarchar(max) NOT NULL, Hash nvarchar(max) NOT NULL, Status nvarchar(max) NOT NULL, LeaseUntil datetime2 NULL, LeaseToken uniqueidentifier NULL, CreatedAt datetime2 NOT NULL, CONSTRAINT PK_Commands PRIMARY KEY(Owner,Id));
IF OBJECT_ID(N'dbo.Operations',N'U') IS NULL
  CREATE TABLE dbo.Operations(Id uniqueidentifier NOT NULL PRIMARY KEY, RunId uniqueidentifier NOT NULL UNIQUE REFERENCES Runs(Id), Status nvarchar(max) NOT NULL, Workload nvarchar(max) NULL, BootId nvarchar(max) NULL, Fence bigint NOT NULL, LeaseUntil datetime2 NULL, SessionId nvarchar(max) NULL, CancelDesired bit NOT NULL, ProducerSequence bigint NOT NULL, PreviewBytes int NOT NULL, Truncated bit NOT NULL, ErrorCode nvarchar(max) NULL);
IF OBJECT_ID(N'dbo.Events',N'U') IS NULL
  CREATE TABLE dbo.Events(RunId uniqueidentifier NOT NULL REFERENCES Runs(Id), Sequence bigint NOT NULL, Kind nvarchar(max) NOT NULL, Payload nvarchar(max) NOT NULL, CreatedAt datetime2 NOT NULL, CONSTRAINT PK_Events PRIMARY KEY(RunId,Sequence));
IF OBJECT_ID(N'dbo.Receipts',N'U') IS NULL
  CREATE TABLE dbo.Receipts(OperationId uniqueidentifier NOT NULL REFERENCES Operations(Id), Sequence bigint NOT NULL, MessageId nvarchar(36) NOT NULL, Hash nvarchar(max) NOT NULL, EventSequence bigint NOT NULL, CONSTRAINT PK_Receipts PRIMARY KEY(OperationId,Sequence), CONSTRAINT UQ_ReceiptMessage UNIQUE(OperationId,MessageId));
IF OBJECT_ID(N'dbo.Publications',N'U') IS NULL
  CREATE TABLE dbo.Publications(RunId uniqueidentifier NOT NULL REFERENCES Runs(Id), [Key] nvarchar(100) NOT NULL, Hash nvarchar(max) NOT NULL, CONSTRAINT PK_Publications PRIMARY KEY(RunId,[Key]));
IF OBJECT_ID(N'dbo.Artifacts',N'U') IS NULL
  CREATE TABLE dbo.Artifacts(Id uniqueidentifier NOT NULL PRIMARY KEY, RunId uniqueidentifier NOT NULL REFERENCES Runs(Id), OperationId uniqueidentifier NOT NULL REFERENCES Operations(Id), Kind nvarchar(20) NOT NULL, Hash nvarchar(max) NOT NULL, Content varbinary(max) NOT NULL, ExpiresAt datetime2 NOT NULL, CONSTRAINT UQ_ArtifactKind UNIQUE(OperationId,Kind));
IF OBJECT_ID(N'dbo.DataProtectionKeys',N'U') IS NULL
  CREATE TABLE dbo.DataProtectionKeys(Id int IDENTITY NOT NULL PRIMARY KEY, FriendlyName nvarchar(max) NULL, Xml nvarchar(max) NULL);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_Runs_Owner_CreatedAt' AND object_id=OBJECT_ID('dbo.Runs')) CREATE INDEX IX_Runs_Owner_CreatedAt ON dbo.Runs(Owner,CreatedAt);
IF COL_LENGTH(N'dbo.Repositories',N'AuthKind') IS NOT NULL
  UPDATE dbo.Repositories SET AuthKind=N'Pat' WHERE CredentialRef <> N'' AND AuthKind=N'Anonymous' AND CredentialCipher IS NULL;
COMMIT;
