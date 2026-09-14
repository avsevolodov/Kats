using AgentPlatform;
using AgentPlatform.Contracts.Runner.V1;
using Google.Protobuf;
int count = 0;
void Check(bool value, string name) { if (!value) throw new Exception(name); count++; Console.WriteLine($"PASS {name}"); }
Check(States.RunStatus("UNKNOWN") == "NEEDS_ATTENTION", "unknown is not failed");
Check(!States.Terminal("RUNNING") && States.Terminal("SUCCEEDED"), "terminal mapping");
Check(Wire.ResultHash("ab", "c", "") != Wire.ResultHash("a", "bc", ""), "length-delimited hash");
Check(Wire.ResultHash("", "", "") == "9d908ecfb6b256def8b49a7c504e6c889c4b0e41fe6ce3e01863dd7b61a20aa0", "empty golden hash");
var frame = new RunnerFrame { MessageId = "m", Output = new() { ProducerSequence = 9007199254740993, Text = "Привет" } };
Check(RunnerFrame.Parser.ParseFrom(frame.ToByteArray()).Equals(frame), "protobuf int64 roundtrip");
var request = new StartRun(Guid.NewGuid(), Guid.NewGuid(), new string('a',40), "change"); Rules.Validate(request); count++;
Rules.Validate(request with { BaseCommit = "main" }); Check(Rules.ValidBaseRef("main"), "branch ref allowed");
try { Rules.Validate(request with { BaseCommit = "../etc" }); throw new Exception("Expected validation"); } catch (PlatformException e) { Check(e.Code == "INVALID_COMMIT", "rejects path traversal ref"); }
try { Rules.Validate(request with { Prompt = new string('я',9000) }); throw new Exception("Expected byte limit"); } catch (PlatformException e) { Check(e.Status == 413, "UTF8 byte limit"); }
var hosts = new[] { "github.com", "example.invalid" };
var github = Rules.ValidateRepository(new UpsertRepository("Demo", "https://github.com/org/repo.git", "Pat", "GitHub", "x-access-token", "ghp_test"), hosts, true);
Check(github.Host == "github.com", "github host allowed");
try { Rules.ValidateRepository(new UpsertRepository("X", "https://evil.example/r.git", "Anonymous", "Generic"), hosts, false); throw new Exception("Expected host deny"); } catch (PlatformException e) { Check(e.Code == "HOST_NOT_ALLOWED", "deny unlisted host"); }
try { Rules.ValidateRepository(new UpsertRepository("X", "https://github.com/org/r.git", "Pat", "GitHub"), hosts, true); throw new Exception("Expected credential"); } catch (PlatformException e) { Check(e.Code == "CREDENTIAL_REQUIRED", "pat requires credential on create"); }
var listed = Wire.Serialize(new RepositoryView(Guid.NewGuid(), "Demo", "https://github.com/org/repo.git", "Pat", "GitHub", true, true));
Check(!listed.Contains("ghp_", StringComparison.Ordinal) && !listed.Contains("\"password\"", StringComparison.Ordinal), "repository view has no secret fields");
var thumbprint = "ABCDEF0123456789ABCDEF0123456789ABCDEF01";
var runnerView = new RunnerView(Guid.Parse("11111111-1111-1111-1111-111111111111"), thumbprint[^8..], "0.1.0 / 1.2.27", DateTime.UtcNow, "idle", null, null, null);
var runnerJson = Wire.Serialize(runnerView);
Check(runnerJson.Contains("\"state\":\"idle\"", StringComparison.Ordinal) && runnerJson.Contains("EF01", StringComparison.Ordinal), "runner view idle hint");
Check(!runnerJson.Contains(thumbprint, StringComparison.Ordinal), "runner view omits full workload identity");
var busyView = Wire.Serialize(runnerView with { State = "busy", RunId = Guid.Parse("22222222-2222-2222-2222-222222222222"), OperationId = Guid.Parse("33333333-3333-3333-3333-333333333333"), OperationStatus = "RUNNING" });
Check(busyView.Contains("\"state\":\"busy\"", StringComparison.Ordinal) && busyView.Contains("RUNNING", StringComparison.Ordinal), "runner view busy join fields");
Check(RunnerPresence.FreshnessSeconds == 15, "connected freshness window");
var assignment = new Assignment { AuthKind = "Pat", CloneUrl = "https://github.com/org/repo.git" };
Check(assignment.AuthKind == "Pat", "assignment auth kind");
var fetch = new RunnerFrame { MessageId = Guid.NewGuid().ToString("D"), FetchGitCredential = new() { Key = new() { OperationId = Guid.NewGuid().ToString("D"), BootId = Guid.NewGuid().ToString("D"), Fence = 1 } } };
Check(fetch.PayloadCase == RunnerFrame.PayloadOneofCase.FetchGitCredential, "fetch git credential oneof");
var confirmFrame = new RunnerFrame
{
    MessageId = Guid.NewGuid().ToString("D"),
    ConfirmationRequired = new()
    {
        Key = new() { OperationId = Guid.NewGuid().ToString("D"), BootId = Guid.NewGuid().ToString("D"), Fence = 1 },
        ProducerSequence = 2,
        RequestId = "perm1",
        Kind = "permission",
        SafePayloadJson = """{"permission":"bash"}"""
    }
};
Check(confirmFrame.PayloadCase == RunnerFrame.PayloadOneofCase.ConfirmationRequired, "confirmation required oneof");
var confirmReply = new GatewayFrame { ConfirmationReply = new() { RequestId = "perm1", Decision = "once" } };
Check(confirmReply.PayloadCase == GatewayFrame.PayloadOneofCase.ConfirmationReply, "confirmation reply oneof");
Rules.Validate(new ConfirmRun(Guid.NewGuid(), "perm1", "once")); count++;
try { Rules.Validate(new ConfirmRun(Guid.NewGuid(), "q1", "answer")); throw new Exception("Expected answers"); } catch (PlatformException e) { Check(e.Code == "ANSWERS_REQUIRED", "answer requires answers"); }
Console.WriteLine($"{count} checks passed");
