# Clickstream Analytics UI

React + Vite dashboard for the clickstream analytics backend. It provides:

- Simulation controls for generating clickstream batches
- Real-time fraud detection metrics overview
- Recommendation accuracy visualisations
- Ray job orchestration helpers for full and incremental workflows

## Getting Started

```bash
cd services/clickstream/ui
npm install
npm run dev
```

The dev server proxies API calls to `http://localhost:8000` by default. Override with `VITE_API_BASE_URL` if needed.

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1 npm run dev
```

Build for production:

```bash
npm run build
```

Preview the production bundle locally:

```bash
npm run preview
```

