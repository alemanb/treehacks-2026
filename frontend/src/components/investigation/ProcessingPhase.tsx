import { useEffect, useState } from "react"
import { Progress } from "@/components/ui/progress"

interface ProcessingPhaseProps {
  isComplete: boolean
  onTransitionEnd: () => void
}

export function ProcessingPhase({
  isComplete,
  onTransitionEnd,
}: ProcessingPhaseProps) {
  const [progress, setProgress] = useState(0)

  // Simulate progress from 0 → ~90 while loading
  useEffect(() => {
    if (isComplete) return

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 90) return prev
        return prev + Math.random() * 8 + 2 // increment 2–10 per tick
      })
    }, 200)

    return () => clearInterval(interval)
  }, [isComplete])

  // Delay transition after completion
  useEffect(() => {
    if (!isComplete) return

    const timeout = setTimeout(onTransitionEnd, 300)
    return () => clearTimeout(timeout)
  }, [isComplete, onTransitionEnd])

  const displayProgress = isComplete ? 100 : progress

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="max-w-2xl w-full mx-auto space-y-4">
        <Progress value={displayProgress} />
        <p className="text-center text-sm text-muted-foreground">
          Analyzing observations...
        </p>
      </div>
    </div>
  )
}
