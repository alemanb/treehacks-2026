import { format } from "date-fns"
import type { ColumnDef } from "@tanstack/react-table"
import type { SearchResult } from "@/types/search"
import { scoreToPercentage } from "@/lib/likelihood"
import { LikelihoodBadge } from "./LikelihoodBadge"

export function createColumns(
  onViewImage: (frameUuid: string, timestamp: string) => void,
): ColumnDef<SearchResult>[] {
  return [
    {
      accessorKey: "content",
      header: "Content",
      cell: ({ row }) => (
        <p className="max-w-xl whitespace-normal break-words">
          {row.original.content}
        </p>
      ),
    },
    {
      accessorFn: (row) => row.metadata.timestamp,
      id: "time",
      header: "Time",
      cell: ({ row }) =>
        format(new Date(row.original.metadata.timestamp), "MM-dd-yy hh:mm a"),
    },
    {
      accessorKey: "score",
      header: "Likelihood",
      cell: ({ row }) => (
        <LikelihoodBadge percentage={scoreToPercentage(row.original.score)} />
      ),
    },
    {
      id: "link",
      header: "Link",
      cell: ({ row }) => {
        const frameUuid = row.original.metadata.frame_uuid
        const timestamp = row.original.metadata.timestamp
        return (
          <button
            type="button"
            onClick={() => onViewImage(frameUuid ?? "", timestamp)}
            className="text-blue-500 underline text-sm disabled:text-muted-foreground disabled:no-underline"
            disabled={!frameUuid}
          >
            View
          </button>
        )
      },
    },
  ]
}
