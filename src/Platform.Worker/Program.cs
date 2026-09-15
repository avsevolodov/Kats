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
builder.Services.AddSingleton<ChatStore>();
builder.Services.AddHostedService<ExecutionHost>();
await builder.Build().RunAsync();

sealed class Activities(SqlStore store, ChatStore chat)
{
    [Activity] public Task EnsureOperation(WorkflowInput input) => store.EnsureOperation(input);
    [Activity] public Task<OperationView> Poll(Guid op) => store.Poll(op);
    [Activity] public async Task Publish(Guid run, string state, string? error)
    {
        await store.Publish(run, state, error);
        await chat.ProjectRunStatus(run, state, error);
    }
    [Activity] public Task RequestAbort(Guid op) => store.RequestAbort(op);
    [Activity] public Task MarkUnknown(Guid op) => store.MarkUnknown(op);
    [Activity] public Task PublishTask(Guid taskId, string state, string? error) => chat.SetTaskStatus(taskId, state);
    [Activity] public async Task<AgentTaskView> PollTask(Guid taskId)
    {
        var row = await chat.GetTaskRow(taskId) ?? throw new ApplicationFailureException("TASK_NOT_FOUND");
        return new AgentTaskView(row.Id, row.ConversationId, row.Status, row.GoalRevision, row.WorkflowId, row.WallDeadline, row.CancelDesired);
    }
    [Activity] public Task RequestTaskAbort(Guid taskId) => chat.SetTaskStatus(taskId, "CANCEL_REQUESTED");
    [Activity] public Task MarkTaskNeedsAttention(Guid taskId) => chat.SetTaskStatus(taskId, "NEEDS_ATTENTION");
    [Activity] public Task ReconcileTaskChildren(Guid taskId) => chat.ReconcileTaskChildren(taskId);
    [Activity] public async Task AbortTaskRuns(Guid taskId)
    {
        var linked = await chat.ListLinkedRunsForAbort(taskId);
        foreach (var (runId, owner) in linked)
            await store.Cancel(owner, runId, Guid.NewGuid());
    }
}
sealed class ExecutionHost(SqlStore store, ChatStore chat, IConfiguration config, ILogger<ExecutionHost> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var options = new TemporalClientConnectOptions(config["Temporal:Endpoint"] ?? "localhost:7233") { Namespace = config["Temporal:Namespace"] ?? "default" };
        var cert = config["Temporal:CertPath"];
        if (!string.IsNullOrEmpty(cert)) options.Tls = new() { ClientCert = await File.ReadAllBytesAsync(cert, stoppingToken), ClientPrivateKey = await File.ReadAllBytesAsync(config["Temporal:KeyPath"]!, stoppingToken), ServerRootCACert = await File.ReadAllBytesAsync(config["Temporal:CaPath"]!, stoppingToken) };
        var client = await TemporalClient.ConnectAsync(options);
        var queue = config["Temporal:TaskQueue"] ?? "agent-platform-mvp-v1";
        using var worker = new TemporalWorker(client, new TemporalWorkerOptions(queue)
            .AddWorkflow<RunWorkflow>()
            .AddWorkflow<TaskWorkflow>()
            .AddAllActivities(new Activities(store, chat)));
        await Task.WhenAll(
            worker.ExecuteAsync(stoppingToken),
            Dispatch(client, queue, stoppingToken),
            DispatchChat(client, queue, stoppingToken),
            Reap(stoppingToken));
    }

    async Task Dispatch(ITemporalClient client, string queue, CancellationToken ct)
    {
        log.LogInformation("Command dispatcher started");
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var c = await store.ClaimCommand();
                if (c == null) { await Task.Delay(500, ct); continue; }
                var input = await store.Input(c.RunId);
                var id = $"run-{c.RunId:D}";
                log.LogInformation("Claimed command kind={Kind} command={CommandId} run={RunId} workflow={WorkflowId}", c.Kind, c.Id, c.RunId, id);
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
                log.LogInformation("Command marked DISPATCHED kind={Kind} command={CommandId}", c.Kind, c.Id);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (Exception e) { log.LogWarning("Dispatcher unavailable: {ErrorType}", e.GetType().Name); await Task.Delay(1000, ct); }
        }
        log.LogInformation("Command dispatcher stopped");
    }

    async Task DispatchChat(ITemporalClient client, string queue, CancellationToken ct)
    {
        log.LogInformation("Chat task dispatcher started");
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var c = await chat.ClaimChatCommand();
                if (c == null) { await Task.Delay(500, ct); continue; }
                var taskId = c.AcceptedResourceId;
                var workflowId = $"task-{taskId:D}";
                if (c.Kind == "START_TASK")
                {
                    var input = await chat.TaskInput(taskId);
                    try
                    {
                        await client.StartWorkflowAsync(
                            (TaskWorkflow w) => w.RunAsync(input),
                            new(workflowId, queue) { IdReusePolicy = WorkflowIdReusePolicy.RejectDuplicate });
                    }
                    catch (WorkflowAlreadyStartedException) { /* stable TaskId */ }
                }
                else if (c.Kind == "SIGNAL_CANCEL")
                {
                    try
                    {
                        await client.GetWorkflowHandle<TaskWorkflow>(workflowId).SignalAsync(w => w.RequestCancel(c.CommandId));
                    }
                    catch (Exception e)
                    {
                        log.LogWarning("Chat cancel signal skipped: {ErrorType}", e.GetType().Name);
                    }
                }
                else if (c.Kind == "SIGNAL_CHILD_COMPLETED")
                {
                    try
                    {
                        await client.GetWorkflowHandle<TaskWorkflow>(workflowId).SignalAsync(w => w.ChildCompleted(c.CommandId));
                    }
                    catch (Exception e)
                    {
                        log.LogWarning("Chat child-completed signal skipped: {ErrorType}", e.GetType().Name);
                        await chat.ReconcileTaskChildren(taskId);
                    }
                }
                else if (c.Kind == "ABORT_TASK_RUNS")
                {
                    try
                    {
                        var linked = await chat.ListLinkedRunsForAbort(taskId);
                        foreach (var (runId, owner) in linked)
                            await store.Cancel(owner, runId, Guid.NewGuid());
                    }
                    catch (Exception e)
                    {
                        log.LogWarning("Abort task runs skipped: {ErrorType}", e.GetType().Name);
                    }
                }
                await chat.MarkChatDispatched(c.CommandId, c.OwnerSubject);
                log.LogInformation("Chat command DISPATCHED kind={Kind} task={TaskId}", c.Kind, taskId);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (Exception e) { log.LogWarning("Chat dispatcher unavailable: {ErrorType}", e.GetType().Name); await Task.Delay(1000, ct); }
        }
        log.LogInformation("Chat task dispatcher stopped");
    }

    async Task Reap(CancellationToken ct)
    {
        log.LogInformation("Lease reaper started");
        while (!ct.IsCancellationRequested)
        {
            try { await store.Reap(); }
            catch (Exception e) { log.LogWarning("Lease reaper unavailable: {ErrorType}", e.GetType().Name); }
            await Task.Delay(5000, ct);
        }
        log.LogInformation("Lease reaper stopped");
    }
}
