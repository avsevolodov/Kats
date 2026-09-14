from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dev


def test_windows_host_ip_from_resolv(tmp_path):
    resolv = tmp_path / "resolv.conf"
    route = tmp_path / "route"
    resolv.write_text("# generated\nnameserver 172.29.160.1\nnameserver 1.1.1.1\n")
    assert dev.windows_host_ip(resolv, route) == "172.29.160.1"


def test_windows_host_ip_ignores_loopback_mirrored(tmp_path):
    resolv = tmp_path / "resolv.conf"
    route = tmp_path / "route"
    resolv.write_text("nameserver 127.0.0.1\n")
    assert dev.windows_host_ip(resolv, route) is None


def test_windows_host_ip_dns_stub_uses_default_gateway(tmp_path):
    resolv = tmp_path / "resolv.conf"
    route = tmp_path / "route"
    resolv.write_text("nameserver 10.255.255.254\n")
    # /proc/net/route Gateway is little-endian hex of 172.29.160.1 → 01A01DAC
    route.write_text(
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
        "eth0\t00000000\t01A01DAC\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
    )
    assert dev.default_gateway_ipv4(route) == "172.29.160.1"
    assert dev.windows_host_ip(resolv, route) == "172.29.160.1"


def test_default_gateway_ipv4_skips_zero(tmp_path):
    route = tmp_path / "route"
    route.write_text(
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
        "lo\t00000000\t00000000\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
    )
    assert dev.default_gateway_ipv4(route) is None


def test_platform_grpc_prefers_settings_override(monkeypatch):
    monkeypatch.setattr(dev, "is_wsl", lambda: True)
    monkeypatch.setattr(dev, "windows_host_ip", lambda: "172.1.2.3")
    target, ssl = dev.platform_grpc_endpoint({"local": {"platformGrpc": "10.0.0.5:8081"}}, docker=False)
    assert target == "10.0.0.5:8081"
    assert ssl == "localhost"


def test_platform_grpc_wsl_uses_gateway(monkeypatch):
    monkeypatch.setattr(dev, "is_wsl", lambda: True)
    monkeypatch.setattr(dev, "windows_host_ip", lambda: "172.29.160.1")
    target, ssl = dev.platform_grpc_endpoint({"local": {}}, docker=False)
    assert target == "172.29.160.1:8081"
    assert ssl == "localhost"


def test_platform_grpc_compose_and_localhost(monkeypatch):
    monkeypatch.setattr(dev, "is_wsl", lambda: False)
    assert dev.platform_grpc_endpoint({}, docker=True) == ("api:8081", None)
    assert dev.platform_grpc_endpoint({"local": {}}, docker=False) == ("localhost:8081", None)


def test_scrub_proxy_for_local_grpc():
    env = {
        "PLATFORM_GRPC": "172.29.160.1:8081",
        "HTTP_PROXY": "http://127.0.0.1:3128",
        "https_proxy": "http://127.0.0.1:3128",
        "NO_PROXY": "example.com",
    }
    dev.scrub_proxy_for_local_grpc(env)
    assert "HTTP_PROXY" not in env and "https_proxy" not in env
    assert "172.29.160.1" in env["NO_PROXY"]
    assert "localhost" in env["no_proxy"]
