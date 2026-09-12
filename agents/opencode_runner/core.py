"""Pure protocol invariants shared by real and fake runner."""
import hashlib
import struct


class RunnerError(Exception):
    pass


def result_hash(summary: str, patch: str, commit: str) -> str:
    digest = hashlib.sha256()
    for text in (summary, patch, commit):
        data = text.encode("utf-8")
        digest.update(struct.pack(">Q", len(data)))
        digest.update(data)
    return digest.hexdigest()


def clip_utf8(text: str, limit: int = 8192) -> str:
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


class PromptGuard:
    """Survives network reconnect in this process, NOT process or pod loss."""
    def __init__(self):
        self.sent = False

    def begin_send(self):
        if self.sent:
            raise RunnerError("PROMPT_ALREADY_SENT")
        # Set BEFORE I/O. An ambiguous HTTP result may never cause a blind resend.
        self.sent = True
