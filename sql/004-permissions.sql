IF OBJECT_ID(N'dbo.Permissions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Permissions (
        OperationId uniqueidentifier NOT NULL,
        RequestId nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL,
        Description nvarchar(max) NOT NULL,
        Decision nvarchar(max) NOT NULL,
        Status nvarchar(max) NOT NULL,
        CreatedAt datetime2 NOT NULL,
        DecidedAt datetime2 NULL,
        DecidedBy nvarchar(max) NULL,
        CONSTRAINT PK_Permissions PRIMARY KEY (OperationId, RequestId),
        CONSTRAINT FK_Permissions_Operations FOREIGN KEY (OperationId) REFERENCES dbo.Operations(Id)
    );
END;
