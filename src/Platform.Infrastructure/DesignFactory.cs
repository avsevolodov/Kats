using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
namespace AgentPlatform;
public sealed class DesignFactory : IDesignTimeDbContextFactory<PlatformDb>
{
    public PlatformDb CreateDbContext(string[] args) => new(new DbContextOptionsBuilder<PlatformDb>().UseSqlServer(
        Environment.GetEnvironmentVariable("ConnectionStrings__Platform") ?? "Server=localhost;Database=AgentPlatform;Integrated Security=true;Encrypt=true").Options);
}
