"""测试沙盒通信协议."""
from __future__ import annotations

import json

from sandbox.proto import SandboxRequest, SandboxResponse


class TestSandboxRequest:
    def test_to_json(self):
        req = SandboxRequest(id="r1", method="execute_sql", params={"sql": "SELECT 1"})
        data = json.loads(req.to_json())
        assert data["id"] == "r1"
        assert data["method"] == "execute_sql"
        assert data["params"]["sql"] == "SELECT 1"

    def test_from_json(self):
        line = json.dumps({"id": "r2", "method": "ping", "params": {}})
        req = SandboxRequest.from_json(line)
        assert req.id == "r2"
        assert req.method == "ping"
        assert req.params == {}

    def test_default_params(self):
        req = SandboxRequest(id="r3", method="ping")
        assert req.params == {}


class TestSandboxResponse:
    def test_success_response(self):
        resp = SandboxResponse(id="r1", success=True, result={"rows": [[1, 2]]})
        data = json.loads(resp.to_json())
        assert data["id"] == "r1"
        assert data["success"] is True
        assert data["result"]["rows"] == [[1, 2]]
        assert data["error"] is None

    def test_error_response(self):
        resp = SandboxResponse(id="r2", success=False, error="something went wrong")
        data = json.loads(resp.to_json())
        assert data["id"] == "r2"
        assert data["success"] is False
        assert data["error"] == "something went wrong"
        assert data["result"] is None

    def test_from_json(self):
        line = json.dumps({"id": "r3", "success": True, "result": {"pong": True}, "error": None})
        resp = SandboxResponse.from_json(line)
        assert resp.id == "r3"
        assert resp.success is True
        assert resp.result == {"pong": True}
