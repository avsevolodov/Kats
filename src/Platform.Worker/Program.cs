using AgentPlatform;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Temporalio.Activities;
using Temporalio.Client;
using Temporalio.Worker;
using Temporalio.Exceptions;
using Temporalio.Api.Enums.V1;

var builder = Host.CreateApplicationBuilder(args);
builder.Services.AddDbContextFactory<PlatformDb>(o => o.UseSqlServer(builder.Configuration.GetConnectionString("Platform") ?? throw new InvalidOperationException("ConnectionStrings:Platform required")));
builder.Services.AddDataProtection().SetApplicationName("AgentPlatformMvp").PersistKeysToDbContext<PlatformDb>();
builder.Services.AddSingleton<SqlStore>();
builder.Services.AddHostedService<ExecutionHost>();
await builder.Build().RunAsync();

sealed class Activities(SqlStore store)
{
    [Activity] public Task EnsureOperation(WorkflowInput input) => store.EnsureOperation(input);
    [Activity] public Task<OperationView> Poll(Guid op) => store.Poll(op);
    [Activity] public Task Publish(Guid run, string state, string? error) => store.Publish(run, state, error);
    [Activity] public Task RequestAbort(Guid op) => store.RequestAbort(op);
    [Activity] public Task MarkUnknown(Guid op) => store.MarkUnknown(op);
}
sealed class ExecutionHost(SqlStore store, IConfiguration config, ILogger<ExecutionHost> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var options = new TemporalClientConnectOptions(config["Temporal:Endpoint"] ?? "localhost:7233") { Namespace = config["Temporal:Namespace"] ?? "default" };
        var cert = config["Temporal:CertPath"];
        if (!string.IsNullOrEmpty(cert)) options.Tls = new() { ClientCert = await File.ReadAllBytesAsync(cert, stoppingToken), ClientPrivateKey = await File.ReadAllBytesAsync(config["Temporal:KeyPath"]!, stoppingToken), ServerRootCACert = await File.ReadAllBytesAsync(config["Temporal:CaPath"]!, stoppingToken) };
        var client = await TemporalClient.ConnectAsync(options);
        var queue = config["Temporal:TaskQueue"] ?? "agent-platform-mvp-v1";
        using var worker = new TemporalWorker(client, new TemporalWorkerOptions(queue).AddWorkflow<RunWorkflow>().AddAllActivities(new Activities(store)));
        await Task.WhenAll(worker.ExecuteAsync(stoppingToken), Dispatch(client, queue, stoppingToken), Reap(stoppingToken));
    }
    async Task Dispatch(ITemporalClient client, string queue, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var c = await store.ClaimCommand();
                if (c == null) { await Task.Delay(500, ct); continue; }
                var input = await store.Input(c.RunId);
                var id = $"run-{c.RunId:D}";
                if (c.Kind == "START")
                {
                    try { await client.StartWorkflowAsync((RunWorkflow w) => w.RunAsync(input), new(id, queue) { IdReusePolicy = WorkflowIdReusePolicy.RejectDuplicate }); }
                    catch (WorkflowAlreadyStartedException) { /* Same stable RunId and immutable inbox input; never use a new ID. */ }
                }
                else
                {
                    var view = await store.Get(c.Owner, c.RunId);
                    if (!States.Terminal(view.Status)) await client.GetWorkflowHandle<RunWorkflow>(id).SignalAsync(w => w.RequestCancel(c.Id));
                }
                await store.Dispatched(c);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (Exception e) { log.LogWarning("Dispatcher unavailable: {ErrorType}", e.GetType().Name); await Task.Delay(1000, ct); }
        }
    }
    async Task Reap(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try { await store.Reap(); }
            catch (Exception e) { log.LogWarning("Lease reaper unavailable: {ErrorType}", e.GetType().Name); }
            await Task.Delay(5000, ct);
        }
    }
}
