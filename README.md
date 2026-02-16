# Ctrl-F: Intelligent Video Observation & Search

**Built for TreeHacks 2026** — [Full Project Details on Devpost](https://devpost.com/software/ctrl-f-oc1yr9)

Ctrl-F is an end-to-end, edge-to-cloud intelligent surveillance system that transforms raw video feeds into a searchable, semantic database. Instead of just recording footage, it "understands" the scene locally and allows users to query history using natural language.

## 👥 The Team
* **Benjamin Aleman** ([alemanb](https://github.com/alemanb))
* **Abhinav Srivatsa** ([adsrivatsa](https://github.com/adsrivatsa))
* **Wei Jiang** ([mr2wei](https://github.com/mr2wei))
* **Preet Sojitra** ([preetsojitra2712](https://github.com/preetsojitra2712))

---

## 🚀 System Architecture

The system is split into a high-performance edge pipeline and a scalable cloud intelligence layer:

### 1. Edge Compute (NVIDIA Jetson Orin Nano Super)
Located in the `deepstream/` directory, the edge node handles the heavy lifting of computer vision:
* **Vision Pipeline:** DeepStream + YOLO for real-time object detection and multi-object tracking (MOT).
* **Local Reasoning:** NanoLLM / local VLM service provides semantic enrichment, turning raw bounding boxes into natural-language observations.
* **Frame Server:** A lightweight HTTP server serves captured frames directly from the edge for UI inspection.
* **Ingestion:** Asynchronously pushes enriched observations to the cloud backend.

### 2. Cloud Backend (Modal)
Located in the `backend/` directory, deployed as serverless functions on Modal:
* **FastAPI:** Provides `/ingest` and `/search` endpoints.
* **Intelligent Search:** A multi-agent RAG workflow involving query expansion and temporal reasoning.
* **Embedding & Storage:** Uses Jina embeddings to store data in Elasticsearch Cloud (Vector + Metadata store).

### 3. Frontend (React + TypeScript)
Located in the `frontend/` directory:
* **Investigation UI:** A modern dashboard for searching through historical observations.
* **Visualization:** Calendar and table views with direct deep-links to frame images hosted on the Jetson edge device.

## 🛠️ Tech Stack

- **Hardware:** NVIDIA Jetson Orin Nano Super
- **Edge AI:** NVIDIA DeepStream, NanoLLM, YOLO
- **Cloud/Infra:** Modal (Serverless), Elasticsearch Cloud
- **LLM/Embeddings:** OpenAI GPT-4o, Jina AI
- **Frontend:** React, TypeScript, Vite, Tailwind CSS

## 🔄 Data Flow

1. **Capture:** Webcam feed processed by DeepStream on the Jetson.
2. **Analyze:** VLM generates natural-language descriptions of tracked objects.
3. **Sync:** Observations are POSTed to the Modal backend.
4. **Index:** Modal embeds the text and indexes it into Elasticsearch.
5. **Query:** User enters a natural language query in the React UI.
6. **Retrieve:** Backend agents perform a vector search + re-ranking and return the most relevant video frames.