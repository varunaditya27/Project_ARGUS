"""Shared onnxruntime plumbing for the vision adapters.

Both models in the InsightFace buffalo_l pack are plain ONNX graphs, so serving
needs onnxruntime only. Sessions load lazily and exactly once; InferenceSession
is thread-safe, which matters because inference runs on worker threads.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import onnxruntime

from app.core.errors import DependencyNotConfiguredError, DependencyUnavailableError
from app.core.logging import get_logger
from app.recognition.ports import ComponentStatus

logger = get_logger(__name__)


def resolve_providers(requested: tuple[str, ...]) -> list[str]:
    # Keep only the providers this onnxruntime build actually offers.
    available = set(onnxruntime.get_available_providers())
    usable = [provider for provider in requested if provider in available]
    if not usable:
        logger.warning("Requested ONNX providers %s unavailable; using CPU.", list(requested))
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
        self._providers = providers
        self._intra_op_threads = intra_op_threads
        self._quiet = quiet
        self._session: Any | None = None
        self._input_name: str | None = None
        self._lock = threading.Lock()
        self._load_error: str | None = None

    def status(self) -> ComponentStatus:
        # Reports the model file and whether it loaded.
        detail = f"{self._path.name} providers={list(self._providers)}"
        if self._load_error:
            detail = f"{detail} load_error={self._load_error}"
        elif self._session is not None:
            detail = f"{detail} loaded=true"
        return ComponentStatus(
            name=self._component, configured=self._load_error is None, detail=detail
        )

    def session(self) -> Any:
        # Load on first use, under a lock so two threads cannot both load.
        if self._session is None:
            with self._lock:
                if self._session is None:
                    self._session = self._load()
        return self._session

    def warmup(self) -> None:
        # Load eagerly at startup so /health reports the truth before traffic.
        try:
            self.session()
        except Exception as exc:
            self._load_error = str(exc)
            logger.error("Failed to load %s from %s: %s", self._component, self._path, exc)

    def _load(self) -> Any:
        # Build the inference session, or fail with the path that was expected.
        if not self._path.is_file():
            raise DependencyNotConfiguredError(
                f"The {self._component} model file is missing.",
                details={"expected_path": str(self._path)},
            )
        options = onnxruntime.SessionOptions()
        if self._intra_op_threads > 0:
            options.intra_op_num_threads = self._intra_op_threads
        if self._quiet:
            # ERROR only: some exports declare a fixed output batch while
            # accepting a dynamic input batch, which logs a benign shape warning.
            options.log_severity_level = 3
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        try:
            session = onnxruntime.InferenceSession(
                str(self._path), sess_options=options, providers=resolve_providers(self._providers)
            )
        except Exception as exc:
            raise DependencyUnavailableError(
                f"The {self._component} model could not be loaded.",
                details={"path": str(self._path), "driver_error": str(exc)},
            ) from exc
        self._input_name = session.get_inputs()[0].name
        self._load_error = None
        logger.info("Loaded %s from %s", self._component, self._path.name)
        return session

    def input_shape(self) -> list[Any]:
        # Declared input dimensions, which may contain symbolic entries.
        return list(self.session().get_inputs()[0].shape)

    def run(self, blob: Any) -> list[Any]:
        # Single forward pass.
        session = self.session()
        assert self._input_name is not None
        try:
            return session.run(None, {self._input_name: blob})
        except Exception as exc:
            raise DependencyUnavailableError(
                f"Inference failed for the {self._component} model.",
                details={"driver_error": str(exc)},
            ) from exc
