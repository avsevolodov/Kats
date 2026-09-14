import asyncio
import hashlib
import struct
import subprocess
import pytest
from opencode_runner.core import PromptGuard, RunnerError, clip_utf8, result_hash
from opencode_runner.workspace import Workspace
from opencode_runner import runner_pb2 as pb


def test_result_hash_is_length_delimited_and_unicode_safe():
    parts = ["Привет", "+hello\n", "a"*40]
    payload = b"".join(struct.pack(">Q", len(s.encode()))+s.encode() for s in parts)
    assert result_hash(*parts) == hashlib.sha256(payload).hexdigest()
    assert result_hash("ab", "c", "") != result_hash("a", "bc", "")


def test_no_second_prompt_after_ambiguous_network_result():
    g = PromptGuard(); g.begin_send()
    with pytest.raises(RunnerError, match="PROMPT_ALREADY_SENT"):
        g.begin_send()


def test_utf8_boundaries():
    s = clip_utf8("я"*9000,8191)
    assert len(s.encode()) == 8190


def test_protobuf_preserves_big_sequences():
    f = pb.RunnerFrame(message_id="m", output=pb.OutputBatch(producer_sequence=2**53+1, text="текст"))
    assert pb.RunnerFrame.FromString(f.SerializeToString()) == f


def test_patch_includes_added_files(tmp_path):
    w = Workspace(str(tmp_path)); w.repo.mkdir()
    def git(*args):
        return subprocess.run(["git", *args], cwd=w.repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
    git("init"); git("config","user.name","Fixture"); git("config","user.email","fixture@example.invalid")
    (w.repo/"a.txt").write_text("before\n"); git("add","."); git("commit","-m","base")
    (w.repo/"a.txt").write_text("after\n"); (w.repo/"new.txt").write_text("new\n")
    patch = asyncio.run(w.patch())
    assert "new.txt" in patch and "+after" in patch
    git("reset","--hard","HEAD"); git("clean","-fd")
    subprocess.run(["git","apply","-"],input=patch.encode(),cwd=w.repo,check=True)
    assert (w.repo/"new.txt").read_text() == "new\n"


def test_symlink_rejected(tmp_path):
    w = Workspace(str(tmp_path)); w.repo.mkdir(); (w.repo/"link").symlink_to("/etc/passwd")
    with pytest.raises(RunnerError,match="SYMLINK_UNSUPPORTED"):
        asyncio.run(w.patch())
