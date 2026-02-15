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

export function scoreToPercentage(score: number): number {
  return score * 100
}
