# Third-Party Libraries and Tools

Split by where each one actually runs. Serving depends on `onnxruntime` alone —
**PyTorch and the `insightface` package are not serving dependencies**, they
belong to the research pipeline.

## Serving (backend + frontend)

| Tool | Purpose |
|------|---------|
| Python 3.11+ | Backend runtime (`enum.StrEnum` requires 3.11) |
| FastAPI | REST APIs and WebSocket communication |
| Pydantic v2 / pydantic-settings | Validates requests, responses and `ARGUS_`-prefixed configuration |
| Uvicorn | ASGI server |
| SQLAlchemy 2 (async) + asyncpg | PostgreSQL access, set-based statements |
| Alembic | Schema migrations (`0001_initial_schema` == `docs/db.md`) |
| PostgreSQL | Classrooms, students, sessions, attendance, image URLs, constraints |
| ChromaDB | Stores face embeddings and performs cosine similarity search |
| onnxruntime | **Executes the SCRFD and ArcFace ONNX graphs** — the only inference runtime at serving time |
| OpenCV | Image decoding, alignment, geometric mask synthesis, video frame sampling |
| NumPy | Embedding and vector manipulation |
| boto3 | Cloudflare R2 (S3-compatible) uploads for enrollment images |
| Next.js 16 / React 19 | Frontend operator console |
| TypeScript | Type-safe frontend development |
| Tailwind CSS v4 + Radix UI | Styling and accessible UI primitives |
| TanStack Query | Server-state management and caching |
| Zustand | Local UI state (sidebar, theme) |
| Recharts | Attendance reporting charts |

## Models (weights, not libraries)

| Model | Purpose |
|------|---------|
| SCRFD (`det_10g.onnx`) | Detects faces and 5-point facial landmarks |
| ArcFace (`w600k_r50.onnx`) | Generates 512-dimensional L2-normalised face embeddings |

Both ship in the InsightFace `buffalo_l` pack. The pack is git-ignored — see the
root `README.md` for the expected layout.

## Research pipeline only

| Tool | Purpose |
|------|---------|
| InsightFace | Reference implementations and the `buffalo_l` weights used for batch embedding extraction |
| PyTorch | Dependency of the research-side tooling; the abandoned fine-tuning experiment used it. Not used at serving time |
| dlib | Facial landmark detection required by the vendored masking tools |
| MaskTheFace | Generates synthetic masked face images (`surgical`, `surgical_blue`, `N95`, `KN95`, `cloth`) |
| RWMFD masking | Produces additional synthetic mask variations (`rwmfd_blue`, `rwmfd_black`) |
| scikit-learn | Evaluation metrics (ROC-AUC, TAR@FAR) and threshold analysis |
| SciPy | Numerical support for the evaluation scripts |
| Matplotlib | Plots ROC curves and result visualisations |
| pytest | Test suites on both halves of the repository |

## Datasets

| Dataset | Purpose |
|------|---------|
| LFW | Baseline recognition and the synthetic-mask evaluation subset |
| MFR2 | Real masked-face evaluation (53 identities, 269 images) |
| RWMFD | Real-world masked face data and its masking tool |

See `datasets/README.md` for provenance and exactly which images entered each
result.
