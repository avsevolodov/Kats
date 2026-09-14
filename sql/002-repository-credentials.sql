-- Additive upgrade for existing DBs created before repository credential columns.
-- Safe to re-run. Prefer this when 001-initial.sql was already applied without AuthKind.
SET XACT_ABORT ON;
GO
BEGIN TRANSACTION;
DECLARE @lock int; EXEC @lock=sp_getapplock @Resource=N'agent-platform-schema-v1',@LockMode='Exclusive',@LockOwner='Transaction';
IF @lock<0 THROW 51000,'Schema lock failed',1;
IF COL_LENGTH(N'dbo.Repositories',N'AuthKind') IS NULL
  ALTER TABLE dbo.Repositories ADD AuthKind nvarchar(32) NOT NULL CONSTRAINT DF_Repositories_AuthKind DEFAULT N'Anonymous';
IF COL_LENGTH(N'dbo.Repositories',N'ProviderHint') IS NULL
  ALTER TABLE dbo.Repositories ADD ProviderHint nvarchar(32) NOT NULL CONSTRAINT DF_Repositories_ProviderHint DEFAULT N'Generic';
IF COL_LENGTH(N'dbo.Repositories',N'CredentialCipher') IS NULL
  ALTER TABLE dbo.Repositories ADD CredentialCipher varbinary(max) NULL;
COMMIT;
GO
UPDATE dbo.Repositories
SET AuthKind=N'Pat'
WHERE CredentialRef <> N'' AND AuthKind=N'Anonymous' AND CredentialCipher IS NULL;
GO
