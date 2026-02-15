import * as React from "react"
import { createContext, useContext, useMemo, useState } from "react"
import { format } from "date-fns"
import type { DayButton } from "react-day-picker"

import { Calendar, CalendarDayButton } from "@/components/ui/calendar"
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import {
  TIER_STYLES,
  getLikelihoodTier,
  scoreToPercentage,
} from "@/lib/likelihood"
import type { SearchResult } from "@/types/search"
import { DateDetailCard } from "./DateDetailCard"

// --- Data types ---

interface DateInfo {
  results: SearchResult[]
  maxPercentage: number
  tier: "high" | "medium" | "low"
}

interface CalendarData {
  dateMap: Map<string, DateInfo>
  mostLikelyDateKey: string | null
}

// --- Context for passing data to custom DayButton ---

const CalendarDataContext = createContext<CalendarData>({
  dateMap: new Map(),
  mostLikelyDateKey: null,
})

// --- Helpers ---

function toDateKey(date: Date): string {
  return format(date, "yyyy-MM-dd")
}

function processResults(results: SearchResult[]) {
  const dateMap = new Map<string, DateInfo>()

  for (const result of results) {
    const dateKey = toDateKey(new Date(result.metadata.timestamp))
    const percentage = scoreToPercentage(result.score)
    const existing = dateMap.get(dateKey)

    if (existing) {
      existing.results.push(result)
      if (percentage > existing.maxPercentage) {
        existing.maxPercentage = percentage
        existing.tier = getLikelihoodTier(percentage)
      }
    } else {
      dateMap.set(dateKey, {
        results: [result],
        maxPercentage: percentage,
        tier: getLikelihoodTier(percentage),
      })
    }
  }

  let mostLikelyDateKey: string | null = null
  let highest = 0
  for (const [key, info] of dateMap) {
    if (info.maxPercentage > highest) {
      highest = info.maxPercentage
      mostLikelyDateKey = key
    }
  }

  return { dateMap, mostLikelyDateKey }
}

// --- Custom DayButton with tier styling ---

function HighlightedDayButton({
  day,
  modifiers,
  className,
  children,
  ...rest
}: React.ComponentProps<typeof DayButton>) {
  const { dateMap, mostLikelyDateKey } = useContext(CalendarDataContext)
  const dateKey = toDateKey(day.date)
  const info = dateMap.get(dateKey)

  if (!info) {
    return (
      <CalendarDayButton
        day={day}
        modifiers={modifiers}
        className={className}
        {...rest}
      >
        {children}
      </CalendarDayButton>
    )
  }

  const styles = TIER_STYLES[info.tier]
  const isMostLikely = dateKey === mostLikelyDateKey

  return (
    <CalendarDayButton
      day={day}
      modifiers={modifiers}
      className={cn(
        styles.calendarBg,
        styles.calendarText,
        "rounded-md transition-colors",
        isMostLikely && "animate-pulse",
        className,
      )}
      {...rest}
    >
      {children}
    </CalendarDayButton>
  )
}

// --- CalendarView ---

interface CalendarViewProps {
  results: SearchResult[]
}

export function CalendarView({ results }: CalendarViewProps) {
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  const { dateMap, mostLikelyDateKey } = useMemo(
    () => processResults(results),
    [results],
  )

  const calendarData = useMemo(
    () => ({ dateMap, mostLikelyDateKey }),
    [dateMap, mostLikelyDateKey],
  )

  const selectedDateInfo = selectedDate ? dateMap.get(selectedDate) : null

  function handleDayClick(date: Date) {
    const key = toDateKey(date)
    if (dateMap.has(key)) {
      setSelectedDate((prev) => (prev === key ? null : key))
    } else {
      setSelectedDate(null)
    }
  }

  return (
    <Popover
      open={selectedDateInfo !== null}
      onOpenChange={(open) => {
        if (!open) setSelectedDate(null)
      }}
    >
      <PopoverAnchor asChild>
        <div className="inline-block w-fit rounded-lg border bg-card p-4 shadow-sm">
          <CalendarDataContext.Provider value={calendarData}>
            <Calendar
              components={{ DayButton: HighlightedDayButton }}
              onDayClick={handleDayClick}
            />
          </CalendarDataContext.Provider>
        </div>
      </PopoverAnchor>

      {selectedDateInfo && selectedDate && (
        <PopoverContent className="w-80">
          <DateDetailCard
            date={selectedDate}
            results={selectedDateInfo.results}
          />
        </PopoverContent>
      )}
    </Popover>
  )
}
