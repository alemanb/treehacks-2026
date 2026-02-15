import { format } from "date-fns"
import type { SearchResult } from "@/types/search"

interface DateDetailCardProps {
  date: string
  results: SearchResult[]
}

export function DateDetailCard({ date, results }: DateDetailCardProps) {
  const formattedDate = format(new Date(date), "MMM d, yyyy")

  return (
    <div className="space-y-3">
      <p className="font-medium text-sm">{formattedDate}</p>
      <ul className="space-y-2">
        {results.map((result) => (
          <li key={result.id} className="text-sm space-y-0.5">
            <p className="text-muted-foreground">
              {format(
                new Date(result.metadata.timestamp),
                "MM-dd-yy hh:mm a",
              )}
            </p>
            <p>{result.content}</p>
            <a href="#" className="text-blue-500 underline text-xs">
              View Details
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
