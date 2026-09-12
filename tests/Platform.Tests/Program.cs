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
try { Rules.Validate(request with { BaseCommit = "main" }); throw new Exception("Expected validation"); } catch (PlatformException e) { Check(e.Code == "INVALID_COMMIT", "immutable commit validation"); }
try { Rules.Validate(request with { Prompt = new string('я',9000) }); throw new Exception("Expected byte limit"); } catch (PlatformException e) { Check(e.Status == 413, "UTF8 byte limit"); }
Console.WriteLine($"{count} checks passed");
