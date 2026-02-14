# Design Document: Stolen Item Investigation UI

## 1. Overview

A single-page React application that enables users to report a potentially stolen item, process the report against an existing vector search backend, and present investigation results through two complementary views: a **Calendar View** (likelihood heatmap) and a **Data Table View** (tabular evidence).

### User Flow

```
[Input Phase] → [Processing Phase] → [Results Phase]
     │                  │                    │
 Textarea +        Animated           Calendar (left)
 Submit btn      Progress bar        DataTable (right)
```

The three phases are mutually exclusive: only one is visible at a time.

---

## 2. Architecture

### 2.1 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | React 19 + TypeScript | UI framework |
| Build | Vite 7 | Dev server + bundler |
| Components | shadcn/ui | Accessible component primitives |
| Styling | Tailwind CSS v4 | Utility-first styling |
| Table Engine | TanStack React Table | Headless table logic |
| Calendar | react-day-picker (via shadcn Calendar) | Date rendering |
| Date Utils | date-fns | Date formatting |
| Icons | lucide-react | Icon set |
| HTTP | fetch (native) | Backend communication |

### 2.2 Backend Integration

**Existing API** (Modal + FastAPI): `https://alemanb--treehacks-vector-search-web.modal.run`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Connectivity check |
| `/ingest` | POST | Single observation ingestion |
| `/ingest/batch` | POST | Batch ingestion |
| `/search` (TBD) | POST | Vector similarity search *(to be implemented)* |

**Note**: The backend currently has ingestion endpoints only. A `/search` endpoint will need to be added to query Elasticsearch by vector similarity. Until then, the frontend will use **mock data** that mirrors the expected search response shape.

### 2.3 Expected Search Response Schema

```typescript
interface SearchResult {
  id: string
  content: string           // natural language description (from embedding source)
  score: number             // cosine similarity 0-1 → mapped to likelihood percentage
  metadata: {
    object: string | null
    color: string | null
    timestamp: string       // ISO 8601 (e.g., "2026-02-13T14:30:05Z")
    motion_vector: number[] | null
    device_id: string | null
  }
}

interface SearchResponse {
  query: string
  results: SearchResult[]
}
```

The `score` (0.0–1.0) will be converted to a **likelihood percentage** (0–100%) for display.

---

## 3. Component Architecture

### 3.1 Component Tree

```
App
└── InvestigationPage
    ├── InputPhase
    │   ├── Textarea (shadcn)
    │   └── Button (shadcn)
    ├── ProcessingPhase
    │   ├── Progress (shadcn)
    │   └── Status text
    └── ResultsPhase
        ├── CalendarView
        │   ├── Calendar (shadcn / react-day-picker)
        │   ├── Popover (shadcn)
        │   └── Card (shadcn) [inside popover]
        └── DataTableView
            ├── DataTable (TanStack + shadcn Table)
            └── LikelihoodBadge (custom, uses Badge from shadcn)
```

### 3.2 State Machine

The page operates as a three-state machine:

```
┌─────────┐    submit    ┌────────────┐   complete   ┌─────────┐
│  INPUT   │ ──────────→ │ PROCESSING │ ───────────→ │ RESULTS │
└─────────┘              └────────────┘              └─────────┘
     ↑                                                    │
     └────────────────── "New Search" ────────────────────┘
```

**State type**:
```typescript
type Phase = "input" | "processing" | "results"
```

---

## 4. Component Specifications

### 4.1 InputPhase

**shadcn components**: `Textarea`, `Button`

| Element | Spec |
|---------|------|
| Textarea | Multi-line, placeholder: "Describe the item you think was stolen..." |
| Submit button | Disabled when textarea is empty, label: "Investigate" |
| Layout | Centered on page, max-width constraint (e.g., `max-w-2xl`) |

**Behavior**:
- User types a description (e.g., "My blue backpack was stolen from the library")
- If text includes "show me the last movement" or similar phrasing, the frontend flags `include_motion: true` in the search request
- On submit → transition to `processing` phase

### 4.2 ProcessingPhase

**shadcn components**: `Progress`

| Element | Spec |
|---------|------|
| Progress bar | Animated, indeterminate or simulated progress (0→100 over request duration) |
| Status text | Below progress bar: "Analyzing observations..." |
| Layout | Centered, same position as input was |

**Behavior**:
- Fires the search API call
- Simulates progress (increment every ~200ms)
- On API response → jump to 100%, brief pause, transition to `results`

### 4.3 ResultsPhase

**Layout**: Two-column, side-by-side.

```
┌──────────────────────┬──────────────────────┐
│   Calendar View      │   Data Table View    │
│   (left column)      │   (right column)     │
└──────────────────────┴──────────────────────┘
```

Uses a responsive grid: `grid grid-cols-1 lg:grid-cols-2 gap-6` — stacks on mobile, side-by-side on desktop.

#### 4.3.1 CalendarView

**shadcn components**: `Calendar`, `Popover`, `PopoverContent`, `PopoverTrigger`, `Card`, `CardContent`

**Date highlighting logic**:
- Group search results by date (from `metadata.timestamp`)
- For each date, take the **highest** likelihood score among that day's results
- Apply color based on likelihood tier:

| Likelihood | Color | Tailwind class (bg) | Tailwind class (text) |
|------------|-------|---------------------|-----------------------|
| >= 85% | Green | `bg-emerald-500` | `text-emerald-50` |
| 70–84% | Yellow | `bg-amber-400` | `text-amber-900` |
| < 70% | Red | `bg-red-500` | `text-red-50` |

**Most likely indicator**: The date with the overall highest percentage displays a small star icon or "Most Likely" badge overlay.

**Date click behavior**:
- Clicking a highlighted date opens a `Popover` anchored to that date cell
- Inside the popover, a `Card` displays:
  - **Time**: formatted as `MM-DD-YY HH:MM AM/PM`
  - **Link**: `<a href="#">View Details</a>` (placeholder, non-functional)
- If multiple results share the same date, show a list within the card

**Custom day rendering**: Override `react-day-picker`'s day cell to apply background colors and render the "Most Likely" indicator.

#### 4.3.2 DataTableView

**shadcn components**: `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell`, `Badge`

**Dependencies**: `@tanstack/react-table`

**Columns** (left to right):

| Header | Source | Formatting |
|--------|--------|-----------|
| Content | `result.content` | Plain text (already human-readable from the embedding source) |
| Time | `result.metadata.timestamp` | `MM-DD-YY HH:MM AM/PM` via `date-fns` `format()` |
| Likelihood | `result.score * 100` | Percentage + colored Badge |
| Link | — | `<a href="#">View</a>` (placeholder) |

**Likelihood Badge**:

| Range | Badge bg | Badge text | Border |
|-------|---------|-----------|--------|
| >= 85% | `bg-emerald-100` | `text-emerald-600` | none (`border-0`) |
| 70–84% | `bg-amber-100` | `text-amber-600` | none (`border-0`) |
| < 70% | `bg-red-100` | `text-red-600` | none (`border-0`) |

Badge is rendered with `border-0` to remove any default border. Text color is intentionally lighter than a full-contrast foreground to match the spec ("lighter color than badge color").

---

## 5. Color System

### 5.1 Application Theme

Uses shadcn/ui default theme with Tailwind CSS. Neutral palette for chrome, semantic colors for likelihood tiers only.

### 5.2 Likelihood Tier Colors (Shared)

Both CalendarView and DataTableView use the same semantic mapping:

```typescript
export type LikelihoodTier = "high" | "medium" | "low"

export function getLikelihoodTier(percentage: number): LikelihoodTier {
  if (percentage >= 85) return "high"
  if (percentage >= 70) return "medium"
  return "low"
}

export const TIER_STYLES = {
  high: {
    calendarBg: "bg-emerald-500",
    calendarText: "text-emerald-50",
    badgeBg: "bg-emerald-100",
    badgeText: "text-emerald-600",
  },
  medium: {
    calendarBg: "bg-amber-400",
    calendarText: "text-amber-900",
    badgeBg: "bg-amber-100",
    badgeText: "text-amber-600",
  },
  low: {
    calendarBg: "bg-red-500",
    calendarText: "text-red-50",
    badgeBg: "bg-red-100",
    badgeText: "text-red-600",
  },
} as const
```

---

## 6. Data Flow

### 6.1 Sequence Diagram

```
User                  Frontend                  Backend (Modal)
 │                      │                          │
 │ types description    │                          │
 │ clicks "Investigate" │                          │
 │─────────────────────→│                          │
 │                      │ POST /search             │
 │                      │ { query, include_motion } │
 │                      │─────────────────────────→│
 │                      │                          │ embed query via Jina
 │                      │                          │ kNN search in ES
 │                      │                          │←─────────────────
 │                      │ SearchResponse           │
 │                      │←─────────────────────────│
 │                      │                          │
 │ results rendered     │                          │
 │←─────────────────────│                          │
```

### 6.2 Data Transformation Pipeline

```
SearchResponse.results
    │
    ├──→ groupByDate()     → Map<dateString, SearchResult[]>  → CalendarView
    │     └─ max score per day → color tier
    │     └─ overall max → "Most Likely" indicator
    │
    └──→ formatForTable()  → TableRow[]                       → DataTableView
          └─ content: string
          └─ time: formatted string
          └─ likelihood: { percentage, tier }
          └─ link: "#"
```

---

## 7. Mock Data Contract

Until the `/search` endpoint is built, use this mock structure:

```typescript
export const MOCK_RESULTS: SearchResult[] = [
  {
    id: "doc_001",
    content: "Blue backpack detected on shelf near entrance camera",
    score: 0.92,
    metadata: {
      object: "backpack",
      color: "blue",
      timestamp: "2026-02-10T09:15:00Z",
      motion_vector: [0.3, -0.1],
      device_id: "jetson_01",
    },
  },
  {
    id: "doc_002",
    content: "Blue bag moved from table to floor area",
    score: 0.78,
    metadata: {
      object: "bag",
      color: "blue",
      timestamp: "2026-02-11T14:30:00Z",
      motion_vector: [0.5, -0.4],
      device_id: "jetson_02",
    },
  },
  {
    id: "doc_003",
    content: "Person carrying blue item exiting through side door",
    score: 0.65,
    metadata: {
      object: "unknown",
      color: "blue",
      timestamp: "2026-02-12T18:45:00Z",
      motion_vector: [0.8, 0.2],
      device_id: "jetson_03",
    },
  },
  // ... more entries for calendar population
]
```

---

## 8. File Structure (Target)

```
frontend/src/
├── main.tsx
├── App.tsx                          # Root, renders InvestigationPage
├── index.css                        # Tailwind directives + shadcn theme
├── lib/
│   ├── utils.ts                     # cn() helper (shadcn standard)
│   └── likelihood.ts                # getLikelihoodTier(), TIER_STYLES
├── types/
│   └── search.ts                    # SearchResult, SearchResponse interfaces
├── hooks/
│   └── useSearch.ts                 # Search API hook (mock for now)
├── data/
│   └── mock-results.ts             # Mock search results
├── components/
│   ├── ui/                          # shadcn primitives (auto-generated)
│   │   ├── badge.tsx
│   │   ├── button.tsx
│   │   ├── calendar.tsx
│   │   ├── card.tsx
│   │   ├── input.tsx
│   │   ├── popover.tsx
│   │   ├── progress.tsx
│   │   ├── table.tsx
│   │   └── textarea.tsx
│   ├── investigation/
│   │   ├── InvestigationPage.tsx     # Phase state machine container
│   │   ├── InputPhase.tsx            # Textarea + submit
│   │   ├── ProcessingPhase.tsx       # Progress bar + status
│   │   └── ResultsPhase.tsx          # Two-column results layout
│   ├── calendar/
│   │   ├── CalendarView.tsx          # Calendar with highlighted dates
│   │   └── DateDetailCard.tsx        # Popover card for date click
│   └── data-table/
│       ├── DataTableView.tsx         # TanStack table wrapper
│       ├── columns.tsx               # Column definitions
│       └── LikelihoodBadge.tsx       # Colored badge component
└── components.json                   # shadcn config (project root)
```

---

## 9. Accessibility Considerations

- All interactive elements have proper `aria-label` attributes
- Calendar navigation is keyboard-accessible (react-day-picker built-in)
- Badge colors are supplemented with text percentages (not color-only indicators)
- Popover content is focus-trapped and dismissible via Escape
- Table has proper `<thead>` / `<tbody>` semantics via shadcn Table

---

## 10. Responsive Design

| Breakpoint | Layout |
|-----------|--------|
| < 1024px (`lg`) | Single column — Calendar stacked above DataTable |
| >= 1024px | Two-column side-by-side |

Input and Processing phases are always centered single-column.

---

## 11. Key Design Decisions

1. **Three-phase state machine** over router-based navigation: simpler, no URL routing needed for a single-page flow
2. **shadcn/ui primitives** over custom components: consistent accessible design, Tailwind-native
3. **Mock data first**: decouples frontend work from backend `/search` endpoint development
4. **Shared likelihood utilities**: single source of truth for color mapping across Calendar and DataTable
5. **TanStack React Table**: headless table engine allows full control over cell rendering while shadcn provides the visual shell
6. **date-fns for formatting**: already a dependency of shadcn Calendar, no extra bundle cost
