using Microsoft.EntityFrameworkCore;
using Microsoft.AspNetCore.DataProtection.EntityFrameworkCore;
namespace AgentPlatform;

public sealed class RepositoryRow
{
    public Guid Id { get; set; }
    public string DisplayName { get; set; } = "";
    public string CloneUrl { get; set; } = "";
    public string CredentialRef { get; set; } = "";
    public bool Enabled { get; set; } = true;
}
public sealed class RunRow
{
    public Guid Id { get; set; }
    public Guid OperationId { get; set; }
    public Guid RepositoryId { get; set; }
    public string Owner { get; set; } = "";
    public string BaseCommit { get; set; } = "";
    public string Prompt { get; set; } = "";
    public string Status { get; set; } = "ACCEPTED";
    public bool CancelDesired { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public DateTime Deadline { get; set; }
    public long NextSequence { get; set; } = 1;
    public long EarliestSequence { get; set; } = 1;
    public string? ErrorCode { get; set; }
}
public sealed class CommandRow
{
    public Guid Id { get; set; }
    public string Owner { get; set; } = "";
    public Guid RunId { get; set; }
    public string Kind { get; set; } = "";
    public string Hash { get; set; } = "";
    public string Status { get; set; } = "PENDING";
    public DateTime? LeaseUntil { get; set; }
    public Guid? LeaseToken { get; set; }
    public DateTime CreatedAt { get; set; }
}
public sealed class OperationRow
{
    public Guid Id { get; set; }
    public Guid RunId { get; set; }
    public string Status { get; set; } = "QUEUED";
    public string? Workload { get; set; }
    public string? BootId { get; set; }
    public long Fence { get; set; }
    public DateTime? LeaseUntil { get; set; }
    public string? SessionId { get; set; }
    public bool CancelDesired { get; set; }
    public long ProducerSequence { get; set; }
    public int PreviewBytes { get; set; }
    public bool Truncated { get; set; }
    public string? ErrorCode { get; set; }
}
public sealed class EventRow
{
    public Guid RunId { get; set; }
    public long Sequence { get; set; }
    public string Kind { get; set; } = "";
    public string Payload { get; set; } = "{}";
    public DateTime CreatedAt { get; set; }
}
public sealed class ReceiptRow
{
    public Guid OperationId { get; set; }
    public long Sequence { get; set; }
    public string MessageId { get; set; } = "";
    public string Hash { get; set; } = "";
    public long EventSequence { get; set; }
}
public sealed class PublicationRow
{
    public Guid RunId { get; set; }
    public string Key { get; set; } = "";
    public string Hash { get; set; } = "";
}
public sealed class ArtifactRow
{
    public Guid Id { get; set; }
    public Guid RunId { get; set; }
    public Guid OperationId { get; set; }
    public string Kind { get; set; } = "";
    public string Hash { get; set; } = "";
    public byte[] Content { get; set; } = [];
    public DateTime ExpiresAt { get; set; }
}
public sealed class PlatformDb(DbContextOptions<PlatformDb> options) : DbContext(options), IDataProtectionKeyContext
{
    public DbSet<RepositoryRow> Repositories => Set<RepositoryRow>();
    public DbSet<RunRow> Runs => Set<RunRow>();
    public DbSet<CommandRow> Commands => Set<CommandRow>();
    public DbSet<OperationRow> Operations => Set<OperationRow>();
    public DbSet<EventRow> Events => Set<EventRow>();
    public DbSet<ReceiptRow> Receipts => Set<ReceiptRow>();
    public DbSet<PublicationRow> Publications => Set<PublicationRow>();
    public DbSet<ArtifactRow> Artifacts => Set<ArtifactRow>();
    public DbSet<DataProtectionKey> DataProtectionKeys { get; set; } = null!;
    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<RepositoryRow>().HasKey(x => x.Id);
        b.Entity<RunRow>().HasKey(x => x.Id);
        b.Entity<RunRow>().Property(x => x.Owner).HasMaxLength(200).UseCollation("Latin1_General_100_BIN2");
        b.Entity<RunRow>().HasIndex(x => new { x.Owner, x.CreatedAt });
        b.Entity<RunRow>().HasIndex(x => x.OperationId).IsUnique();
        b.Entity<CommandRow>().HasKey(x => new { x.Owner, x.Id });
        b.Entity<CommandRow>().Property(x => x.Owner).HasMaxLength(200).UseCollation("Latin1_General_100_BIN2");
        b.Entity<OperationRow>().HasKey(x => x.Id);
        b.Entity<OperationRow>().HasIndex(x => x.RunId).IsUnique();
        b.Entity<EventRow>().HasKey(x => new { x.RunId, x.Sequence });
        b.Entity<ReceiptRow>().HasKey(x => new { x.OperationId, x.Sequence });
        b.Entity<ReceiptRow>().Property(x => x.MessageId).HasMaxLength(36);
        b.Entity<ReceiptRow>().HasIndex(x => new { x.OperationId, x.MessageId }).IsUnique();
        b.Entity<PublicationRow>().HasKey(x => new { x.RunId, x.Key });
        b.Entity<PublicationRow>().Property(x => x.Key).HasMaxLength(100);
        b.Entity<ArtifactRow>().HasKey(x => x.Id);
        b.Entity<ArtifactRow>().Property(x => x.Kind).HasMaxLength(20);
        b.Entity<ArtifactRow>().HasIndex(x => new { x.OperationId, x.Kind }).IsUnique();
        foreach (var e in b.Model.GetEntityTypes())
            foreach (var p in e.GetProperties().Where(x => x.ClrType == typeof(DateTime) || x.ClrType == typeof(DateTime?))) p.SetColumnType("datetime2");
    }
}
