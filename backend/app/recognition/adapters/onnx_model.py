"""Shared onnxruntime plumbing for the vision adapters.

Both models in the InsightFace ``buffalo_l`` pack (SCRFD detection, ArcFace
recognition) are plain ONNX graphs, so serving needs onnxruntime only - no
PyTorch and no insightface package at runtime.

Sessions load lazily and exactly once. ``InferenceSession.run`` is thread-safe,
which matters because the service layer pushes inference onto worker threads to
keep the event loop free.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.core.errors import DependencyNotConfiguredError, DependencyUnavailableError
from app.core.logging import get_logger
from app.recognition.ports import ComponentStatus

logger = get_logger(__name__)


def _import_onnxruntime() -> Any:
    try:
        import onnxruntime
    except ImportError as exc:  # pragma: no cover - depends on the install extra
        raise DependencyNotConfiguredError(
            "onnxruntime is required to run the face models. Install the recognition extra: "
            "pip install -e '.[recognition]'."
        ) from exc
    return onnxruntime


def resolve_providers(requested: tuple[str, ...]) -> list[str]:
    """Keep only providers this onnxruntime build actually offers."""
    onnxruntime = _import_onnxruntime()
    available = set(onnxruntime.get_available_providers())
    usable = [provider for provider in requested if provider in available]
    if not usable:
        logger.warning(
            "None of the requested ONNX providers %s are available (have: %s); using CPU.",
            list(requested),
            sorted(available),
        )
        return ["CPUExecutionProvider"]
    return usable


class OnnxModel:
    """A lazily loaded ONNX graph with a reportable status."""

    def __init__(
        self,
        *,
        component: str,
        model_path: Path,
        providers: tuple[str, ...],
        intra_op_threads: int,
        quiet: bool = False,
    ) -> None:
        self._component = component
        self._path = Path(model_path)
        self._requested_providers = providers
        self._intra_op_threads = intra_op_threads
        self._quiet = quiet
        self._session: Any | None = None
        self._input_name: str | None = None
        self._lock = threading.Lock()
        self._load_error: str | None = None

    # ------------------------------------------------------------------ status
    @property
    def path(self) -> Path:
        return self._path

    @property
    def loaded(self) -> bool:
        return self._session is not None

    def status(self) -> ComponentStatus:
        detail = f"{self._path.name} providers={list(self._requested_providers)}"
        if self._load_error:
            detail = f"{detail} load_error={self._load_error}"
        elif self._session is not None:
            detail = f"{detail} loaded=true"
        return ComponentStatus(
            name=self._component,
            configured=self._load_error is None,
            adapter="onnxruntime",
            detail=detail,
        )

    # ------------------------------------------------------------------ loading
    def session(self) -> Any:
        if self._session is None:
            with self._lock:
                if self._session is None:
                    self._session = self._load()
        return self._session

    def warmup(self) -> None:
        """Load eagerly at startup so /health reports the truth before traffic."""
        try:
            self.session()
        except Exception as exc:
            self._load_error = str(exc)
            logger.error("Failed to load %s from %s: %s", self._component, self._path, exc)

    def _load(self) -> Any:
        if not self._path.is_file():
            raise DependencyNotConfiguredError(
                f"The {self._component} model file is missing.",
                details={"expected_path": str(self._path)},
            )
        onnxruntime = _import_onnxruntime()
        options = onnxruntime.SessionOptions()
        if self._intra_op_threads > 0:
            options.intra_op_num_threads = self._intra_op_threads
        if self._quiet:
            # ERROR only. Some exports declare a fixed batch on their output while
            # accepting a dynamic input batch, which makes onnxruntime log a shape
            # warning on every batched call even though the result is correct.
            options.log_severity_level = 3
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        try:
            session = onnxruntime.InferenceSession(
                str(self._path),
                sess_options=options,
                providers=resolve_providers(self._requested_providers),
            )
        except Exception as exc:
            raise DependencyUnavailableError(
                f"The {self._component} model could not be loaded.",
                details={"path": str(self._path), "driver_error": str(exc)},
            ) from exc
        self._input_name = session.get_inputs()[0].name
        self._load_error = None
        logger.info(
            "Loaded %s from %s (providers=%s)",
            self._component,
            self._path.name,
            session.get_providers(),
        )
        return session

    # ------------------------------------------------------------------ running
    @property
    def input_name(self) -> str:
        self.session()
        assert self._input_name is not None
        return self._input_name

    def input_shape(self) -> list[Any]:
        return list(self.session().get_inputs()[0].shape)

    def run(self, blob: Any) -> list[Any]:
        try:
            return self.session().run(None, {self.input_name: blob})
        except Exception as exc:
            raise DependencyUnavailableError(
                f"Inference failed for the {self._component} model.",
                details={"driver_error": str(exc)},
            ) from exc
