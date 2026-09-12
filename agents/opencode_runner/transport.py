import asyncio
import uuid
from pathlib import Path
import grpc
from . import runner_pb2 as pb
from . import runner_pb2_grpc as rpc
from .core import RunnerError


class Transport:
    def __init__(self, target, ca, cert, key, boot, version):
        self.target, self.boot, self.version = target, boot, version
        self.credentials = grpc.ssl_channel_credentials(Path(ca).read_bytes(), Path(key).read_bytes(), Path(cert).read_bytes())
        self.connected = asyncio.Event()
        self.abort = asyncio.Event()
        self.pending = {}
        self.write_lock = asyncio.Lock()
        self.call = None
        self.closing = False

    async def run(self):
        while not self.closing:
            try:
                async with grpc.aio.secure_channel(self.target, self.credentials, options=[("grpc.max_receive_message_length", 6*1024*1024), ("grpc.max_send_message_length", 6*1024*1024)]) as channel:
                    self.call = rpc.RunnerGatewayStub(channel).WorkChannel()
                    hello = pb.RunnerFrame(message_id=str(uuid.uuid4()), hello=pb.Hello(protocol_version=1, boot_id=self.boot, runner_version="0.1.0", opencode_version=self.version))
                    await self.call.write(hello)
                    response = await asyncio.wait_for(self.call.read(), 10)
                    if not response.HasField("hello"):
                        raise RunnerError("HELLO_REJECTED")
                    self.connected.set()
                    while not self.closing:
                        frame = await self.call.read()
                        if frame is grpc.aio.EOF:
                            raise ConnectionError()
                        if frame.HasField("abort"):
                            self.abort.set()
                        future = self.pending.get(frame.correlation_message_id)
                        if future is not None and not future.done():
                            future.set_result(frame)
            except (grpc.RpcError, ConnectionError, TimeoutError, RunnerError):
                pass
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

    async def close(self):
        self.closing = True
        if self.call is not None:
            self.call.cancel()
