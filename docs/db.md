# Database Schema

Project ARGUS uses PostgreSQL as the relational database to manage student information, classrooms, sessions, and attendance records. Face embeddings are **not stored** in PostgreSQL—they are managed separately in **ChromaDB**.

---

# Students

Stores the enrolled student information.

| Column | Data Type | Constraints | Description |
|---------|-----------|-------------|-------------|
| student_id | UUID | PRIMARY KEY | Unique student identifier |
| student_name | TEXT | NOT NULL | Full name of the student |
| roll_no | INTEGER | UNIQUE, NOT NULL | Student roll number |
| class_id | UUID | FOREIGN KEY | Assigned classroom |
| image_url | TEXT | NOT NULL | Cloudflare R2 URL of the original enrollment image |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Enrollment timestamp |

---

# Classrooms

Stores classroom information.

| Column | Data Type | Constraints | Description |
|---------|-----------|-------------|-------------|
| class_id | UUID | PRIMARY KEY | Unique classroom identifier |
| class_name | TEXT | NOT NULL | Classroom name (e.g., CSE-A) |
| department | TEXT | NOT NULL | Department name |
| semester | INTEGER | NOT NULL | Semester number |
| strength | INTEGER | NOT NULL | Total number of students |

---

# Class Sessions

Represents an individual lecture or attendance session.

| Column | Data Type | Constraints | Description |
|---------|-----------|-------------|-------------|
| session_id | UUID | PRIMARY KEY | Unique session identifier |
| class_id | UUID | FOREIGN KEY | Classroom conducting the session |
| subject | TEXT | NOT NULL | Subject name |
| faculty | TEXT | NOT NULL | Faculty conducting the class |
| date | DATE | NOT NULL | Session date |
| start_time | TIME | NOT NULL | Lecture start time |
| end_time | TIME | NOT NULL | Lecture end time |
| status | TEXT | NOT NULL | ACTIVE / CLOSED |

---

# Attendance

Stores attendance records generated after successful recognition.

| Column | Data Type | Constraints | Description |
|---------|-----------|-------------|-------------|
| attendance_id | UUID | PRIMARY KEY | Unique attendance record |
| session_id | UUID | FOREIGN KEY | Class session |
| student_id | UUID | FOREIGN KEY | Recognized student |
| timestamp | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Detection time |
| confidence | FLOAT | NOT NULL | Recognition confidence score |
| status | TEXT | NOT NULL | Present / Absent |

## Constraint

```sql
UNIQUE(session_id, student_id)
```

Ensures attendance can only be marked once per student for each session.

---

# Relationships

```text
Classrooms
      │
      │ 1
      │
      │ N
Students
      │
      │ 1
      │
      │ N
Attendance
      │
      │ N
      │
      │ 1
Class Sessions
```

---

# Database Responsibilities

## PostgreSQL

Stores:

- Student information
- Classroom information
- Lecture/Class sessions
- Attendance records
- Image URLs
- Relational data and constraints

---

## ChromaDB (Vector Database)

Stores:

- Multiple masked face embeddings for each student
- Cosine similarity index
- Embedding metadata
  - student_id
  - mask_type
  - model_version

---

## Cloudflare R2 Storage

Stores:

- Original enrollment image
- Synthetic masked images generated using MaskTheFace

---

# Recognition Workflow

```text
Webcam
   │
   ▼
Masked Face
   │
   ▼
ArcFace Embedding
   │
   ▼
ChromaDB Similarity Search
   │
   ▼
student_id
   │
   ▼
PostgreSQL
   │
   ├── Fetch Student Details
   ├── Fetch Active Class Session
   └── Insert Attendance Record
   │
   ▼
Attendance Successfully Marked
```
