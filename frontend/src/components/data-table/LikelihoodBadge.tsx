import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { TIER_STYLES, getLikelihoodTier } from "@/lib/likelihood"

interface LikelihoodBadgeProps {
  percentage: number
}

export function LikelihoodBadge({ percentage }: LikelihoodBadgeProps) {
  const tier = getLikelihoodTier(percentage)
  const styles = TIER_STYLES[tier]

  return (
    <Badge
      variant="secondary"
      className={cn("border-0", styles.badgeBg, styles.badgeText)}
    >
      {Math.round(percentage)}%
    </Badge>
  )
}
