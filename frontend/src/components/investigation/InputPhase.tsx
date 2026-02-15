import { useState, useEffect } from "react"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"

interface InputPhaseProps {
  onSubmit: (query: string) => void
}

const PLACEHOLDER_WORDS = [
  "stolen",
  "lost",
  "missing",
  "misplaced",
  "taken",
  "moved",
  "left behind",
]

export function InputPhase({ onSubmit }: InputPhaseProps) {
  const [query, setQuery] = useState("")
  const [placeholderText, setPlaceholderText] = useState("")
  const [wordIndex, setWordIndex] = useState(0)
  const [isDeleting, setIsDeleting] = useState(false)
  const [typingSpeed, setTypingSpeed] = useState(150)

  useEffect(() => {
    const currentWord = PLACEHOLDER_WORDS[wordIndex]
    const baseText = "Describe the item you think was "

    const handleTyping = () => {
      if (!isDeleting) {
        // Typing forward
        const nextText = currentWord.substring(0, placeholderText.length - baseText.length + 1)
        setPlaceholderText(baseText + nextText)

        if (baseText + nextText === baseText + currentWord) {
          // Finished typing, pause then start deleting
          setTypingSpeed(2000)
          setIsDeleting(true)
        } else {
          setTypingSpeed(100)
        }
      } else {
        // Deleting
        const currentLength = placeholderText.length - baseText.length
        const nextText = currentWord.substring(0, currentLength - 1)
        setPlaceholderText(baseText + nextText)

        if (nextText === "") {
          // Finished deleting, move to next word
          setIsDeleting(false)
          setWordIndex((prev) => (prev + 1) % PLACEHOLDER_WORDS.length)
          setTypingSpeed(500)
        } else {
          setTypingSpeed(50)
        }
      }
    }

    const timer = setTimeout(handleTyping, typingSpeed)
    return () => clearTimeout(timer)
  }, [placeholderText, isDeleting, wordIndex, typingSpeed])

  function handleSubmit() {
    const trimmed = query.trim()
    if (!trimmed) return

    onSubmit(trimmed)
  }

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="relative max-w-2xl w-full mx-auto space-y-3 sm:space-y-4 pt-6 sm:pt-8 pb-20 sm:pb-28">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-2xl font-semibold tracking-tight">ctrl+f</h2>
          <h3 className="text-sm">Your surveillance, instantly searchable</h3>
        </div>
        <Textarea
          placeholder={placeholderText + "..."}
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
        <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-16 sm:top-24 z-0 opacity-90">
          <img
            src="/ctrlf_logo.png"
            alt="ctrl+f logo"
            className="h-128 max-h-[800px] w-auto object-contain"
          />
        </div>
      </div>
    </div>
  )
}
