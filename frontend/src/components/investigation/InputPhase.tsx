import { useState } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"

interface InputPhaseProps {
  onSubmit: (query: string) => void
}

export function InputPhase({ onSubmit }: InputPhaseProps) {
  const [query, setQuery] = useState("")

  function handleSubmit() {
    const trimmed = query.trim()
    if (!trimmed) return

    onSubmit(trimmed)
  }

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="max-w-2xl w-full mx-auto space-y-4">
        <Textarea
          placeholder="Describe the item you think was stolen..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={4}
        />
        <Button
          className="w-full"
          disabled={query.trim().length === 0}
          onClick={handleSubmit}
        >
          Investigate
        </Button>
      </div>
    </div>
  )
}
