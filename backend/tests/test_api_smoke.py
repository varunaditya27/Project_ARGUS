"""API behaviour with nothing provisioned: every failure must be explicit."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.helpers import CLASS_ID, PNG, build_zip, roster_csv


async def test_health_reports_degraded_without_dependencies(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert {check["name"] for check in body["checks"]} == {"postgresql", "chromadb"}
    assert not any(check["healthy"] for check in body["checks"])


async def test_models_reports_missing_components_and_uncalibrated_thresholds(
    client: AsyncClient,
) -> None:
    body = (await client.get("/api/v1/models")).json()
    components = {component["name"]: component for component in body["components"]}
    assert components.keys() == {
        "face_detector",
        "face_embedder",
        "mask_synthesizer",
        "template_index",
    }
    # Mask synthesis is pure geometry, so it is always available; the three
    # components that need a model file or a server are not.
    assert components["mask_synthesizer"]["configured"] is True
    assert not any(
        components[name]["configured"]
        for name in ("face_detector", "face_embedder", "template_index")
    )
    assert body["thresholds"] == {
        "match_threshold": None,
        "review_threshold": None,
        "minimum_margin": None,
    }
    assert body["recognition_ready"] is False


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


async def test_import_returns_503_when_object_storage_is_disabled(
    client_unreachable_db: AsyncClient,
) -> None:
    response = await client_unreachable_db.post(
        "/api/v1/students/import",
        files={
            "csv_file": ("roster.csv", roster_csv("Ada,1,ada.png"), "text/csv"),
            "images": ("images.zip", build_zip({"ada.png": PNG}).getvalue(), "application/zip"),
        },
        data={"class_id": str(CLASS_ID)},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_not_configured"


async def test_import_reports_a_missing_header_with_the_shared_envelope(
    client_unreachable_db: AsyncClient,
) -> None:
    response = await client_unreachable_db.post(
        "/api/v1/students/import",
        files={"csv_file": ("roster.csv", roster_csv("Ada,1,ada.png"), "text/csv")},
        data={"dry_run": "true"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"]["missing"] == ["class_id"]
