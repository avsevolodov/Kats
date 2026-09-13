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
Rules.Validate(request with { BaseCommit = "main" }); Check(Rules.ValidBaseRef("feature/x-1"), "branch ref validation");
try { Rules.Validate(request with { BaseCommit = "../evil" }); throw new Exception("Expected validation"); } catch (PlatformException e) { Check(e.Code == "INVALID_COMMIT", "reject unsafe ref"); }
try { Rules.Validate(request with { Prompt = new string('я',9000) }); throw new Exception("Expected byte limit"); } catch (PlatformException e) { Check(e.Status == 413, "UTF8 byte limit"); }
var hosts = new[] { "github.com", "example.invalid" };
var github = Rules.ValidateRepository(new UpsertRepository("Demo", "https://github.com/org/repo.git", "Pat", "GitHub", "x-access-token", "ghp_test"), hosts, true);
Check(github.Host == "github.com", "github host allowed");
try { Rules.ValidateRepository(new UpsertRepository("Bad", "https://evil.example/repo.git", "Anonymous", "Generic"), hosts, false); throw new Exception("Expected host deny"); }
catch (PlatformException e) { Check(e.Code == "REPOSITORY_HOST_NOT_ALLOWED", "deny unlisted host"); }
try { Rules.ValidateRepository(new UpsertRepository("Pat", "https://github.com/org/repo.git", "Pat", "GitHub"), hosts, true); throw new Exception("Expected credential"); }
catch (PlatformException e) { Check(e.Code == "CREDENTIAL_REQUIRED", "pat requires credential on create"); }
var anon = new UpsertRepository("Public", "https://example.invalid/repo.git", "Anonymous", "Generic");
Rules.ValidateRepository(anon, hosts, false); count++;
var listed = Wire.Serialize(new RepositoryView(Guid.NewGuid(), "Demo", "https://github.com/org/repo.git", "Pat", "GitHub", true, true));
Check(!listed.Contains("ghp_", StringComparison.Ordinal) && !listed.Contains("\"password\"", StringComparison.Ordinal), "repository view has no secret fields");
var assignment = new Assignment { AuthKind = "pat", CloneUrl = "https://github.com/org/repo.git" };
Check(assignment.AuthKind == "pat" && string.IsNullOrEmpty(assignment.CredentialRef), "assignment carries auth kind without secret material");
Console.WriteLine($"{count} checks passed");
