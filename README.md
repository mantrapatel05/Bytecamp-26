# DepGraph.ai

**Cross-language dependency intelligence for polyglot codebases.**  
Catch silent breaks across SQL → Python → TypeScript → React — *before* they reach production.

---

## What is this?

Most dev tools understand one language. Your codebase speaks four.

When you rename a database column, your ORM model breaks. The Pydantic serializer breaks. The TypeScript interface breaks. The React component breaks. None of these failures happen in the same file, or even in the same language — and no linter, type-checker, or IDE is watching across that full chain.

**DepGraph.ai is.** It builds a unified knowledge graph of your entire polyglot stack, maps every cross-language dependency edge, scores the blast radius of any change, and generates a safe, ordered migration plan with exact before/after diffs.

---

## Demo

1. Clone the repo and start the backend
2. Enter `./sample_repo` in the path input and click **Analyze**
3. Watch the 6-layer pipeline run live in the terminal
4. Click `user_email` in the left sidebar
5. See: 4 languages affected, severity = **CRITICAL**
6. Open the **Migrate** tab → type `email` → get a complete diff plan across every file

---

## Features

### 🗺️ 2.5D Knowledge Graph
WebGL-powered, force-directed graph built on `react-force-graph-3d` and Three.js. The engine is fully 3D (real sphere meshes, camera orbit, WebGL rendering) but a Z-axis flattening force keeps nodes in a layered 2D plane — giving you a clean, readable layout while retaining depth, glow effects, and smooth camera controls. Nodes are color-coded by layer (amber = SQL, violet = Python, sky = TypeScript/React). Cross-language edges are rendered with distinct colors per relationship type — `MAPS_TO`, `SERIALIZES_TO`, `BREAKS_IF_RENAMED`, and more.

### ⚡ ImpactScore Engine
Every node gets a severity score using the formula:

```
ImpactScore = weighted_dependents × api_multiplier × coverage_multiplier
```

Tiers: `CRITICAL ≥ 8` · `HIGH ≥ 4` · `MEDIUM ≥ 1` · `LOW < 1`

Click any node to see its animated severity gauge, full downstream impact chain, per-hop confidence scores, and whether each dependent node will **BREAK** on rename.

### 🤖 RAG Chat
Ask questions about your codebase in plain English. The chat engine retrieves relevant subgraph context, builds a focused prompt, and returns precise answers grounded in your actual code — with file names, line numbers, and relationship edges cited. Sessions are persisted and resumable.

```
You:   "What breaks if I delete the user_email field?"
Bot:   "user_email maps to User.email in models.py:34 via ORM_MAP (confidence 1.0),
        which serializes to UserSerializer.email in serializers.py:18, which exposes
        as userEmail in /api/users (TypeScript type UserResponse:12), which is
        destructured in UserProfile.tsx:47 and SettingsView.tsx:93. All four will break."
```

### 🔁 Cross-Language Migration Planner
Select a node, type a new name, and get a complete rename plan in seconds:
- Exact file paths and line numbers
- Old code vs. new code diff for every affected file
- Safe execution order: SQL → Python → TypeScript → React
- **Apply directly** to your local repo (in-place patch) or **download** as a `.zip`

The planner uses a deterministic AST-based diff first, then optionally enriches with an LLM pass to catch casing rules (`snake_case` → `camelCase` at language boundaries).

### 🔗 Variable Chain Tracing
See the full data journey of any symbol: from the database column it originates from, through every ORM field, serializer, API route, TypeScript type, and React prop it flows through — with transformation annotations at each layer boundary.

### 🛡️ Git Pre-Commit Hook
Block commits that introduce silent cross-language breaks:

```bash
python scripts/install_hooks.py /path/to/your/repo
```

On every `git commit`, the hook checks staged files against the knowledge graph. If any change carries a `break_risk = HIGH` or `CRITICAL` edge, the commit is blocked with an explanation. Override with `--no-verify`.

### 🔐 Multi-User Auth
JWT-based authentication with per-user knowledge graphs. Each user gets their own isolated graph stored on disk — analyze multiple repos simultaneously with different accounts.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Source Code                          │
│          .sql   .py   .ts   .tsx   .js   .jsx               │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
          ┌─────────────────────────┐
          │   Layer 1: AST Parser   │  tree-sitter + sqlglot
          │  sql_parser.py          │  Extracts CodeNode trees
          │  python_parser.py       │  from every file in repo
          │  typescript_parser.py   │
          └────────────┬────────────┘
                       │
                       ▼
          ┌─────────────────────────┐
          │  Layer 2: Structural    │  ORM_MAP, CONVENTION_MAP
          │  Graph Builder          │  IMPORTS, CALLS edges
          │  graph/builder.py       │  via name-match + AST
          └────────────┬────────────┘
                       │
                       ▼
          ┌─────────────────────────┐
          │  Layer 3: Boundary      │  AXA Language Detector
          │  Zone Detector          │  (ASE 2024 technique)
          │  graph/boundary.py      │  Finds cross-lang nodes
          └────────────┬────────────┘
                       │
                       ▼
          ┌─────────────────────────┐
          │  Layer 4: LLM Semantic  │  GLM-4.7 via Featherless
          │  Resolution             │  Batch-annotates boundary
          │  graph/llm_resolver.py  │  nodes in ≤4 API calls
          └────────────┬────────────┘
                       │
                       ▼
          ┌─────────────────────────┐
          │  Layer 5: Knowledge     │  NetworkX DiGraph
          │  Graph Assembly         │  Persisted as JSON
          │  graph/pipeline.py      │  Per-user on disk
          └────────────┬────────────┘
                       │
                       ▼
          ┌─────────────────────────┐
          │  Layer 6: Query Engine  │  Fast BFS impact query
          │  query/engine.py        │  LLM narration
          │                         │  Migration planner
          └─────────────────────────┘
                       │
                       ▼
          ┌─────────────────────────┐
          │  FastAPI Backend        │  REST + WebSocket
          │  backend/main.py        │  JWT auth
          │  :8000                  │  Per-user graph store
          └────────────┬────────────┘
                       │
                       ▼
          ┌─────────────────────────┐
          │  React Frontend         │  Vite + TypeScript
          │  :5173                  │  Framer Motion
          │                         │  react-force-graph-3d
          └─────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Featherless.ai](https://featherless.ai) API key (free tier available) — used for LLM annotation and RAG chat. The tool degrades gracefully to structural-only mode if no key is set.

### 1. Clone & Install Backend

```bash
git clone https://github.com/your-username/depgraph.git
cd depgraph

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Create .env in the project root
cp .env.example .env
```

Edit `.env`:

```env
FEATHERLESS_API_KEY=your_key_here
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1
FEATHERLESS_MODEL=zai-org/GLM-4.7

# JWT secret — change this in production
JWT_SECRET=change_me_in_production
```

### 3. Start the Backend

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

The API will be live at `http://localhost:8000`. Open `http://localhost:8000/docs` for the auto-generated Swagger UI.

### 4. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### 5. Analyze a Repo

1. Register an account on the login screen
2. Paste a **local path** (e.g. `/home/you/projects/myapp`) or a **GitHub URL** (e.g. `https://github.com/org/repo`) into the input
3. Click **Analyze** and watch the 6-layer pipeline run in real-time
4. Explore the 2.5D graph, click nodes, chat with the codebase, and generate migration plans

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `FEATHERLESS_API_KEY` | No* | — | API key for LLM features. Without this, the tool runs in structural-only mode (no RAG chat, no LLM migration enrichment). |
| `FEATHERLESS_BASE_URL` | No | `https://api.featherless.ai/v1` | LLM API base. Any OpenAI-compatible endpoint works (OpenRouter, local vLLM, etc). |
| `FEATHERLESS_MODEL` | No | `zai-org/GLM-4.7` | Model to use for annotation and chat. |
| `JWT_SECRET` | Yes | — | Secret for signing JWT tokens. Use a strong random string in production. |
| `VITE_API_BASE_URL` | No | `http://localhost:8000` | Frontend env var. Set to your deployed backend URL for production builds. |

---

## API Reference

All endpoints require a `Bearer <token>` header except `/api/auth/login` and `/api/auth/register`.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create a new user account |
| `POST` | `/api/auth/login` | Login and receive a JWT token |
| `GET` | `/api/auth/me` | Get current user info |
| `POST` | `/api/analyze?repo_path=` | Trigger full repo analysis. Accepts local path or GitHub URL. Returns immediately; streams progress via WebSocket. |
| `GET` | `/api/graph` | Full knowledge graph in React Flow node/edge format |
| `GET` | `/api/impact/{node_id}` | Fast BFS impact analysis for a node (no LLM, instant) |
| `GET` | `/api/narrate/{node_id}` | LLM-narrated plain-English explanation of the impact chain |
| `POST` | `/api/chat` | RAG chat — ask a question about the graph, optionally anchored to a node |
| `POST` | `/api/migrate` | Generate a cross-language rename migration plan |
| `POST` | `/api/migrate/apply` | Apply migration patches directly to the local repo |
| `POST` | `/api/migrate/download` | Download migration patches as a `.zip` |
| `GET` | `/api/chains` | List all traced variable chains across language layers |
| `GET` | `/api/routes` | List all detected API routes with their boundary metadata |
| `GET` | `/api/sections` | Node counts per layer (DATABASE / BACKEND / FRONTEND) and cross-section edge count |
| `GET` | `/api/git/impact?mode=staged` | Map staged git changes to affected graph nodes |
| `GET` | `/api/repo-path` | Get the current repo path for the authenticated user |
| `POST` | `/api/repo-path` | Set or override the repo path |
| `GET` | `/api/user/status` | Check if a graph exists for the current user |
| `GET` | `/api/health` | Health check |
| `WS` | `/ws/progress` | WebSocket stream for real-time analysis progress (percent + log lines) |

---

## Project Structure

```
depgraph/
├── backend/
│   ├── main.py                  # FastAPI app — all endpoints, user state, analysis runner
│   ├── core/
│   │   └── models.py            # CodeNode dataclass (the AST node representation)
│   ├── parsers/
│   │   ├── dispatcher.py        # parse_repo(), routes files to correct parser
│   │   ├── sql_parser.py        # sqlglot-based SQL schema parser
│   │   ├── python_parser.py     # tree-sitter Python parser
│   │   └── typescript_parser.py # tree-sitter TypeScript/TSX parser
│   ├── graph/
│   │   ├── builder.py           # Constructs DiGraph from parsed file nodes
│   │   ├── boundary.py          # Detects cross-language boundary nodes
│   │   ├── llm_resolver.py      # Batched LLM semantic annotation
│   │   ├── pipeline.py          # Orchestrates all 6 layers; chain/route detection
│   │   ├── schema.py            # Knowledge graph vocabulary (node/edge types)
│   │   └── serializer.py        # save_graph() / load_graph() (NetworkX ↔ JSON)
│   ├── query/
│   │   └── engine.py            # get_impact(), generate_migration(), graph_rag_chat()
│   ├── git/
│   │   ├── cloner.py            # GitHub repo cloner with SHA-based cache
│   │   ├── diff_reader.py       # Reads staged/PR/last-commit diffs
│   │   └── pre_commit_hook.py   # Hook entrypoint — blocks high-risk commits
│   └── auth/
│       └── db.py                # SQLite user store, bcrypt passwords, JWT issuance
│
├── scripts/
│   └── install_hooks.py         # Installs pre-commit hook into any target git repo
│
├── sample_repo/                 # Demo polyglot project (SQL + Python + TypeScript)
│   ├── schema.sql
│   └── services/
│       ├── auth_service.py
│       ├── models.py
│       └── schemas.py
│
├── frontend/
│   └── src/
│       ├── api/client.ts        # Typed API client, axios interceptors, all request functions
│       ├── context/
│       │   ├── AppContext.tsx   # Global state: graph, impact, chains, WebSocket stream
│       │   └── AuthContext.tsx  # JWT auth state, login/logout
│       ├── pages/
│       │   ├── LoginPage.tsx    # Auth screen
│       │   ├── SetupPage.tsx    # Repo connect screen
│       │   ├── AnalyzingPage.tsx# 6-layer pipeline progress UI
│       │   └── MainApp.tsx      # Root layout
│       └── components/app/
│           ├── TopBar.tsx
│           ├── LeftSidebar.tsx  # File tree + node list + search
│           ├── GraphCanvas.tsx  # 2.5D WebGL graph (Three.js + react-force-graph-3d, Z-flattened)
│           ├── RightPanel.tsx   # Impact / Chat / Migrate / Chains tabs
│           ├── Terminal.tsx     # Collapsible log terminal
│           ├── VariableChain.tsx
│           └── tabs/
│               ├── ImpactTab.tsx    # Severity gauge + dependency chain timeline
│               ├── ChatTab.tsx      # RAG chat with markdown renderer + session history
│               └── MigrateTab.tsx   # Rename planner + apply/download
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## How the 6-Layer Pipeline Works

### Layer 1 — AST Foundation
Every `.sql`, `.py`, `.ts`, `.tsx`, `.js`, and `.jsx` file in the repo is parsed into a tree of `CodeNode` objects. SQL uses `sqlglot`; Python and TypeScript use `tree-sitter` grammars. Each node captures: name, type, language, file, line range, source lines, and parent/child relationships.

### Layer 2 — Structural Graph
The `GraphBuilder` walks all parsed nodes and creates directed edges based on deterministic rules:
- `ORM_MAP` — Python field name matches SQL column name in snake_case
- `CONVENTION_MAP` — camelCase TypeScript prop matches snake_case Python field
- `IMPORTS` — static import analysis from AST
- `CALLS` — function call detection within the same language

### Layer 3 — Boundary Zone Detector
Each node is tested against a set of regex patterns (`BOUNDARY_PATTERNS`) tuned per language — Pydantic `BaseModel`, FastAPI route decorators, DRF `Serializer`, TypeScript `interface *DTO`, Zod schemas, Mongoose models, React prop access patterns. Nodes that match are flagged as `is_boundary = True`. These become the candidates for LLM enrichment in the next layer.

### Layer 4 — LLM Semantic Resolution
Boundary nodes are batched (all at once, ≤4 total API calls) and sent to GLM-4.7 via Featherless. The LLM annotates:
- Semantic relationship type (`MAPS_TO`, `SERIALIZES_TO`, `FLOWS_TO`, etc.)
- Transformation type (`snake_to_camel`, `direct`, `alias`)
- Break risk per edge (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`)
- Confidence score (0.0–1.0)

If the LLM API is unavailable, the pipeline continues with structural-only edges — no crash, no silent failure.

### Layer 5 — Knowledge Graph Assembly
All nodes and edges are merged into a `NetworkX DiGraph` and persisted to disk as `depgraph_<username>.json`. The graph also detects variable chains (multi-hop data flows with named transformations) and API routes (FastAPI/Express endpoints with their input/output types).

### Layer 6 — Query Engine
Three query modes on the frozen graph:
- **Fast BFS** (`get_impact`) — instant, no LLM, pure graph traversal. Returns the full downstream chain with per-hop confidence and break risk.
- **LLM Narration** (`narrate_impact`) — feeds the BFS result into a prompt and returns a developer-readable plain-English explanation.
- **Graph RAG Chat** (`graph_rag_chat`) — retrieves a relevant subgraph neighborhood for the user's question, builds a grounded system prompt, and runs a conversational Q&A loop with session history.

---

## ImpactScore Formula

```
ImpactScore = Σ(dependents × edge_weight) × api_multiplier × coverage_multiplier
```

Where:
- `edge_weight` — 3.0 for `BREAKS_IF_RENAMED`, 2.5 for `MAPS_TO`/`SERIALIZES_TO`, 1.5 for `FLOWS_TO`, 1.0 for `IMPORTS`
- `api_multiplier` — 2.0 if the node is exposed via a public API route, else 1.0
- `coverage_multiplier` — 1.5 if the affected nodes have no test coverage signals, else 1.0

Tier thresholds: **CRITICAL ≥ 8 · HIGH ≥ 4 · MEDIUM ≥ 1 · LOW < 1**

---

## Git Hook

```bash
# Install the hook into any git repo
python scripts/install_hooks.py /absolute/path/to/your/repo

# The hook runs automatically on every commit
git add models.py
git commit -m "rename user_email to email"
# → DepGraph.ai: checking cross-language impact...
# → BLOCKED: user_email has CRITICAL cross-language break risk
# → Affected: auth_service.py:34, serializers.py:18, UserProfile.tsx:47
# → Use git commit --no-verify to skip this check.
```

The hook uses `git diff --cached` to get staged files, maps them to graph nodes, and traverses downstream edges. Only commits with `break_risk = HIGH` or `CRITICAL` are blocked — low/medium risk changes pass through with a warning.

---

## Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn — async REST + WebSocket API
- [NetworkX](https://networkx.org/) — directed graph engine
- [tree-sitter](https://tree-sitter.github.io/) — language-agnostic AST parsing (Python, TypeScript, JavaScript)
- [sqlglot](https://sqlglot.com/) — SQL dialect-agnostic schema parsing
- [OpenAI SDK](https://github.com/openai/openai-python) (pointed at Featherless) — LLM annotation and RAG
- [GitPython](https://gitpython.readthedocs.io/) — repo cloning and git operations
- [PyJWT](https://pyjwt.readthedocs.io/) + [passlib](https://passlib.readthedocs.io/) — auth

**Frontend**
- [React 18](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/) + [Vite](https://vitejs.dev/)
- [react-force-graph-3d](https://github.com/vasturiano/react-force-graph) + [Three.js](https://threejs.org/) — 2.5D WebGL knowledge graph (3D engine, Z-axis flattened for layered layout)
- [Framer Motion](https://www.framer.com/motion/) — animations
- [shadcn/ui](https://ui.shadcn.com/) + [Radix UI](https://www.radix-ui.com/) — component library
- [TanStack Query](https://tanstack.com/query) — server state
- [Axios](https://axios-http.com/) — HTTP client with auth interceptors
- [Tailwind CSS](https://tailwindcss.com/) — styling

---

## Known Limitations

- **Analysis time scales with repo size.** Large repos (>500 files) may take 2–5 minutes for the full LLM annotation pass. The structural-only mode (no API key) is always fast.
- **LLM accuracy varies.** The deterministic AST graph is always correct; LLM-enriched edges are best-effort. Confidence scores are shown on every edge.
- **Apply / in-place patching** requires that the analyzed repo path is set and accessible on the same machine as the backend. Remote-only usage should use the download-as-zip workflow instead.
- **Python 2 syntax** is not supported. tree-sitter Python grammar targets Python 3.
- **Monorepos with complex build systems** (nx, Turborepo workspaces) may need the repo root to be pointed at the relevant sub-package rather than the workspace root.

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to discuss what you'd like to change.

```bash
# Run backend tests
pytest

# Run frontend tests
cd frontend && npm test

# Lint
cd frontend && npm run lint
```

---

## License

MIT
