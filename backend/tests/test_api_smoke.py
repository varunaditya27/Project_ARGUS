"""API behaviour with nothing provisioned: every failure must be explicit."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_health_reports_degraded_without_dependencies(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert {check["name"] for check in body["checks"]} == {"postgresql", "chromadb"}
    assert all(check["code"] == "dependency_not_configured" for check in body["checks"])


async def test_runtime_exposes_capture_configuration(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/runtime")).json()
    assert body["database_configured"] is False
    assert body["recognition_ready"] is False
    assert body["capture"]["pending_observations"] == 0


async def test_models_lists_placeholders_and_uncalibrated_thresholds(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/models")).json()
    assert {component["name"] for component in body["components"]} == {
        "face_detector",
        "face_embedder",
        "mask_synthesizer",
        "template_index",
    }
    assert all(component["configured"] is False for component in body["components"])
    assert body["thresholds"] == {
        "match_threshold": None,
        "review_threshold": None,
        "minimum_margin": None,
        "calibrated": False,
    }
    assert body["recognition_ready"] is False
    assert body["embedding_dim"] == 512


async def test_database_endpoints_fail_with_a_configuration_hint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/classrooms")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "dependency_not_configured"
    assert "ARGUS_DATABASE_URL" in error["message"]


async def test_recognize_never_invents_a_result(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/recognize",
        files={"frame": ("frame.jpg", b"not-a-real-frame", "image/jpeg")},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_not_configured"


async def test_validation_errors_use_the_shared_envelope(
    client_unreachable_db: AsyncClient,
) -> None:
    response = await client_unreachable_db.post(
        "/api/v1/classrooms",
        json={"class_name": "", "department": "CSE", "semester": 0, "strength": -1},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


async def test_unreachable_database_is_reported_not_crashed(
    client_unreachable_db: AsyncClient,
) -> None:
    response = await client_unreachable_db.get("/api/v1/classrooms")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"


async def test_unknown_route_uses_the_shared_envelope(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/sessions/{uuid.uuid4()}/does-not-exist")
    assert response.status_code == 404
    assert "error" in response.json()
