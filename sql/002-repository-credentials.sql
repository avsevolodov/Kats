-- Upgrade existing MVP databases. Also included in 001-initial.sql.
IF COL_LENGTH(N'dbo.Repositories', N'AuthKind') IS NULL
    ALTER TABLE dbo.Repositories ADD AuthKind nvarchar(32) NOT NULL CONSTRAINT DF_Repositories_AuthKind DEFAULT N'Anonymous';
IF COL_LENGTH(N'dbo.Repositories', N'ProviderHint') IS NULL
    ALTER TABLE dbo.Repositories ADD ProviderHint nvarchar(32) NOT NULL CONSTRAINT DF_Repositories_ProviderHint DEFAULT N'Generic';
IF COL_LENGTH(N'dbo.Repositories', N'CredentialCipher') IS NULL
    ALTER TABLE dbo.Repositories ADD CredentialCipher varbinary(max) NULL;
