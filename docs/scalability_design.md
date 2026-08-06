# Scalability & Sustainability

ARGUS is designed to handle increasing amounts of data while remaining easy to maintain and extend. This is achieved through a scalable database architecture, modular backend design, and lightweight automated testing.

---

# 1. Database Design

## Polyglot Persistence

Instead of storing every type of data in a single database, ARGUS stores each type of data in the system best suited for it.

```text
                ┌─────────────────────┐
                │     ARGUS Backend   │
                └──────────┬──────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌────────────────┐  ┌────────────────┐  ┌─────────────────┐
│ PostgreSQL     │  │ ChromaDB       │  │ Cloudflare R2   │
├────────────────┤  ├────────────────┤  ├─────────────────┤
│ Students       │  │ Face           │  │ Face Images     │
│ Attendance     │  │ Embeddings     │  │                 │
│ Sessions       │  │                │  │                 │
└────────────────┘  └────────────────┘  └─────────────────┘
```

### Why?

| Storage | Purpose |
|---------|---------|
| PostgreSQL | Structured relational data |
| ChromaDB | Fast vector similarity search |
| Cloudflare R2 | Large image storage |

Separating these responsibilities keeps each system efficient and allows the application to scale as the number of students and attendance records grows.

---

## Image Storage

Instead of storing images inside PostgreSQL:

```text
PostgreSQL

Student
──────────────
ID
Name
Image_URL
```

the actual image is stored separately.

```text
Image_URL
      │
      ▼
Cloudflare R2
      │
      ▼
student_001.jpg
```

### Benefits

- Smaller database
- Faster queries
- Faster backups
- Lower storage costs

---

## Storage Replacement

Because the backend communicates through a storage interface, replacing storage providers does not affect the application logic.

```text
          Storage Interface
                 │
       ┌─────────┴─────────┐
       │                   │
Cloudflare R2          AWS S3
```

Only the implementation changes.

The rest of the system remains unchanged.

---

## Database Integrity

Attendance records include

```sql
UNIQUE(session_id, student_id)
```

This prevents duplicate attendance entries, even if multiple requests arrive simultaneously.

---

# 2. Coding Architecture

## Modular Backend

Each service performs one specific responsibility.

```text
                ARGUS Backend

                     │

 ┌──────────┬────────┼─────────┬──────────┐
 │          │        │         │          │
 ▼          ▼        ▼         ▼          ▼

Recognition Attendance Storage Import Repository
 Service      Service  Service Service   Layer
```

Since every module is independent, adding features or modifying one service has minimal impact on the rest of the project.

---

## Observation Buffer

A webcam captures approximately **30 frames every second**.

Without buffering:

```text
Frame 1  → Database Write
Frame 2  → Database Write
Frame 3  → Database Write
Frame 4  → Database Write
...
Frame 150 → Database Write
```

The same student may generate hundreds of unnecessary database operations.

---

With the Observation Buffer:

```text
Frame 1
Frame 2
Frame 3
Frame 4
   │
   ▼

Observation Buffer

   │
Merge duplicate detections
Keep highest confidence

   │
   ▼

Single Database Write
```

### Benefits

- Fewer database writes
- Lower CPU usage
- Reduced processing overhead
- Better performance
- Supports multiple classrooms simultaneously

---

## Dependency Injection

Instead of depending directly on Cloudflare R2:

```text
Attendance Service
        │
        ▼
Cloudflare R2
```

ARGUS depends on an interface.

```text
Attendance Service
        │
        ▼
 Storage Interface
        │
 ┌──────┴───────┐
 │              │
 ▼              ▼
Cloudflare    AWS S3
```

Only the implementation changes.

The Attendance Service never changes.

The same principle is used for replacing AI models.

---

# 3. Automated Testing

## Lightweight Testing

Instead of loading every external component:

```text
Tests

    │

    ├── PostgreSQL
    ├── Cloudflare R2
    ├── ArcFace
    └── Camera
```

tests use lightweight mock implementations.

```text
Tests

    │

    ├── Fake Database
    ├── RecordingStorage
    ├── FakeImportService
    └── Mock AI
```

This allows the complete test suite to execute in seconds.

---

## Business Logic Testing

The recognition logic is tested independently.

```text
Confidence

0.91 ─────────► Match

0.71 ─────────► Human Review

0.31 ─────────► Unknown
```

Since these tests don't depend on cameras or AI models, they execute quickly and reliably.

---

# Summary

| Component | Scalability | Sustainability |
|-----------|-------------|----------------|
| Database | Polyglot persistence keeps each database focused on its own task. | Storage providers can be replaced independently. |
| Backend | Observation Buffer reduces unnecessary processing and database writes. | Dependency Injection allows components to be swapped without changing business logic. |
| Testing | Lightweight tests execute quickly even as the project grows. | Mock services and isolated logic make future maintenance easier. |