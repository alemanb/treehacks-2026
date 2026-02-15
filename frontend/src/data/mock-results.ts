import type { SearchResult } from "@/types/search"

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
  {
    id: "doc_004",
    content: "Blue backpack seen on bench outside building A",
    score: 0.88,
    metadata: {
      object: "backpack",
      color: "blue",
      timestamp: "2026-02-10T11:42:00Z",
      motion_vector: [0.1, 0.0],
      device_id: "jetson_01",
    },
  },
  {
    id: "doc_005",
    content: "Unattended blue bag on library floor near exit",
    score: 0.71,
    metadata: {
      object: "bag",
      color: "blue",
      timestamp: "2026-02-13T08:20:00Z",
      motion_vector: null,
      device_id: "jetson_04",
    },
  },
  {
    id: "doc_006",
    content: "Individual picking up blue backpack from lost and found counter",
    score: 0.95,
    metadata: {
      object: "backpack",
      color: "blue",
      timestamp: "2026-02-13T16:05:00Z",
      motion_vector: [0.2, -0.3],
      device_id: "jetson_02",
    },
  },
  {
    id: "doc_007",
    content: "Blue item briefly visible in hallway camera feed",
    score: 0.55,
    metadata: {
      object: "unknown",
      color: "blue",
      timestamp: "2026-02-11T10:10:00Z",
      motion_vector: [0.9, 0.5],
      device_id: "jetson_05",
    },
  },
  {
    id: "doc_008",
    content: "Blue backpack placed under desk in study room",
    score: 0.83,
    metadata: {
      object: "backpack",
      color: "blue",
      timestamp: "2026-02-10T15:30:00Z",
      motion_vector: [0.0, -0.2],
      device_id: "jetson_03",
    },
  },
  {
    id: "doc_009",
    content: "Person with blue bag walking toward parking lot",
    score: 0.74,
    metadata: {
      object: "bag",
      color: "blue",
      timestamp: "2026-02-12T20:15:00Z",
      motion_vector: [0.6, 0.3],
      device_id: "jetson_06",
    },
  },
  {
    id: "doc_010",
    content: "Blue backpack detected near vending machines",
    score: 0.61,
    metadata: {
      object: "backpack",
      color: "blue",
      timestamp: "2026-02-14T07:45:00Z",
      motion_vector: [0.1, 0.1],
      device_id: "jetson_01",
    },
  },
]
