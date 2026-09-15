"""LangGraph BaseCheckpointSaver adapter → C# internal checkpoint API → MSSQL.

Implements get/list/put/put_writes semantics required by pinned LangGraph.
Does not use pickle; payloads are versioned codec bytes (JSON envelope).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


CODEC_VERSION = "kats-checkpoint-v1"


@dataclass
class CheckpointTuple:
    config: dict[str, Any]
    checkpoint: dict[str, Any]
    metadata: dict[str, Any]
    parent_config: dict[str, Any] | None = None
    pending_writes: list[tuple[str, str, Any]] = field(default_factory=list)


class CheckpointClient:
    """Transport to C# CheckpointService. Tests may inject an in-memory backend;
    live acceptance requires real MSSQL roundtrip (see T004/T014)."""

    async def get(self, thread_id: str, namespace: str, checkpoint_id: str | None) -> dict | None:
        raise NotImplementedError

    async def list(self, thread_id: str, namespace: str, limit: int = 10) -> list[dict]:
        raise NotImplementedError

    async def put(
        self,
        thread_id: str,
        namespace: str,
        checkpoint_id: str,
        parent_checkpoint_id: str | None,
        checkpoint: dict,
        metadata: dict,
        fence: int,
    ) -> None:
        raise NotImplementedError

    async def put_writes(
        self,
        thread_id: str,
        namespace: str,
        checkpoint_id: str,
        task_id: str,
        writes: Sequence[tuple[int, str, Any]],
    ) -> None:
        raise NotImplementedError


class InMemoryCheckpointClient(CheckpointClient):
    """Unit-test double only — does not prove SQL recovery (FR-207)."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], dict] = {}
        self.writes: dict[tuple[str, str, str, str, int], dict] = {}

    async def get(self, thread_id: str, namespace: str, checkpoint_id: str | None) -> dict | None:
        if checkpoint_id:
            return self.rows.get((thread_id, namespace, checkpoint_id))
        items = [v for (t, n, _), v in self.rows.items() if t == thread_id and n == namespace]
        return items[-1] if items else None

    async def list(self, thread_id: str, namespace: str, limit: int = 10) -> list[dict]:
        items = [v for (t, n, _), v in self.rows.items() if t == thread_id and n == namespace]
        return items[-limit:]

    async def put(self, thread_id, namespace, checkpoint_id, parent_checkpoint_id, checkpoint, metadata, fence):
        key = (thread_id, namespace, checkpoint_id)
        if key in self.rows:
            existing = self.rows[key]
            if existing["checkpoint"] != checkpoint or existing["metadata"] != metadata:
                raise ValueError("CHECKPOINT_CONFLICT")
            return
        self.rows[key] = {
            "thread_id": thread_id,
            "namespace": namespace,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "checkpoint": checkpoint,
            "metadata": metadata,
            "codec_version": CODEC_VERSION,
            "fence": fence,
        }

    async def put_writes(self, thread_id, namespace, checkpoint_id, task_id, writes):
        for index, channel, value in writes:
            key = (thread_id, namespace, checkpoint_id, task_id, index)
            row = {"channel": channel, "value": value}
            if key in self.writes and self.writes[key] != row:
                raise ValueError("PENDING_WRITE_CONFLICT")
            self.writes[key] = row


class SqlHttpCheckpointClient(CheckpointClient):
    """Calls C# internal checkpoint endpoints (mTLS in production)."""

    def __init__(self, base_url: str, session) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session

    async def get(self, thread_id, namespace, checkpoint_id=None):
        params = {"threadId": thread_id, "namespace": namespace}
        if checkpoint_id:
            params["checkpointId"] = checkpoint_id
        r = await self.session.get(f"{self.base_url}/internal/v1/checkpoints", params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("item")

    async def list(self, thread_id, namespace, limit=10):
        r = await self.session.get(
            f"{self.base_url}/internal/v1/checkpoints/list",
            params={"threadId": thread_id, "namespace": namespace, "limit": limit},
        )
        r.raise_for_status()
        return r.json().get("items", [])

    async def put(self, thread_id, namespace, checkpoint_id, parent_checkpoint_id, checkpoint, metadata, fence):
        body = {
            "threadId": thread_id,
            "namespace": namespace,
            "checkpointId": checkpoint_id,
            "parentCheckpointId": parent_checkpoint_id,
            "codecVersion": CODEC_VERSION,
            "payloadJson": json.dumps(checkpoint, separators=(",", ":"), ensure_ascii=False),
            "metadataJson": json.dumps(metadata, separators=(",", ":"), ensure_ascii=False),
            "fence": fence,
        }
        r = await self.session.put(f"{self.base_url}/internal/v1/checkpoints", json=body)
        r.raise_for_status()

    async def put_writes(self, thread_id, namespace, checkpoint_id, task_id, writes):
        body = {
            "threadId": thread_id,
            "namespace": namespace,
            "checkpointId": checkpoint_id,
            "graphTaskId": task_id,
            "writes": [
                {"writeIndex": i, "channel": ch, "valueJson": json.dumps(val, separators=(",", ":"), ensure_ascii=False)}
                for i, ch, val in writes
            ],
        }
        r = await self.session.put(f"{self.base_url}/internal/v1/checkpoints/writes", json=body)
        r.raise_for_status()


class KatsCheckpointer:
    """Thin facade matching LangGraph saver operations used by conformance tests."""

    def __init__(self, client: CheckpointClient) -> None:
        self.client = client

    async def aput(self, config: dict, checkpoint: dict, metadata: dict, new_versions: dict | None = None) -> dict:
        thread_id = config["configurable"]["thread_id"]
        namespace = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent = config["configurable"].get("checkpoint_id")
        fence = int(config["configurable"].get("fence", 0))
        await self.client.put(thread_id, namespace, checkpoint_id, parent, checkpoint, metadata, fence)
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aget_tuple(self, config: dict) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        namespace = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")
        row = await self.client.get(thread_id, namespace, checkpoint_id)
        if not row:
            return None
        parent_id = row.get("parent_checkpoint_id")
        parent_config = (
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": namespace, "checkpoint_id": parent_id}}
            if parent_id
            else None
        )
        writes_raw = [
            (k[3], w["channel"], w["value"])
            for k, w in getattr(self.client, "writes", {}).items()
            if k[0] == thread_id and k[1] == namespace and k[2] == row["checkpoint_id"]
        ] if hasattr(self.client, "writes") else []
        return CheckpointTuple(
            config={"configurable": {"thread_id": thread_id, "checkpoint_ns": namespace, "checkpoint_id": row["checkpoint_id"]}},
            checkpoint=row["checkpoint"],
            metadata=row["metadata"],
            parent_config=parent_config,
            pending_writes=writes_raw,
        )

    async def alist(self, config: dict, limit: int = 10) -> list[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        namespace = config["configurable"].get("checkpoint_ns", "")
        rows = await self.client.list(thread_id, namespace, limit)
        out = []
        for row in rows:
            out.append(
                CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": namespace,
                            "checkpoint_id": row["checkpoint_id"],
                        }
                    },
                    checkpoint=row["checkpoint"],
                    metadata=row["metadata"],
                    parent_config=None,
                )
            )
        return out

    async def aput_writes(self, config: dict, writes: Sequence[tuple[str, Any]], task_id: str) -> None:
        thread_id = config["configurable"]["thread_id"]
        namespace = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        indexed = [(i, ch, val) for i, (ch, val) in enumerate(writes)]
        await self.client.put_writes(thread_id, namespace, checkpoint_id, task_id, indexed)


def encode_payload(obj: dict) -> bytes:
    envelope = {"codec": CODEC_VERSION, "body": obj}
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decode_payload(raw: bytes) -> dict:
    envelope = json.loads(raw.decode("utf-8"))
    if envelope.get("codec") != CODEC_VERSION:
        raise ValueError("INCOMPATIBLE_CODEC")
    return envelope["body"]
