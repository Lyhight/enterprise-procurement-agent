from fastapi.testclient import TestClient

from procurement_agent.main import app


def test_operational_endpoints_and_request_context() -> None:
    client = TestClient(app)
    live = client.get("/health/live", headers={"X-Request-ID": "REQ-TEST"})
    ready = client.get("/health/ready")
    snapshot = client.get("/metrics")

    assert live.status_code == 200
    assert live.headers["X-Request-ID"] == "REQ-TEST"
    assert "X-Response-Time-Ms" in live.headers
    assert ready.status_code == 200
    assert snapshot.json()["request_count"] >= 2
    assert {
        "runs_started",
        "runs_completed",
        "runs_failed",
        "runs_cancelled",
        "recoveries_completed",
        "tool_calls",
        "tool_failures",
        "tool_failure_rate",
        "planner_fallback_decisions",
        "average_terminal_duration_ms",
    } <= snapshot.json()["agent"].keys()
