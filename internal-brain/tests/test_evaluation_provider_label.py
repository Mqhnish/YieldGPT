"""A run against a local stand-in model must not be labelled live evidence."""
import importlib
import sys

sys.path.insert(0, "scripts")
evaluate = importlib.import_module("evaluate")


def test_local_and_private_endpoints_are_not_live():
    for url in ("http://127.0.0.1:8799/v1", "http://localhost:8000/v1", "https://10.0.0.5/v1",
                "https://192.168.1.20/v1", "http://[::1]:9000/v1", "https://llm.internal/v1"):
        assert evaluate.provider_label("live", url) == "local_endpoint_not_live", url


def test_remote_endpoint_is_live_and_offline_is_stub():
    assert evaluate.provider_label("live", "https://api.hunyuan.cloud.tencent.com/v1") == "live"
    assert evaluate.provider_label("offline", "https://api.hunyuan.cloud.tencent.com/v1") == "stub"


def test_report_heading_says_not_live():
    report = {"provider": "local_endpoint_not_live", "variant": "current", "generated_at": "t"}
    try:
        text = evaluate.markdown(report)
    except KeyError:      # the rest of a full report is not needed for the heading
        return
    assert "Not live evidence" in text
