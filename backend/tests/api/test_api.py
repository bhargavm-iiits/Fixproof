from __future__ import annotations

import json

import pytest

from backend.tests.api.conftest import drain_events, seed_run

pytestmark = pytest.mark.anyio


class TestHealth:
    async def test_healthz_reports_the_modes(self, client) -> None:
        payload = (await client.get("/healthz")).json()
        assert payload["status"] == "ok"
        assert payload["app_mode"] == "local"
        assert payload["model_mode"] == "fake"
        assert payload["mutations_enabled"] is True

    async def test_healthz_reports_the_schema_version(self, client) -> None:
        assert (await client.get("/healthz")).json()["schema_version"] == 1

    async def test_healthz_reports_docker_and_the_image(self, client) -> None:
        payload = (await client.get("/healthz")).json()
        assert isinstance(payload["docker_reachable"], bool)
        assert payload["image"] == "fixproof-verifier:1"

    async def test_healthz_reports_the_config_hash(self, client) -> None:
        assert len((await client.get("/healthz")).json()["config_hash"]) == 16

    async def test_healthz_is_reachable_in_demo_mode(self, demo_client) -> None:
        payload = (await demo_client.get("/healthz")).json()
        assert payload["mutations_enabled"] is False


class TestDefects:
    async def test_listing_returns_both_sets(self, client) -> None:
        payload = (await client.get("/defects")).json()
        assert len(payload) == 24
        assert {entry["fixture_set"] for entry in payload} == {"dev", "holdout"}

    async def test_filtering_by_set(self, client) -> None:
        payload = (await client.get("/defects", params={"set": "dev"})).json()
        assert len(payload) == 12
        assert all(entry["fixture_set"] == "dev" for entry in payload)

    async def test_holdout_listing_is_allowed(self, client) -> None:
        assert len((await client.get("/defects", params={"set": "holdout"})).json()) == 12

    async def test_an_unknown_set_is_rejected(self, client) -> None:
        assert (await client.get("/defects", params={"set": "banana"})).status_code == 422

    async def test_a_single_defect(self, client) -> None:
        payload = (await client.get("/defects/dev-off_by_one-001")).json()
        assert payload["category"] == "off_by_one"
        assert payload["allowed_paths"] == ["paging.py"]

    async def test_the_reference_patch_is_never_served(self, client) -> None:
        body = (await client.get("/defects/dev-off_by_one-001")).text
        assert "total + limit - 1" not in body

    async def test_an_unknown_defect_is_404(self, client) -> None:
        assert (await client.get("/defects/nope")).status_code == 404


class TestCreateRun:
    async def test_a_run_is_accepted_with_202(self, client) -> None:
        response = await client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        assert response.status_code == 202
        assert response.json()["run_id"].startswith("run-")

    async def test_an_unknown_defect_is_404(self, client) -> None:
        assert (await client.post("/runs", json={"defect_id": "nope"})).status_code == 404

    async def test_a_missing_body_is_422(self, client) -> None:
        assert (await client.post("/runs", json={})).status_code == 422

    async def test_a_run_reaches_a_terminal_status(self, client) -> None:
        created = await client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        run_id = created.json()["run_id"]
        await drain_events(client, run_id)
        payload = (await client.get(f"/runs/{run_id}")).json()
        assert payload["status"] in {"succeeded", "failed", "cancelled"}
        assert payload["decision"] is not None

    async def test_a_fake_mode_run_reports_its_gate_rejections(self, client) -> None:
        created = await client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        run_id = created.json()["run_id"]
        await drain_events(client, run_id)
        payload = (await client.get(f"/runs/{run_id}")).json()
        rejections = {c["candidate_id"]: c["rejected_by"] for c in payload["candidates"]}
        assert rejections["r1-scope"] == "scope"
        assert rejections["r1-testedit"] == "no_test_edits"


class TestDemoMode:
    async def test_creating_a_run_is_403_not_404(self, demo_client) -> None:
        response = await demo_client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        assert response.status_code == 403
        assert "read-only" in response.json()["detail"]

    async def test_cancelling_is_403(self, demo_client) -> None:
        assert (await demo_client.post("/runs/anything/cancel")).status_code == 403

    async def test_reading_is_still_allowed(self, demo_client) -> None:
        assert (await demo_client.get("/defects")).status_code == 200
        assert (await demo_client.get("/runs")).status_code == 200

    async def test_the_403_explains_rather_than_hides(self, demo_client) -> None:
        response = await demo_client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        assert "APP_MODE=demo" in response.json()["detail"]


class TestRunViews:
    async def test_listing_is_paged(self, client) -> None:
        seed_run(client, "run-a")
        seed_run(client, "run-b")
        payload = (await client.get("/runs", params={"limit": 1})).json()
        assert payload["total"] == 2
        assert len(payload["runs"]) == 1

    async def test_an_empty_listing(self, client) -> None:
        payload = (await client.get("/runs")).json()
        assert payload["total"] == 0
        assert payload["runs"] == []

    async def test_a_stored_run_is_served_after_the_process_forgot_it(self, client) -> None:
        seed_run(client, "run-stored")
        payload = (await client.get("/runs/run-stored")).json()
        assert payload["decision"] == "NO_VERIFIED_FIX"
        assert payload["candidates"][0]["candidate_id"] == "r1-noop"

    async def test_the_decision_is_explained(self, client) -> None:
        seed_run(client, "run-explained")
        payload = (await client.get("/runs/run-explained")).json()
        assert "none was eligible" in payload["decision_explanation"]

    async def test_an_unknown_run_is_404(self, client) -> None:
        assert (await client.get("/runs/nope")).status_code == 404

    async def test_a_candidate_carries_its_diff_and_gates(self, client) -> None:
        seed_run(client, "run-diff")
        candidate = (await client.get("/runs/run-diff")).json()["candidates"][0]
        assert candidate["unified_diff"].startswith("--- a/paging.py")
        assert candidate["gates"][0]["gate"] == "diff_parses"


class TestArtifacts:
    async def test_an_allow_listed_artifact_is_served(self, client) -> None:
        seed_run(client, "run-art")
        response = await client.get("/runs/run-art/artifacts/report.md")
        assert response.status_code == 200
        assert "seeded" in response.text

    async def test_json_artifacts_are_served_as_json(self, client) -> None:
        seed_run(client, "run-art")
        response = await client.get("/runs/run-art/artifacts/report.json")
        assert response.headers["content-type"].startswith("application/json")

    @pytest.mark.parametrize(
        "name",
        [
            "../../../etc/passwd",
            "..%2F..%2Fsecret",
            "run.json/../../../secret",
            "C:/Windows/system32/config",
            "notes.md",
            "reference.patch",
        ],
    )
    async def test_anything_outside_the_allow_list_is_refused(self, client, name: str) -> None:
        seed_run(client, "run-art")
        response = await client.get(f"/runs/run-art/artifacts/{name}")
        assert response.status_code == 404
        assert "passwd" not in response.text.replace("etc/passwd", "")

    async def test_an_allow_listed_but_absent_artifact_is_404(self, client) -> None:
        seed_run(client, "run-art")
        assert (await client.get("/runs/run-art/artifacts/baseline.json")).status_code == 404

    async def test_the_run_view_lists_only_artifacts_that_exist(self, client) -> None:
        seed_run(client, "run-art")
        payload = (await client.get("/runs/run-art")).json()
        assert set(payload["artifacts"]) == {"report.md", "report.json"}


class TestEvents:
    async def test_the_stage_sequence_arrives_in_order(self, client) -> None:
        created = await client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        events = await drain_events(client, created.json()["run_id"])
        stages = [
            event["stage"]
            for event in events
            if event.get("type") == "stage" and event.get("state") == "started"
        ]
        assert stages[:4] == ["prepare", "baseline", "retrieve", "propose"]
        assert "gate" in stages
        assert stages[-1] == "select"

    async def test_candidate_events_are_emitted(self, client) -> None:
        created = await client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        events = await drain_events(client, created.json()["run_id"])
        candidate_events = [event for event in events if event.get("type") == "candidate"]
        assert len(candidate_events) == 3
        assert {event["candidate_id"] for event in candidate_events} == {
            "r1-noop", "r1-scope", "r1-testedit"
        }

    async def test_the_stream_ends_with_a_terminal_status(self, client) -> None:
        created = await client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        events = await drain_events(client, created.json()["run_id"])
        assert events[-1]["type"] == "status"
        assert events[-1]["terminal"] is True

    async def test_events_for_an_unknown_run_are_404(self, client) -> None:
        assert (await client.get("/runs/nope/events")).status_code == 404

    async def test_events_for_a_run_from_an_earlier_process_are_409(self, client) -> None:
        seed_run(client, "run-old")
        assert (await client.get("/runs/run-old/events")).status_code == 409


class TestCancel:
    async def test_cancelling_an_unknown_run_is_404(self, client) -> None:
        assert (await client.post("/runs/nope/cancel")).status_code == 404

    async def test_cancelling_a_live_run_is_accepted(self, client) -> None:
        created = await client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        run_id = created.json()["run_id"]
        response = await client.post(f"/runs/{run_id}/cancel")
        assert response.status_code == 200
        assert response.json()["run_id"] == run_id
        await drain_events(client, run_id)


class TestQueueing:
    async def test_a_second_run_reports_its_queue_position(self, client) -> None:
        """Docker is a shared resource, so runs queue rather than contend."""
        first = await client.post("/runs", json={"defect_id": "dev-off_by_one-001"})
        second = await client.post("/runs", json={"defect_id": "dev-wrong_operator-001"})
        assert second.json()["queue_position"] >= 0
        await drain_events(client, first.json()["run_id"])
        await drain_events(client, second.json()["run_id"])
        assert (await client.get("/runs")).json()["total"] == 2


class TestReports:
    async def test_latest_report_is_404_when_none_are_committed(self, client, monkeypatch,
                                                                tmp_path) -> None:
        from backend.app.api import routes

        monkeypatch.setattr(routes, "REPORTS_DIR", tmp_path / "empty")
        assert (await client.get("/reports/latest")).status_code == 404

    async def test_reports_listing_is_empty_when_none_are_committed(self, client, monkeypatch,
                                                                    tmp_path) -> None:
        from backend.app.api import routes

        monkeypatch.setattr(routes, "REPORTS_DIR", tmp_path / "empty")
        assert (await client.get("/reports")).json() == []

    async def test_a_committed_report_is_parsed(self, client, monkeypatch, tmp_path) -> None:
        from backend.app.api import routes

        reports = tmp_path / "reports"
        reports.mkdir()
        (reports / "eval-dev-abc-20260921.json").write_text(
            json.dumps({"metrics": {"verified_fix_rate": 0.0}}), encoding="utf-8"
        )
        monkeypatch.setattr(routes, "REPORTS_DIR", reports)
        payload = (await client.get("/reports/latest")).json()
        assert payload["metrics"]["verified_fix_rate"] == 0.0
        assert payload["report_file"].startswith("eval-dev-")


class TestSystemRoutes:
    async def test_the_graph_describes_every_stage(self, client) -> None:
        payload = (await client.get("/graph")).json()
        assert payload["stages"] == [
            "prepare", "baseline", "retrieve", "propose", "gate", "verify", "select"
        ]
        assert len(payload["nodes"]) == 7
        assert all(node["description"] for node in payload["nodes"])

    async def test_the_graph_has_a_retry_edge(self, client) -> None:
        edges = (await client.get("/graph")).json()["edges"]
        assert any(edge["source"] == "verify" and edge["target"] == "propose" for edge in edges)

    async def test_decisions_are_documented(self, client) -> None:
        payload = (await client.get("/decisions")).json()
        assert {entry["decision"] for entry in payload} == {
            "FIX_VERIFIED", "NO_VERIFIED_FIX", "ALL_GATED", "TIMEOUT", "ERROR"
        }

    async def test_openapi_is_served(self, client) -> None:
        payload = (await client.get("/openapi.json")).json()
        assert payload["info"]["title"] == "fixproof"
        assert "/runs" in payload["paths"]

    async def test_swagger_ui_is_served(self, client) -> None:
        assert (await client.get("/docs")).status_code == 200
