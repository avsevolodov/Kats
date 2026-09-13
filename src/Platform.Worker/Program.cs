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
var protection = builder.Services.AddDataProtection().SetApplicationName("AgentPlatformMvp").PersistKeysToDbContext<PlatformDb>();
var keyPath = builder.Configuration["Security:DataProtectionCertificate"];
if (!string.IsNullOrEmpty(keyPath))
    protection.ProtectKeysWithCertificate(System.Security.Cryptography.X509Certificates.X509CertificateLoader.LoadPkcs12FromFile(
        keyPath, builder.Configuration["Security:DataProtectionPassword"]));
builder.Services.AddSingleton<SqlStore>();
builder.Services.AddHostedService<ExecutionHost>();
await builder.Build().RunAsync();

sealed class Activities(SqlStore store, ILogger<Activities> log)
{
    [Activity] public async Task EnsureOperation(WorkflowInput input)
    {
        log.LogInformation("EnsureOperation run={RunId} operation={OperationId}", input.RunId, input.OperationId);
        await store.EnsureOperation(input);
    }
    [Activity] public Task<OperationView> Poll(Guid op) => store.Poll(op);
    [Activity] public async Task Publish(Guid run, string state, string? error)
    {
        log.LogInformation("Publish run={RunId} status={Status} error={Error}", run, state, error);
        await store.Publish(run, state, error);
    }
    [Activity] public async Task RequestAbort(Guid op)
    {
        log.LogInformation("RequestAbort operation={OperationId}", op);
        await store.RequestAbort(op);
    }
    [Activity] public async Task MarkUnknown(Guid op)
    {
        log.LogInformation("MarkUnknown operation={OperationId}", op);
        await store.MarkUnknown(op);
    }
}

sealed class ExecutionHost(SqlStore store, IConfiguration config, ILogger<ExecutionHost> log, ILoggerFactory logs) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var endpoint = config["Temporal:Endpoint"] ?? "localhost:7233";
        var ns = config["Temporal:Namespace"] ?? "default";
        var queue = config["Temporal:TaskQueue"] ?? "agent-platform-mvp-v1";
        log.LogInformation("Worker starting Temporal endpoint={Endpoint} namespace={Namespace} queue={Queue}", endpoint, ns, queue);
        try
        {
            var options = new TemporalClientConnectOptions(endpoint) { Namespace = ns };
            var cert = config["Temporal:CertPath"];
            if (!string.IsNullOrEmpty(cert))
            {
                options.Tls = new()
                {
                    ClientCert = await File.ReadAllBytesAsync(cert, stoppingToken),
                    ClientPrivateKey = await File.ReadAllBytesAsync(config["Temporal:KeyPath"]!, stoppingToken),
                    ServerRootCACert = await File.ReadAllBytesAsync(config["Temporal:CaPath"]!, stoppingToken)
                };
                log.LogInformation("Temporal mTLS enabled");
            }
            log.LogInformation("Connecting to Temporal…");
            var client = await TemporalClient.ConnectAsync(options);
            log.LogInformation("Temporal connected");
            var activities = new Activities(store, logs.CreateLogger<Activities>());
            using var worker = new TemporalWorker(client, new TemporalWorkerOptions(queue)
                .AddWorkflow<RunWorkflow>()
                .AddAllActivities(activities));
            log.LogInformation("Temporal worker polling queue={Queue}", queue);
            await Task.WhenAll(
                worker.ExecuteAsync(stoppingToken),
                Dispatch(client, queue, stoppingToken),
                Reap(stoppingToken));
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            log.LogInformation("Worker stopped");
        }
        catch (Exception e)
        {
            log.LogError(e, "Worker failed to start or run: {Message}", e.Message);
            throw;
        }
    }

    async Task Dispatch(ITemporalClient client, string queue, CancellationToken ct)
    {
        log.LogInformation("Command dispatcher started");
        var idleSince = DateTime.UtcNow;
        var lastIdleLog = DateTime.MinValue;
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var c = await store.ClaimCommand();
                if (c == null)
                {
                    var now = DateTime.UtcNow;
                    if (now - lastIdleLog >= TimeSpan.FromSeconds(30))
                    {
                        log.LogInformation("Dispatcher idle, waiting for PENDING commands ({Seconds}s)", (int)(now - idleSince).TotalSeconds);
                        lastIdleLog = now;
                    }
                    await Task.Delay(500, ct);
                    continue;
                }
                idleSince = DateTime.UtcNow;
                lastIdleLog = DateTime.MinValue;
                var input = await store.Input(c.RunId);
                var id = $"run-{c.RunId:D}";
                log.LogInformation("Claimed command kind={Kind} command={CommandId} run={RunId} workflow={WorkflowId}", c.Kind, c.Id, c.RunId, id);
                if (c.Kind == "START")
                {
                    try
                    {
                        await client.StartWorkflowAsync((RunWorkflow w) => w.RunAsync(input), new(id, queue) { IdReusePolicy = WorkflowIdReusePolicy.RejectDuplicate });
                        log.LogInformation("Started workflow {WorkflowId}", id);
                    }
                    catch (WorkflowAlreadyStartedException)
                    {
                        // Same stable RunId and immutable inbox input; never use a new ID.
                        log.LogInformation("Workflow already started {WorkflowId}; marking command dispatched", id);
                    }
                }
                else
                {
                    var view = await store.Get(c.Owner, c.RunId);
                    if (!States.Terminal(view.Status))
                    {
                        await client.GetWorkflowHandle<RunWorkflow>(id).SignalAsync(w => w.RequestCancel(c.Id));
                        log.LogInformation("Signaled cancel on {WorkflowId} command={CommandId}", id, c.Id);
                    }
                    else log.LogInformation("Skip cancel signal; run already terminal status={Status}", view.Status);
                }
                await store.Dispatched(c);
                log.LogInformation("Command marked DISPATCHED kind={Kind} command={CommandId}", c.Kind, c.Id);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (Exception e)
            {
                log.LogWarning(e, "Dispatcher error: {ErrorType}: {Message}", e.GetType().Name, e.Message);
                await Task.Delay(1000, ct);
            }
        }
        log.LogInformation("Command dispatcher stopped");
    }

    async Task Reap(CancellationToken ct)
    {
        log.LogInformation("Lease reaper started");
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var n = await store.Reap();
                if (n > 0) log.LogInformation("Reaper marked {Count} expired operation(s) UNKNOWN", n);
            }
            catch (Exception e)
            {
                log.LogWarning(e, "Lease reaper error: {ErrorType}: {Message}", e.GetType().Name, e.Message);
            }
            await Task.Delay(5000, ct);
        }
        log.LogInformation("Lease reaper stopped");
    }
}
