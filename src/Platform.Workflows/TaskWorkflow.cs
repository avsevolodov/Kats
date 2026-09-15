using Temporalio.Workflows;

namespace AgentPlatform;

/// <summary>
/// Owns AgentTask lifecycle only. No LLM, SQL, network, or filesystem in this class.
/// </summary>
[Workflow]
public sealed class TaskWorkflow
{
    private bool cancel;
    private bool childWakeup;

    [WorkflowSignal]
    public Task RequestCancel(Guid commandId) { cancel = true; return Task.CompletedTask; }

    [WorkflowSignal]
    public Task ChildCompleted(Guid invocationId) { childWakeup = true; return Task.CompletedTask; }

    [WorkflowRun]
    public async Task<string> RunAsync(TaskWorkflowInput input)
    {
        var options = new ActivityOptions
        {
            StartToCloseTimeout = TimeSpan.FromSeconds(30),
            RetryPolicy = new() { InitialInterval = TimeSpan.FromSeconds(1), MaximumInterval = TimeSpan.FromSeconds(10) }
        };
        await Workflow.ExecuteActivityAsync("PublishTask", new object?[] { input.TaskId, "ACTIVE", null }, options);
        string? published = null;
        DateTime? abortAt = null;
        while (true)
        {
            var view = await Workflow.ExecuteActivityAsync<AgentTaskView>("PollTask", new object[] { input.TaskId }, options);
            if (States.Terminal(view.Status))
            {
                await Workflow.ExecuteActivityAsync("PublishTask", new object?[] { input.TaskId, view.Status, null }, options);
                return view.Status;
            }
            if (cancel || view.CancelDesired || Workflow.UtcNow >= input.Deadline)
            {
                abortAt ??= Workflow.UtcNow;
                await Workflow.ExecuteActivityAsync("RequestTaskAbort", new object[] { input.TaskId }, options);
                if (Workflow.UtcNow - abortAt.Value >= TimeSpan.FromSeconds(30))
                {
                    await Workflow.ExecuteActivityAsync("MarkTaskNeedsAttention", new object[] { input.TaskId }, options);
                    await Workflow.ExecuteActivityAsync("PublishTask", new object?[] { input.TaskId, "NEEDS_ATTENTION", "CANCEL_TIMEOUT" }, options);
                    return "NEEDS_ATTENTION";
                }
            }
            if (childWakeup)
            {
                childWakeup = false;
                await Workflow.ExecuteActivityAsync("ReconcileTaskChildren", new object[] { input.TaskId }, options);
            }
            var status = abortAt != null ? "CANCEL_REQUESTED" : view.Status;
            if (status != published)
            {
                await Workflow.ExecuteActivityAsync("PublishTask", new object?[] { input.TaskId, status, null }, options);
                published = status;
            }
            await Workflow.DelayAsync(TimeSpan.FromSeconds(5));
        }
    }
}
