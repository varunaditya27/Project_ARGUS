"""Settings validation: a half-configured dependency must fail at startup."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_comma_separated_values_become_lists() -> None:
    settings = make_settings(cors_origins="http://a.test, http://b.test ,")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_a_log_level_is_accepted_in_any_case() -> None:
    assert make_settings(log_level="debug").log_level == "DEBUG"


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_threshold_means_uncalibrated_not_zero(blank: str) -> None:
    # .env.example ships these keys empty; zero would silently match everything.
    settings = make_settings(match_threshold=blank, review_threshold=blank, minimum_margin=blank)
    assert settings.match_threshold is None
    assert settings.review_threshold is None
    assert settings.minimum_margin is None


def test_a_review_threshold_above_the_match_threshold_is_refused() -> None:
    with pytest.raises(ValidationError, match="REVIEW_THRESHOLD"):
        make_settings(match_threshold=0.4, review_threshold=0.6)


def test_equal_thresholds_are_allowed() -> None:
    # Edge of the same rule: review <= match, so equality passes.
    settings = make_settings(match_threshold=0.4, review_threshold=0.4)
    assert settings.review_threshold == settings.match_threshold


@pytest.mark.parametrize("similarity", [-1.5, 1.5])
def test_a_similarity_outside_the_cosine_range_is_refused(similarity: float) -> None:
    with pytest.raises(ValidationError):
        make_settings(match_threshold=similarity)


def test_persistent_chroma_needs_a_path() -> None:
    with pytest.raises(ValidationError, match="ARGUS_CHROMA_PATH"):
        make_settings(chroma_mode="persistent")


@pytest.mark.parametrize("overrides", [{"chroma_host": "localhost"}, {"chroma_port": 8000}])
def test_http_chroma_needs_both_host_and_port(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="ARGUS_CHROMA_HOST"):
        make_settings(chroma_mode="http", **overrides)


def test_r2_names_every_setting_it_is_missing() -> None:
    with pytest.raises(ValidationError) as excinfo:
        make_settings(object_storage_mode="r2", r2_bucket="faces")
    message = str(excinfo.value)
    assert "ARGUS_R2_ENDPOINT_URL" in message
    assert "ARGUS_R2_BUCKET" not in message


def test_local_storage_needs_nothing_extra() -> None:
    # The defaults are usable, which is what makes it the offline demo mode.
    settings = make_settings(object_storage_mode="local")
    assert settings.local_storage_path is not None
    assert settings.media_url_path.startswith("/")


def test_an_explicit_model_path_wins_over_the_pack_root() -> None:
    settings = make_settings(
        model_root=Path("/packs/buffalo_l"), detector_model_path=Path("/custom/det.onnx")
    )
    assert settings.model_file(settings.detector_model_path, "det_10g.onnx") == Path(
        "/custom/det.onnx"
    )
    assert settings.model_file(None, "det_10g.onnx") == Path("/packs/buffalo_l/det_10g.onnx")


def test_without_a_pack_root_a_model_is_simply_unset() -> None:
    # Edge: nothing configured, so the component reports itself missing rather
    # than pointing at a path that does not exist.
    assert make_settings().model_file(None, "det_10g.onnx") is None


@pytest.mark.parametrize("semester_free_field", ["capture_interval_seconds", "db_pool_size"])
def test_positive_only_settings_reject_zero(semester_free_field: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{semester_free_field: 0})
