# Project ARGUS - Frontend Application

> **Production-Quality Modern SaaS Interface for ARGUS (Masked Face Recognition Attendance System)**

This is the complete, high-performance, and modular frontend for **Project ARGUS**, built with **Next.js 15 (App Router)**, **TypeScript**, **Tailwind CSS**, **shadcn/ui design language**, **Framer Motion**, and **TanStack Query**.

---

## 🚀 Key Features & Highlights

- **Linear / Vercel / Stripe Dashboard Aesthetic**: Modern dark mode first, subtle micro-animations, glassmorphism card containers, curated typography, and high contrast status indicators.
- **Webcam Viewport Placeholders (Zero Stock Images)**: Production-ready `<video>` viewport components pre-wired for `navigator.mediaDevices.getUserMedia()` integration without requiring layout refactoring. Includes controls for Start/Stop Stream, Snapshot Capture, Switch Device, and Fullscreen.
- **Dynamic Bounding Box Overlays**: Real-time bounding box overlays for recognized faces, unmasked targets, confidence percentages, mask detection badges, and unknown subject alerts.
- **Complete Feature Pages**:
  1. **Dashboard**: Executive summary, KPI stat cards, Recharts accuracy trends (Baseline vs Masked ArcFace vs ARGUS), daily attendance bar charts, and live activity stream.
  2. **Enrollment**: Multi-step student enrollment form (React Hook Form + Zod), drag-and-drop file upload, webcam snapshot capture, and animated 5-step synthetic mask generation status checklist.
  3. **Live Recognition**: Real-time recognition viewport with target bounding box overlays, stream control buttons, latency/FPS metrics, live recognition stream table, and expected attendance checklist.
  4. **Attendance Log**: Professional table with live search, date/class/status filters, column sorting, pagination, and instant CSV/PDF export triggers.
  5. **Students Roster**: Full CRUD UI, student profile cards with initial avatars (**no photographs**), search, department filtering, and modal dialogs.
  6. **Classrooms**: Hardware node status cards, seating capacity gauges, assigned faculty, and quick stream launcher.
  7. **Sessions**: Active session hero card, timetable scheduler, and session creation modal.
  8. **Reports**: Recognition accuracy gap analysis charts, department breakdown, and weekly matrix heatmaps.
  9. **Settings**: Hyper-parameter sliders (cosine similarity cutoff, synthetic mask variant count, unknown rejection cutoff), model backbone selectors, theme toggles, and vector storage health.

---

## 📂 Scalable Clean Architecture & Directory Structure

```text
frontend/
├── src/
│   ├── app/                    # Next.js App Router Page Routes
│   │   ├── (pages)/
│   │   │   ├── page.tsx        # Executive Dashboard
│   │   │   ├── enrollment/     # Face Enrollment & Synthetic Mask Generation
│   │   │   ├── live-recognition/# Real-time Detection Viewport
│   │   │   ├── attendance/     # Attendance Records Log
│   │   │   ├── students/       # Student Roster CRUD
│   │   │   ├── classrooms/     # Physical Rooms & Hardware Nodes
│   │   │   ├── sessions/       # Timetable & Session Scheduler
│   │   │   ├── reports/        # Accuracy & Attendance Analytics
│   │   │   └── settings/       # Hyperparameters & Model Configs
│   │   ├── globals.css         # Design Tokens, Animations & Theme CSS
│   │   └── layout.tsx          # Root Layout & Theme Configuration
│   ├── components/
│   │   ├── ui/                 # Atomic UI Components (Button, Card, Badge, Dialog, etc.)
│   │   ├── common/             # Layout Navigation (Sidebar, Header, SearchModal, Notifications)
│   │   └── webcam/             # Webcam Viewport & Live Recognition Overlays
│   ├── services/               # API Abstraction Layer (mocked Promises, ready for FastAPI)
│   │   ├── api.ts              # Base HTTP Client & Delay Simulator
│   │   ├── student.ts          # Student API Service
│   │   ├── attendance.ts       # Attendance API Service
│   │   ├── recognition.ts      # Recognition Stream API Service
│   │   ├── session.ts          # Session API Service
│   │   ├── classroom.ts        # Classroom API Service
│   │   ├── report.ts           # Report API Service
│   │   └── settings.ts         # Settings API Service
│   ├── store/                  # Zustand Client State Management
│   │   ├── use-theme-store.ts
│   │   ├── use-sidebar-store.ts
│   │   ├── use-live-recognition-store.ts
│   │   └── use-enrollment-store.ts
│   ├── types/                  # Strict TypeScript Interfaces
│   ├── mock/                   # Realistic Mock Datasets
│   ├── hooks/                  # Custom Hooks (Webcam, Time, Keyboard Shortcuts)
│   ├── lib/                    # Utilities & Class Merging (clsx, twMerge)
│   ├── providers/              # React Query & Theme Providers
│   └── layouts/                # Dashboard Layout Wrapper
├── package.json
└── README.md
```

---

## ⚡ Getting Started & Running Locally

### 1. Install Dependencies
```bash
npm install
```

### 2. Start Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🔗 Connecting to FastAPI Backend

To connect this frontend application to the FastAPI backend:
1. Update `process.env.NEXT_PUBLIC_API_URL` in `.env.local` to point to your FastAPI server (`http://localhost:8000/api/v1`).
2. Open `src/services/*.ts` files and replace the `simulateDelay` mocked responses with actual `fetch` or `axios` calls to your API endpoints. No component refactoring is required!

---

## 📷 Connecting Real Webcam Stream

The webcam component (`src/components/webcam/webcam-viewport-placeholder.tsx`) includes a `<video ref={videoRef}>` element. To stream real user camera feeds:
```ts
const stream = await navigator.mediaDevices.getUserMedia({ video: true });
if (videoRef.current) {
  videoRef.current.srcObject = stream;
}
```

---

## 🛠️ Technology Stack

- **Framework**: Next.js 15 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Components**: Radix UI Primitives / Lucide Icons
- **State Management**: Zustand & TanStack Query (React Query)
- **Forms & Validation**: React Hook Form + Zod
- **Visualizations**: Recharts
- **Animations**: Framer Motion
