# Implementation Plan: Stolen Item Investigation UI

## Prerequisites

- Node.js 18+
- Existing frontend boilerplate (React 19 + TypeScript + Vite 7)
- Reference: [Design Document](./design-document.md)

---

## Phase 1: Project Setup & Dependencies

### 1.1 Install Tailwind CSS v4

```bash
cd frontend
npm install tailwindcss @tailwindcss/vite
```

Update `vite.config.ts` to include the Tailwind plugin:

```typescript
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

Update `src/index.css` to import Tailwind:

```css
@import "tailwindcss";
```

### 1.2 Initialize shadcn/ui

```bash
npx shadcn@latest init
```

Configuration choices:
- Style: **Default**
- Base color: **Neutral**
- CSS variables: **Yes**

This creates `components.json` and sets up `src/lib/utils.ts` with the `cn()` helper.

### 1.3 Install shadcn Components

```bash
npx shadcn@latest add button textarea progress calendar card popover badge table
```

This generates component files under `src/components/ui/`.

### 1.4 Install TanStack React Table

```bash
npm install @tanstack/react-table
```

### 1.5 Verify Setup

- Run `npm run dev` — app loads with Tailwind styles active
- Confirm `src/components/ui/` contains all installed component files
- Confirm `src/lib/utils.ts` exists with `cn()` function

**Deliverables**: Working dev server, all dependencies installed, shadcn configured.

---

## Phase 2: Types, Utilities & Mock Data

### 2.1 Create Type Definitions

**File**: `src/types/search.ts`

Define:
- `SearchResult` interface (id, content, score, metadata)
- `SearchResponse` interface (query, results)
- `Metadata` interface (object, color, timestamp, motion_vector, device_id)

### 2.2 Create Likelihood Utilities

**File**: `src/lib/likelihood.ts`

Implement:
- `getLikelihoodTier(percentage: number): "high" | "medium" | "low"`
  - >= 85 → `"high"`
  - >= 70 → `"medium"`
  - < 70 → `"low"`
- `TIER_STYLES` constant mapping tiers to Tailwind classes for both calendar and badge contexts
- `scoreToPercentage(score: number): number` — multiplies 0–1 score by 100

### 2.3 Create Mock Data

**File**: `src/data/mock-results.ts`

Create 8–12 mock `SearchResult` entries spanning multiple dates with varied scores (some high, some medium, some low) to exercise all color tiers and the "Most Likely" indicator.

**Deliverables**: Type-safe data contracts, shared utility functions, realistic mock data.

---

## Phase 3: Core Page Structure & State Machine

### 3.1 InvestigationPage Component

**File**: `src/components/investigation/InvestigationPage.tsx`

Implement the three-phase state machine:

```typescript
type Phase = "input" | "processing" | "results"

const [phase, setPhase] = useState<Phase>("input")
const [results, setResults] = useState<SearchResult[]>([])
```

Renders:
- `phase === "input"` → `<InputPhase onSubmit={handleSubmit} />`
- `phase === "processing"` → `<ProcessingPhase />`
- `phase === "results"` → `<ResultsPhase results={results} />`

### 3.2 Update App.tsx

Replace boilerplate content with `<InvestigationPage />`.

**Deliverables**: Page shell with phase transitions, clean App.tsx.

---

## Phase 4: Input Phase

### 4.1 InputPhase Component

**File**: `src/components/investigation/InputPhase.tsx`

Implementation:
- shadcn `Textarea` with placeholder: "Describe the item you think was stolen..."
- shadcn `Button` labeled "Investigate", disabled when textarea is empty
- Centered layout with `max-w-2xl mx-auto`
- On submit, pass the text value to the parent's `onSubmit` callback
- Detect "last movement" keywords in input text, pass as `includeMotion` flag

**Props**:
```typescript
interface InputPhaseProps {
  onSubmit: (query: string, includeMotion: boolean) => void
}
```

**Deliverables**: Functional input form with validation and motion detection.

---

## Phase 5: Processing Phase

### 5.1 ProcessingPhase Component

**File**: `src/components/investigation/ProcessingPhase.tsx`

Implementation:
- shadcn `Progress` component
- Simulated progress: increment from 0 to ~90 every 200ms using `setInterval`
- Status text below: "Analyzing observations..."
- Centered layout matching InputPhase positioning

### 5.2 useSearch Hook

**File**: `src/hooks/useSearch.ts`

Implementation:
- Accepts query string and includeMotion flag
- Returns `{ search, results, isLoading }`
- For now: simulates a 2–3 second delay, then returns mock data
- Later: replace with actual `fetch()` call to `/search` endpoint

### 5.3 Wire Into InvestigationPage

Update `handleSubmit`:
1. Set phase to `"processing"`
2. Call `useSearch.search(query, includeMotion)`
3. On completion → set results, set phase to `"results"`
4. Progress bar jumps to 100%, brief 300ms pause, then phase transition

**Deliverables**: Animated progress bar, mock search integration, smooth transitions.

---

## Phase 6: Results Phase — Layout

### 6.1 ResultsPhase Component

**File**: `src/components/investigation/ResultsPhase.tsx`

Implementation:
- Two-column responsive grid: `grid grid-cols-1 lg:grid-cols-2 gap-6`
- Left column: `<CalendarView results={results} />`
- Right column: `<DataTableView results={results} />`
- Optional header: "Investigation Results" or the original query text
- "New Search" button to reset back to input phase

**Props**:
```typescript
interface ResultsPhaseProps {
  results: SearchResult[]
  onReset: () => void
}
```

**Deliverables**: Responsive two-column results layout.

---

## Phase 7: Calendar View

### 7.1 CalendarView Component

**File**: `src/components/calendar/CalendarView.tsx`

Implementation steps:

1. **Group results by date**: Parse `metadata.timestamp`, group into `Map<string, SearchResult[]>` keyed by `YYYY-MM-DD`

2. **Compute per-date likelihood**: For each date, take the max score → convert to percentage → determine tier

3. **Find "Most Likely" date**: The date with the highest max percentage

4. **Render shadcn Calendar** with custom day rendering:
   - Use `modifiers` and `modifiersClassNames` or custom `components.Day` to apply background colors per date
   - Highlighted dates get their tier's `calendarBg` and `calendarText` classes
   - "Most Likely" date gets an additional star indicator or small badge

5. **Click handler**: On date click, open a shadcn `Popover`

### 7.2 DateDetailCard Component

**File**: `src/components/calendar/DateDetailCard.tsx`

Renders inside the Popover:
- shadcn `Card` with `CardContent`
- For each result on that date:
  - **Time**: formatted as `MM-DD-YY hh:mm A` using `date-fns format()`
  - **Link**: `<a href="#" className="text-blue-500 underline">View Details</a>` (placeholder)
- If multiple results, show as a list

**Deliverables**: Interactive calendar with color-coded dates, popover details, "Most Likely" indicator.

---

## Phase 8: Data Table View

### 8.1 Column Definitions

**File**: `src/components/data-table/columns.tsx`

Define 4 columns using TanStack `ColumnDef<SearchResult>[]`:

1. **Content** (`content`)
   - Header: "Content"
   - Cell: plain text from `row.original.content`

2. **Time** (`metadata.timestamp`)
   - Header: "Time"
   - Cell: `format(new Date(timestamp), "MM-dd-yy hh:mm a")`

3. **Likelihood** (`score`)
   - Header: "Likelihood"
   - Cell: `<LikelihoodBadge percentage={score * 100} />`

4. **Link**
   - Header: "Link"
   - Cell: `<a href="#">View</a>` (placeholder)

### 8.2 LikelihoodBadge Component

**File**: `src/components/data-table/LikelihoodBadge.tsx`

Implementation:
- Uses shadcn `Badge` component
- Applies `border-0` to remove border
- Applies tier-specific `badgeBg` and `badgeText` classes from `TIER_STYLES`
- Displays percentage text (e.g., "92%")

```typescript
interface LikelihoodBadgeProps {
  percentage: number
}
```

### 8.3 DataTableView Component

**File**: `src/components/data-table/DataTableView.tsx`

Implementation:
- Uses TanStack `useReactTable` with `getCoreRowModel`
- Renders shadcn `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell`
- Passes `columns` and `data` (transformed from SearchResult[])

**Deliverables**: Fully rendered data table with formatted columns and colored badges.

---

## Phase 9: Polish & Integration

### 9.1 Transitions

- Add smooth transitions between phases using CSS opacity/transform or a simple fade
- Progress bar completion animation before phase switch

### 9.2 Empty / Error States

- No results: display a message like "No matching observations found"
- API error: display error message with retry button

### 9.3 Responsive Testing

- Verify single-column stacking below `lg` breakpoint
- Confirm calendar and table are usable on smaller screens
- Test popover positioning on mobile

### 9.4 Cleanup

- Remove Vite boilerplate (counter component, default CSS, logos)
- Ensure no unused imports or dead code
- Run `npm run lint` and fix issues
- Run `npm run build` to verify production build

**Deliverables**: Polished, production-ready UI with error handling and responsive design.

---

## Phase Summary

| Phase | Description | Key Files | Est. Complexity |
|-------|------------|-----------|-----------------|
| 1 | Setup & dependencies | `vite.config.ts`, `index.css`, `components.json` | Simple |
| 2 | Types, utils, mock data | `types/`, `lib/`, `data/` | Simple |
| 3 | Page structure & state machine | `InvestigationPage.tsx`, `App.tsx` | Simple |
| 4 | Input phase | `InputPhase.tsx` | Simple |
| 5 | Processing phase | `ProcessingPhase.tsx`, `useSearch.ts` | Moderate |
| 6 | Results layout | `ResultsPhase.tsx` | Simple |
| 7 | Calendar view | `CalendarView.tsx`, `DateDetailCard.tsx` | Moderate |
| 8 | Data table view | `DataTableView.tsx`, `columns.tsx`, `LikelihoodBadge.tsx` | Moderate |
| 9 | Polish & integration | Various | Simple |

---

## Dependency Summary

### npm packages to install

```bash
# Tailwind
npm install tailwindcss @tailwindcss/vite

# shadcn init (interactive)
npx shadcn@latest init

# shadcn components
npx shadcn@latest add button textarea progress calendar card popover badge table

# Table engine
npm install @tanstack/react-table
```

### shadcn components used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | shadcn | Submit, navigation actions |
| `Textarea` | shadcn | Item description input |
| `Progress` | shadcn | Processing progress bar |
| `Calendar` | shadcn (wraps react-day-picker) | Date-based result visualization |
| `Card` / `CardContent` | shadcn | Date detail popover content |
| `Popover` / `PopoverContent` / `PopoverTrigger` | shadcn | Calendar date click overlay |
| `Badge` | shadcn | Likelihood percentage indicator |
| `Table` / `TableHeader` / etc. | shadcn | Data table structure |

### Peer dependencies (auto-installed by shadcn)

- `react-day-picker` (via Calendar)
- `date-fns` (via Calendar)
- `lucide-react` (icons)
- `class-variance-authority` (shadcn internals)
- `clsx` + `tailwind-merge` (via `cn()` utility)
