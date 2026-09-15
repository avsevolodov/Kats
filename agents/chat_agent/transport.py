"""gRPC agent.v1 transport for Chat Agent."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import grpc

from chat_agent import agent_pb2 as pb
from chat_agent import agent_pb2_grpc as rpc


class AgentTransport:
    def __init__(self, target: str, ca: str, cert: str, key: str, boot: str):
        self.target = target
        self.boot = boot
        self.credentials = grpc.ssl_channel_credentials(
            Path(ca).read_bytes(), Path(key).read_bytes(), Path(cert).read_bytes()
        )
        self.call = None
        self.pending: dict[str, asyncio.Future] = {}
        self.closing = False
        self.write_lock = asyncio.Lock()
        self.ready = asyncio.Event()

    def _options(self):
        options = [
            ("grpc.max_receive_message_length", 6 * 1024 * 1024),
            ("grpc.max_send_message_length", 6 * 1024 * 1024),
            # Never tunnel local API gRPC through corporate HTTP_PROXY (502 on :3128).
            ("grpc.enable_http_proxy", 0),
        ]
        ssl_name = os.environ.get("PLATFORM_GRPC_SSL_NAME")
        if ssl_name:
            options.append(("grpc.ssl_target_name_override", ssl_name))
            options.append(("grpc.default_authority", ssl_name))
        return options

    async def run_reader(self):
        while not self.closing:
            self.ready.clear()
            try:
                async with grpc.aio.secure_channel(self.target, self.credentials, options=self._options()) as channel:
                    self.call = rpc.AgentChannelStub(channel).Connect()
                    await self._write(pb.AgentFrame(
                        protocol_version=1,
                        message_id=str(uuid.uuid4()),
                        hello=pb.Hello(boot_id=self.boot, version="0.1.0", supported_definitions=["chat-v1"]),
                    ))
                    hello = await asyncio.wait_for(self.call.read(), 10)
                    if hello.HasField("error"):
                        raise RuntimeError(hello.error.code)
                    self.ready.set()
                    while not self.closing:
                        frame = await self.call.read()
                        if frame is grpc.aio.EOF:
                            raise ConnectionError("EOF")
                        fut = self.pending.pop(frame.correlation_id, None)
                        if fut and not fut.done():
                            fut.set_result(frame)
            except Exception as e:
                self.ready.clear()
                if self.closing:
                    return
                print(f"chat-agent transport reconnect: {type(e).__name__}", file=__import__("sys").stderr, flush=True)
                await asyncio.sleep(1)

    async def wait_ready(self, timeout: float = 30) -> None:
        await asyncio.wait_for(self.ready.wait(), timeout)

    async def _write(self, frame: pb.AgentFrame):
        async with self.write_lock:
            await self.call.write(frame)

    async def request(self, **payload) -> pb.GatewayAgentFrame:
        message_id = str(uuid.uuid4())
        frame = pb.AgentFrame(protocol_version=1, message_id=message_id, **payload)
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self.pending[message_id] = fut
        await self._write(frame)
        return await asyncio.wait_for(fut, 30)

    async def claim(self):
        return await self.request(claim=pb.Claim(boot_id=self.boot))

    async def heartbeat(self, invocation_id: str, fence: int):
        return await self.request(heartbeat=pb.Heartbeat(boot_id=self.boot, invocation_id=invocation_id, fence=fence))

    async def complete(
        self,
        invocation_id: str,
        status: str,
        result: dict,
        *,
        error_code: str = "",
        safe_message: str = "",
    ):
        return await self.request(
            complete=pb.Complete(
                invocation_id=invocation_id,
                status=status,
                result_json=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                error_code=error_code or "",
                safe_message=safe_message or "",
            )
        )

    async def suspend(self, invocation_id: str, checkpoint_id: str, dependency_ids: list[str] | None = None):
        return await self.request(
            suspend=pb.Suspend(
                invocation_id=invocation_id,
                checkpoint_id=checkpoint_id or "",
                dependency_ids=list(dependency_ids or []),
            )
        )

    async def get_invocation(self, invocation_id: str):
        return await self.request(get_invocation=pb.GetInvocation(invocation_id=invocation_id))

    async def ensure_invocation(self, task_id, checkpoint_id, path, tool_call_id, capability, version, input_obj):
        return await self.request(
            ensure_invocation=pb.EnsureInvocation(
                task_id=task_id,
                checkpoint_id=checkpoint_id,
                graph_task_path=path,
                tool_call_id=tool_call_id,
                capability=capability,
                version=version,
                input_json=json.dumps(input_obj, ensure_ascii=False, separators=(",", ":")),
            )
        )
