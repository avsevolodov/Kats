using Temporalio.Workflows;
namespace AgentPlatform;

[Workflow]
public sealed class RunWorkflow
{
    private bool cancel;
    [WorkflowSignal]
    public Task RequestCancel(Guid commandId) { cancel = true; return Task.CompletedTask; }
    [WorkflowRun]
    public async Task<string> RunAsync(WorkflowInput input)
    {
        var options = new ActivityOptions { StartToCloseTimeout = TimeSpan.FromSeconds(20), RetryPolicy = new() { InitialInterval = TimeSpan.FromSeconds(1), MaximumInterval = TimeSpan.FromSeconds(10) } };
        await Workflow.ExecuteActivityAsync("Publish", new object?[] { input.RunId, "STARTING", null }, options);
        await Workflow.ExecuteActivityAsync("EnsureOperation", new object[] { input }, options);
        string? published = null;
        DateTime? abortAt = null;
        while (true)
        {
            var op = await Workflow.ExecuteActivityAsync<OperationView>("Poll", new object[] { input.OperationId }, options);
            if (States.Terminal(op.Status))
            {
                var terminal = States.RunStatus(op.Status);
                await Workflow.ExecuteActivityAsync("Publish", new object?[] { input.RunId, terminal, op.ErrorCode }, options);
                return terminal;
            }
            if (cancel || op.CancelDesired || Workflow.UtcNow >= input.Deadline)
            {
                if (abortAt == null)
                {
                    abortAt = Workflow.UtcNow;
                    await Workflow.ExecuteActivityAsync("RequestAbort", new object[] { input.OperationId }, options);
                }
                if (Workflow.UtcNow - abortAt.Value >= TimeSpan.FromSeconds(30))
                    await Workflow.ExecuteActivityAsync("MarkUnknown", new object[] { input.OperationId }, options);
            }
            var status = abortAt != null ? "CANCEL_REQUESTED" : States.RunStatus(op.Status);
            if (status != published)
            {
                await Workflow.ExecuteActivityAsync("Publish", new object?[] { input.RunId, status, null }, options);
                published = status;
            }
            await Workflow.DelayAsync(TimeSpan.FromSeconds(5));
        }
    }
}
