import asyncio
import grpc
from opencode_runner import runner_pb2 as pb,runner_pb2_grpc as rpc


def test_generated_duplex_binding():
    class Echo(rpc.RunnerGatewayServicer):
        async def WorkChannel(self, request_iterator, context):
            async for f in request_iterator:
                yield pb.GatewayFrame(correlation_message_id=f.message_id,hello=pb.HelloAccepted(heartbeat_seconds=5,lease_seconds=45))
    async def check():
        server=grpc.aio.server();rpc.add_RunnerGatewayServicer_to_server(Echo(),server)
        port=server.add_insecure_port("127.0.0.1:0");await server.start()
        try:
            async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
                call=rpc.RunnerGatewayStub(channel).WorkChannel()
                await call.write(pb.RunnerFrame(message_id="first",hello=pb.Hello(protocol_version=1)))
                assert (await call.read()).correlation_message_id=="first"
                await call.write(pb.RunnerFrame(message_id="second",claim=pb.Claim()))
                assert (await call.read()).correlation_message_id=="second"
                await call.done_writing()
        finally:await server.stop(0)
    asyncio.run(check())
