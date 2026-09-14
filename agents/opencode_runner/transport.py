import asyncio
import os
import time
import uuid
from pathlib import Path
import grpc
from . import runner_pb2 as pb
from . import runner_pb2_grpc as rpc
from .core import RunnerError
from .logutil import LOG


def _reconnect_hint(exc: BaseException) -> str:
    """One-line ops hint without certs, paths, or connection strings."""
    if isinstance(exc, grpc.RpcError):
        code = exc.code().name if exc.code() else "UNKNOWN"
        return f"RpcError/{code}"
    if isinstance(exc, RunnerError):
        return str(exc) or type(exc).__name__
    if isinstance(exc, TimeoutError):
        return "HELLO_TIMEOUT"
    if isinstance(exc, ConnectionError):
        return "CONNECTION_DROPPED"
    return type(exc).__name__


class Transport:
    def __init__(self, target, ca, cert, key, boot, version):
        self.target, self.boot, self.version = target, boot, version
        self.credentials = grpc.ssl_channel_credentials(Path(ca).read_bytes(), Path(key).read_bytes(), Path(cert).read_bytes())
        self.connected = asyncio.Event()
        self.abort = asyncio.Event()
        self.pending = {}
        self.confirmation_replies = {}
        self.confirmation_waiters = {}
        self.write_lock = asyncio.Lock()
        self.call = None
        self.closing = False

    def channel_options(self):
        options = [
            ("grpc.max_receive_message_length", 6 * 1024 * 1024),
            ("grpc.max_send_message_length", 6 * 1024 * 1024),
        ]
        # WSL→Windows uses a 172.x host IP; cert SAN is localhost — override verification name.
        ssl_name = os.environ.get("PLATFORM_GRPC_SSL_NAME")
        if ssl_name:
            options.append(("grpc.ssl_target_name_override", ssl_name))
            options.append(("grpc.default_authority", ssl_name))
        return options

    async def run(self):
        while not self.closing:
            ssl_name = os.environ.get("PLATFORM_GRPC_SSL_NAME") or "-"
            LOG.info("gateway dial target=%s ssl_name=%s", self.target, ssl_name)
            try:
                async with grpc.aio.secure_channel(self.target, self.credentials, options=self.channel_options()) as channel:
                    self.call = rpc.RunnerGatewayStub(channel).WorkChannel()
                    hello = pb.RunnerFrame(message_id=str(uuid.uuid4()), hello=pb.Hello(protocol_version=1, boot_id=self.boot, runner_version="0.1.0", opencode_version=self.version))
                    await self.call.write(hello)
                    response = await asyncio.wait_for(self.call.read(), 10)
                    if not response.HasField("hello"):
                        code = response.error.code if response.HasField("error") else "HELLO_REJECTED"
                        raise RunnerError(code)
                    self.connected.set()
                    LOG.info("gateway hello ok")
                    while not self.closing:
                        frame = await self.call.read()
                        if frame is grpc.aio.EOF:
                            raise ConnectionError()
                        if frame.HasField("abort"):
                            self.abort.set()
                            for waiter in list(self.confirmation_waiters.values()):
                                if not waiter.done():
                                    waiter.set_result(None)
                        if frame.HasField("confirmation_reply"):
                            reply = frame.confirmation_reply
                            payload = {
                                "request_id": reply.request_id,
                                "decision": reply.decision,
                                "answers_json": reply.answers_json or "",
                            }
                            self.confirmation_replies[reply.request_id] = payload
                            waiter = self.confirmation_waiters.get(reply.request_id)
                            if waiter is not None and not waiter.done():
                                waiter.set_result(payload)
                        future = self.pending.get(frame.correlation_message_id)
                        if future is not None and not future.done():
                            future.set_result(frame)
            except (grpc.RpcError, ConnectionError, TimeoutError, RunnerError, OSError) as exc:
                if not self.closing:
                    LOG.warning("gateway reconnect: %s", _reconnect_hint(exc))
            finally:
                self.connected.clear()
                for f in list(self.pending.values()):
                    if not f.done():
                        f.set_exception(ConnectionError())
                if self.call is not None:
                    self.call.cancel()
            if not self.closing:
                await asyncio.sleep(1)

    async def request(self, field: str, payload, *, frame=None, timeout=30):
        frame = frame or pb.RunnerFrame(message_id=str(uuid.uuid4()), **{field: payload})
        async with asyncio.timeout(timeout):
            while True:
                await self.connected.wait()
                future = asyncio.get_running_loop().create_future()
                self.pending[frame.message_id] = future
                try:
                    async with self.write_lock:
                        await self.call.write(frame)
                    response = await asyncio.wait_for(future, 10)
                    if response.HasField("error"):
                        if response.error.retryable:
                            await asyncio.sleep(1)
                            continue
                        raise RunnerError(response.error.code)
                    return response
                except (grpc.RpcError, ConnectionError, TimeoutError):
                    await asyncio.sleep(.2)
                finally:
                    self.pending.pop(frame.message_id, None)

    async def wait_confirmation(self, request_id: str, abort_requested: asyncio.Event, timeout: float):
        if request_id in self.confirmation_replies:
            return self.confirmation_replies[request_id]
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.confirmation_waiters[request_id] = future
        try:
            deadline = time.monotonic() + timeout
            while True:
                if abort_requested.is_set():
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"request_id": request_id, "decision": "reject", "answers_json": ""}
                try:
                    return await asyncio.wait_for(asyncio.shield(future), min(remaining, 1.0))
                except TimeoutError:
                    if request_id in self.confirmation_replies:
                        return self.confirmation_replies[request_id]
                    continue
        finally:
            self.confirmation_waiters.pop(request_id, None)

    async def close(self):
        self.closing = True
        if self.call is not None:
            self.call.cancel()
