import asyncio
import io
import json
import os
import re as _re
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows to handle unicode characters like →
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import networkx as nx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth import create_token, verify_token, check_credentials
from backend.chat_db import init_db, create_session, save_message, update_session_title, get_sessions, get_session_messages, delete_session, create_user, user_exists
from backend.parsers.dispatcher import parse_repo, flatten_tree, build_node_index
from backend.graph.structural import extract_structural_edges
from backend.graph.boundary import detect_boundary_nodes, create_boundary_pairs
from backend.graph.llm_resolver import batch_annotate_nodes, traverse_and_annotate, resolve_boundary_edges
from backend.graph.knowledge_graph import build_knowledge_graph, save_graph, load_graph
from backend.query.engine import get_impact, narrate_impact, generate_migration, answer_query
from backend.query.severity import compute_severity_score
from backend.git.cloner import clone_repo
from backend.git.diff_reader import get_changed_files, get_changed_node_ids
from backend.query.vulnerability import extract_vulnerabilities

# ────────────────────────────────────────────────────────────
# App setup
# ────────────────────────────────────────────────────────────
app = FastAPI(title="DepGraph.ai API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Per-user graph state ──────────────────────────────────────────────────────
USER_GRAPHS:     dict[str, nx.DiGraph | None] = {}  # username -> graph
USER_FILE_NODES: dict[str, list]              = {}  # username -> parsed file nodes
USER_REPO_PATHS: dict[str, str]               = {}  # username -> abs repo path
USER_CHAINS:     dict[str, list]              = {}  # username -> variable chains
USER_ROUTES:     dict[str, list]              = {}  # username -> api routes

_GRAPHS_DIR    = Path(__file__).resolve().parent.parent
REPO_META_PATH = str(_GRAPHS_DIR / "depgraph_meta.json")


def _graph_path(username: str) -> str:
    safe = _re.sub(r'[^a-z0-9]', '_', username.lower())
    return str(_GRAPHS_DIR / f"depgraph_{safe}.json")


def _save_meta():
    try:
        data = {
            "users": {
                u: {"repo_path": USER_REPO_PATHS.get(u, ""), "graph_path": _graph_path(u)}
                for u in USER_GRAPHS
                if USER_GRAPHS.get(u) is not None
            }
        }
        with open(REPO_META_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"  [WARN] Could not save meta: {e}")


def _load_meta():
    try:
        if not os.path.exists(REPO_META_PATH):
            return
        with open(REPO_META_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if "users" in data:
            for u, info in data["users"].items():
                USER_REPO_PATHS[u] = info.get("repo_path", "")
        elif "repo_path" in data and data["repo_path"]:
            # Legacy single-repo format → assign to admin
            USER_REPO_PATHS["admin"] = data["repo_path"]
    except Exception as e:
        print(f"  [WARN] Could not load meta: {e}")


# Active WebSocket connection for progress streaming
_progress_ws: WebSocket | None = None

# Rolling in-memory log buffer (last 200 lines)
from collections import deque
import datetime
_LOG_BUFFER: deque = deque(maxlen=200)


def _log(msg: str, pct: int | None = None, is_error: bool = False):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    prefix = f"[{pct}%]" if pct is not None else "[---]"
    level = "ERROR" if is_error else "INFO"
    entry = {"ts": ts, "pct": pct, "level": level, "msg": msg}
    _LOG_BUFFER.append(entry)
    try:
        print(f"{ts} {prefix} {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"{ts} {prefix} {msg}".encode('utf-8', errors='replace').decode('ascii', errors='replace'), flush=True)


# ────────────────────────────────────────────────────────────
# Progress streaming helper
# ────────────────────────────────────────────────────────────
async def push_progress(msg: str, pct: int, is_error: bool = False):
    global _progress_ws
    _log(msg, pct, is_error)
    if _progress_ws:
        try:
            await _progress_ws.send_json({
                "type": "progress",
                "message": msg,
                "progress": pct / 100.0,
                "is_error": is_error
            })
        except Exception:
            pass


# ────────────────────────────────────────────────────────────
# Full analysis pipeline (runs in background, per-user)
# ────────────────────────────────────────────────────────────
async def run_full_analysis(repo_path: str, username: str):
    abs_path = str(Path(repo_path).resolve())
    USER_REPO_PATHS[username] = abs_path
    _save_meta()

    await push_progress("Initializing AST parsers (tree-sitter)...", 5)
    await push_progress("Scanning repository and parsing source files...", 10)
    file_nodes = parse_repo(repo_path)
    USER_FILE_NODES[username] = file_nodes
    all_nodes_flat = flatten_tree(file_nodes)
    await push_progress(f"Successfully parsed {len(all_nodes_flat)} symbols across SQL/Python/TS", 25)

    await push_progress("Mapping structural dependencies (ORM, Imports)...", 35)
    structural_G = nx.DiGraph()
    repo_path_obj = Path(repo_path)
    for n in all_nodes_flat:
        try:
            rel_file = str(Path(n.file).relative_to(repo_path_obj))
        except ValueError:
            rel_file = n.file
        structural_G.add_node(n.id, **{
            "name": n.name, "type": n.type, "language": n.language,
            "file": rel_file, "line_start": n.line_start, "line_end": n.line_end,
            "source_lines": (n.source_lines or "")[:200],
        })
    extract_structural_edges(file_nodes, structural_G)
    await push_progress(f"Structural mapping complete: {structural_G.number_of_edges()} edges found", 45)

    await push_progress("Boundary Zone Detector running (AXA Logic)...", 55)
    node_index = build_node_index(file_nodes)
    boundary_nodes = detect_boundary_nodes(file_nodes)
    pairs = create_boundary_pairs(boundary_nodes)
    await push_progress(f"Identified {len(pairs)} cross-language boundary pairs", 60)

    total = len(boundary_nodes)
    await push_progress(f"Semantic Annotation: batching {total} boundary nodes into 1 LLM call...", 70)
    try:
        await batch_annotate_nodes(boundary_nodes, node_index)
    except BaseException as e:
        print(f"  [WARN] Batch annotation failed: {e} — falling back to per-node annotation")
        for node in boundary_nodes:
            try:
                await traverse_and_annotate(node, node_index)
            except Exception as inner:
                print(f"  [WARN] Per-node annotation failed for {node.id}: {inner}")
    await push_progress(f"Semantic annotation complete ({total} nodes annotated in 1 LLM call)", 82)

    await push_progress(f"Resolving {len(pairs)} boundary pairs (batched LLM calls)...", 85)
    semantic_edges = await resolve_boundary_edges(pairs, node_index)

    await push_progress("Unifying structural and semantic graphs...", 90)
    try:
        G = build_knowledge_graph(file_nodes, structural_G, semantic_edges)
    except Exception as e:
        import traceback
        err_detail = traceback.format_exc()
        print(f"  [ERROR] build_knowledge_graph failed:\n{err_detail}")
        await push_progress(f"⚠ Graph build error: {e} — using structural graph only", 91, is_error=True)
        G = structural_G

    USER_GRAPHS[username] = G

    graph_file = _graph_path(username)
    try:
        await asyncio.to_thread(save_graph, G, graph_file)
    except Exception as e:
        print(f"  [WARN] save_graph failed: {e} — graph is still in memory")
        await push_progress(f"⚠ Graph save warning: {e}", 92, is_error=True)

    # ── Neo4j ──
    try:
        from backend.graph.neo4j_writer import KnowledgeGraphWriter
        writer = KnowledgeGraphWriter()
        if writer.enabled:
            lang_to_layer = {
                "sql": "database", "python": "backend",
                "typescript": "frontend", "react": "frontend", "javascript": "frontend",
            }
            nodes_meta = [
                {"id": nid, "name": data.get("name", ""), "language": data.get("language", ""),
                 "layer": lang_to_layer.get(data.get("language", ""), "backend"),
                 "file": data.get("file", ""), "line_start": data.get("line_start", 0),
                 "node_type": data.get("type", "")}
                for nid, data in G.nodes(data=True)
            ]
            edges_meta = [
                {"src": src, "tgt": tgt, "type": edata.get("type", "FLOWS_TO"),
                 "confidence": edata.get("confidence", 0.5), "inferred_by": edata.get("inferred_by", "ast"),
                 "break_risk": edata.get("break_risk", "none")}
                for src, tgt, edata in G.edges(data=True)
            ]
            await push_progress(f"Writing {len(nodes_meta)} nodes + {len(edges_meta)} edges to Neo4j...", 93)
            try:
                await asyncio.wait_for(asyncio.to_thread(writer.clear_graph), timeout=10.0)
                await asyncio.wait_for(asyncio.to_thread(writer.write_nodes, nodes_meta), timeout=20.0)
                await asyncio.wait_for(asyncio.to_thread(writer.write_edges, edges_meta), timeout=30.0)
                await asyncio.wait_for(asyncio.to_thread(writer.add_cross_language_edges), timeout=15.0)
                node_count = await asyncio.wait_for(asyncio.to_thread(writer.get_node_count), timeout=10.0)
                await push_progress(f"Neo4j: {node_count} nodes stored in Aura.", 94)
            except asyncio.TimeoutError:
                _log("  [Neo4j WARN] Write timed out — continuing without Aura persistence")
                await push_progress("Neo4j write timed out — continuing in NetworkX-only mode.", 94)
            finally:
                await asyncio.to_thread(writer.close)
        else:
            _log("  Neo4j not enabled — skipping Aura write")
    except Exception as e:
        _log(f"  [WARN] Neo4j write failed: {e}", is_error=True)

    # ── Post-analysis: detect variable chains + API routes ──
    await push_progress("Detecting cross-language variable chains (DB -> Backend -> Frontend)...", 95)
    try:
        from backend.graph.pipeline import detect_variable_chains, detect_api_routes
        import traceback as _tb

        try:
            chains_result = await asyncio.wait_for(
                asyncio.to_thread(detect_variable_chains, G, file_nodes), timeout=30.0
            )
            USER_CHAINS[username] = chains_result
            _log(f"  detect_variable_chains done: {len(chains_result)} chains")
        except asyncio.TimeoutError:
            _log("  detect_variable_chains timed out after 30s — skipping", is_error=True)
            USER_CHAINS[username] = []
        except Exception as e:
            _log(f"  detect_variable_chains error: {e}\n{_tb.format_exc()}", is_error=True)
            USER_CHAINS[username] = []

        try:
            routes_result = await asyncio.wait_for(
                asyncio.to_thread(detect_api_routes, G), timeout=30.0
            )
            USER_ROUTES[username] = routes_result
            _log(f"  detect_api_routes done: {len(routes_result)} routes")
        except asyncio.TimeoutError:
            _log("  detect_api_routes timed out after 30s — skipping", is_error=True)
            USER_ROUTES[username] = []
        except Exception as e:
            _log(f"  detect_api_routes error: {e}\n{_tb.format_exc()}", is_error=True)
            USER_ROUTES[username] = []

        await push_progress(
            f"Found {len(USER_CHAINS.get(username, []))} variable chains and {len(USER_ROUTES.get(username, []))} API routes.", 98
        )
    except Exception as e:
        _log(f"  [WARN] Chain/route detection failed: {e}", is_error=True)

    _save_meta()
    await push_progress("Analysis complete. Knowledge graph ready.", 100)


# ────────────────────────────────────────────────────────────
# Startup: pre-load graphs for all known users
# ────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    init_db()
    _load_meta()

    # Load per-user graphs
    for username in list(USER_REPO_PATHS.keys()):
        gp = _graph_path(username)
        if os.path.exists(gp):
            try:
                USER_GRAPHS[username] = load_graph(gp)
                USER_FILE_NODES.setdefault(username, [])
                USER_CHAINS.setdefault(username, [])
                USER_ROUTES.setdefault(username, [])
                print(f"  Loaded graph for '{username}': {USER_GRAPHS[username].number_of_nodes()} nodes")
            except Exception as e:
                print(f"  Could not load graph for '{username}': {e}")

    # Legacy: load old single-file graph for admin
    legacy = str(_GRAPHS_DIR / "depgraph_knowledge.json")
    if os.path.exists(legacy) and "admin" not in USER_GRAPHS:
        try:
            USER_GRAPHS["admin"] = load_graph(legacy)
            USER_FILE_NODES.setdefault("admin", [])
            USER_CHAINS.setdefault("admin", [])
            USER_ROUTES.setdefault("admin", [])
            USER_REPO_PATHS.setdefault("admin", "")
            print(f"  Loaded legacy graph (admin): {USER_GRAPHS['admin'].number_of_nodes()} nodes")
        except Exception as e:
            print(f"  Could not load legacy graph: {e}")


# ────────────────────────────────────────────────────────────
# REST Endpoints
# ────────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(repo_path: str, background_tasks: BackgroundTasks, username: str = Depends(verify_token)):
    """Trigger full repo analysis. repo_path can be a local path or a GitHub URL."""
    final_path = repo_path
    if repo_path.startswith("http") and "github.com" in repo_path:
        try:
            await push_progress("Cloning remote repository...", 2)
            final_path = clone_repo(repo_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to clone repository: {str(e)}")

    if not os.path.exists(final_path):
        raise HTTPException(status_code=404, detail="Repository path not found")

    background_tasks.add_task(run_full_analysis, final_path, username)
    return {"status": "started", "repo_path": final_path}


@app.get("/api/graph")
async def get_graph(username: str = Depends(verify_token)):
    """Full graph in React Flow format for the authenticated user."""
    G = USER_GRAPHS.get(username)
    if G is None:
        return {"nodes": [], "edges": []}

    nodes = []
    for node_id, data in G.nodes(data=True):
        try:
            desc_count = len(list(nx.descendants(G, node_id)))
            if desc_count > 0:
                impact_chain = []
                for desc in list(nx.descendants(G, node_id))[:20]:
                    try:
                        path = nx.shortest_path(G, node_id, desc)
                        pc = 1.0
                        for i in range(len(path) - 1):
                            e = G.edges[path[i], path[i + 1]]
                            pc *= e.get("confidence", 1.0)
                        risk_order = ["none", "low", "medium", "high"]
                        max_risk = max(
                            (G.edges[path[i], path[i + 1]].get("break_risk", "none")
                             for i in range(len(path) - 1)),
                            key=lambda x: risk_order.index(x) if x in risk_order else 0
                        )
                        impact_chain.append({"node": {"id": desc}, "distance": len(path) - 1,
                                             "path": path, "path_confidence": round(pc, 3),
                                             "max_break_risk": max_risk})
                    except Exception:
                        pass
                severity = compute_severity_score(G, node_id, impact_chain)
            else:
                severity = {"score": 0, "tier": "LOW", "color": "#22c55e", "breakdown": {}}
        except Exception:
            severity = {"score": 0, "tier": "LOW", "color": "#22c55e", "breakdown": {}}

        nodes.append({
            "id": node_id,
            **data,
            "severity": severity,
            "position": {"x": 0, "y": 0}
        })

    edges = []
    for src, tgt, data in G.edges(data=True):
        edges.append({"id": f"{src}->{tgt}", "source": src, "target": tgt, "data": data})

    return {"nodes": nodes, "edges": edges}


@app.get("/api/impact/{node_id:path}")
async def impact_endpoint(node_id: str, username: str = Depends(verify_token)):
    """Fast BFS impact analysis."""
    G = USER_GRAPHS.get(username)
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not built yet. Run /api/analyze first.")
    return get_impact(G, node_id)


@app.get("/api/narrate/{node_id:path}")
async def narrate_endpoint(node_id: str, username: str = Depends(verify_token)):
    """LLM-narrated explanation."""
    G = USER_GRAPHS.get(username)
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not built yet. Run /api/analyze first.")
    return {"narration": await narrate_impact(G, node_id)}


# ────────────────────────────────────────────────────────────
# Auth endpoints
# ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    if not check_credentials(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(req.username)
    return {"token": token, "username": req.username}


@app.get("/api/auth/me")
async def me(username: str = Depends(verify_token)):
    return {"username": username}


class RegisterRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    if len(req.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if user_exists(req.username.strip()):
        raise HTTPException(status_code=409, detail="Username already taken")
    ok = create_user(req.username.strip(), req.password)
    if not ok:
        raise HTTPException(status_code=409, detail="Username already taken")
    token = create_token(req.username.strip())
    return {"token": token, "username": req.username.strip()}


# ────────────────────────────────────────────────────────────
# User status
# ────────────────────────────────────────────────────────────

@app.get("/api/user/status")
async def user_status(username: str = Depends(verify_token)):
    """Return whether this user already has an analyzed graph."""
    G = USER_GRAPHS.get(username)
    repo_path = USER_REPO_PATHS.get(username, "")
    if G is None:
        return {"has_graph": False, "repo_path": "", "node_count": 0, "edge_count": 0, "repo_name": ""}
    return {
        "has_graph": True,
        "repo_path": repo_path,
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "repo_name": Path(repo_path).name if repo_path else "Unknown",
    }


# ────────────────────────────────────────────────────────────
# Chat with history persistence
# ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    selected_node_id: str = None
    history: list[dict] = []
    session_id: str = None


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, username: str = Depends(verify_token)):
    """Graph RAG chat. Grounds answer in user's subgraph context."""
    G = USER_GRAPHS.get(username)
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not built yet. Run /api/analyze first.")
    answer = await answer_query(G, req.question, req.selected_node_id, req.history)

    if req.session_id:
        try:
            save_message(req.session_id, "user", req.question)
            save_message(req.session_id, "assistant", answer)
            msgs = get_session_messages(req.session_id)
            if len(msgs) <= 2:
                title = req.question[:60] + ("..." if len(req.question) > 60 else "")
                update_session_title(req.session_id, title)
        except Exception as e:
            print(f"  [WARN] Failed to save chat message: {e}")

    return {"answer": answer}


# ── Session management ────────────────────────────────────────────────────────

@app.post("/api/chat/sessions")
async def create_chat_session(username: str = Depends(verify_token)):
    session = create_session(username)
    return session


@app.get("/api/chat/sessions")
async def list_chat_sessions(username: str = Depends(verify_token)):
    return {"sessions": get_sessions(username)}


@app.get("/api/chat/sessions/{session_id}")
async def get_chat_session(session_id: str, username: str = Depends(verify_token)):
    messages = get_session_messages(session_id)
    return {"session_id": session_id, "messages": messages}


@app.delete("/api/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str, username: str = Depends(verify_token)):
    delete_session(session_id)
    return {"status": "deleted"}


# ────────────────────────────────────────────────────────────
# Migration
# ────────────────────────────────────────────────────────────

class MigrateRequest(BaseModel):
    node_id: str
    new_name: str


@app.post("/api/migrate")
async def migrate_endpoint(req: MigrateRequest, username: str = Depends(verify_token)):
    G = USER_GRAPHS.get(username)
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not built yet. Run /api/analyze first.")
    return await generate_migration(G, req.node_id, req.new_name)


def _apply_changes_to_lines(lines: list[str], changes: list[dict]) -> list[str]:
    lines = list(lines)
    for change in changes:
        old_stripped = change.get("old_code", "").strip()
        new_stripped = change.get("new_code", "").strip()
        if not old_stripped:
            continue
        line_idx = change.get("line", 0) - 1

        replaced = False
        for offset in range(-2, 3):
            i = line_idx + offset
            if 0 <= i < len(lines) and old_stripped in lines[i]:
                indent = len(lines[i]) - len(lines[i].lstrip())
                lines[i] = " " * indent + new_stripped
                replaced = True
                break

        if not replaced:
            for i, ln in enumerate(lines):
                if old_stripped in ln:
                    indent = len(ln) - len(ln.lstrip())
                    lines[i] = " " * indent + new_stripped
                    replaced = True
                    break

    return lines


class MigrateApplyRequest(BaseModel):
    files: list[dict]


@app.post("/api/migrate/apply")
async def migrate_apply_endpoint(req: MigrateApplyRequest, username: str = Depends(verify_token)):
    repo_path = USER_REPO_PATHS.get(username, "")
    if not repo_path or not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail="No repo path available. Run analysis first.")

    by_file: dict[str, list[dict]] = {}
    for ch in req.files:
        by_file.setdefault(ch["file"], []).append(ch)

    results = []
    for rel_path, changes in by_file.items():
        abs_path = os.path.join(repo_path, rel_path)
        if not os.path.exists(abs_path):
            results.append({"file": rel_path, "status": "error", "detail": "File not found on disk"})
            continue
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().split("\n")
            lines = _apply_changes_to_lines(lines, changes)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            results.append({"file": rel_path, "status": "ok", "changes": len(changes)})
        except Exception as e:
            results.append({"file": rel_path, "status": "error", "detail": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    failed = len(results) - ok
    return {"applied": ok, "failed": failed, "results": results}


@app.post("/api/migrate/download")
async def migrate_download_endpoint(req: MigrateApplyRequest, username: str = Depends(verify_token)):
    import zipfile
    import io as _io
    from fastapi.responses import StreamingResponse

    repo_path = USER_REPO_PATHS.get(username, "")
    if not repo_path or not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail="No repo path available. Run analysis first.")

    by_file: dict[str, list[dict]] = {}
    for ch in req.files:
        by_file.setdefault(ch["file"], []).append(ch)

    buf = _io.BytesIO()
    files_added = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, changes in by_file.items():
            abs_path = os.path.join(repo_path, rel_path)
            if not os.path.exists(abs_path):
                continue
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().split("\n")
            lines = _apply_changes_to_lines(lines, changes)
            zf.writestr(rel_path, "\n".join(lines))
            files_added += 1

    if files_added == 0:
        raise HTTPException(status_code=400, detail="No matching files found in repo path.")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=migration.zip"},
    )


# ────────────────────────────────────────────────────────────
# Knowledge Graph enrichment endpoints
# ────────────────────────────────────────────────────────────

@app.get("/api/chains")
async def get_chains(username: str = Depends(verify_token)):
    chains = USER_CHAINS.get(username, [])
    if chains:
        return {"chains": chains, "count": len(chains)}

    G = USER_GRAPHS.get(username)
    if G is None:
        return {"chains": []}

    try:
        from backend.graph.pipeline import detect_variable_chains
        nodes = USER_FILE_NODES.get(username, [])
        chains = detect_variable_chains(G, nodes)
        USER_CHAINS[username] = chains
        return {"chains": chains, "count": len(chains)}
    except Exception as e:
        return {"chains": [], "error": str(e)}


@app.get("/api/routes")
async def get_routes(username: str = Depends(verify_token)):
    routes = USER_ROUTES.get(username, [])
    if routes:
        return {"routes": routes, "count": len(routes)}

    G = USER_GRAPHS.get(username)
    if G is None:
        return {"routes": []}

    try:
        from backend.graph.pipeline import detect_api_routes
        routes = detect_api_routes(G)
        USER_ROUTES[username] = routes
        return {"routes": routes, "count": len(routes)}
    except Exception as e:
        return {"routes": [], "error": str(e)}


@app.get("/api/sections")
async def get_sections(username: str = Depends(verify_token)):
    G = USER_GRAPHS.get(username)
    if G is None:
        return {"sections": {}, "cross_section_edges": 0}

    lang_to_layer = {
        "sql": "DATABASE", "python": "BACKEND",
        "typescript": "FRONTEND", "react": "FRONTEND", "javascript": "FRONTEND",
    }
    counts = {"DATABASE": 0, "BACKEND": 0, "FRONTEND": 0}
    for _, data in G.nodes(data=True):
        section = lang_to_layer.get(data.get("language", ""), "BACKEND")
        counts[section] += 1

    cross_edges = sum(
        1 for src, tgt, edata in G.edges(data=True)
        if lang_to_layer.get(G.nodes[src].get("language", ""), "?") !=
           lang_to_layer.get(G.nodes[tgt].get("language", ""), "?")
    )

    return {
        "sections": counts,
        "cross_section_edges": cross_edges,
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
    }


@app.get("/api/repo-path")
async def get_repo_path(username: str = Depends(verify_token)):
    repo_path = USER_REPO_PATHS.get(username, "")
    return {"repo_path": repo_path, "exists": bool(repo_path and os.path.isdir(repo_path))}


class SetRepoPathRequest(BaseModel):
    repo_path: str


@app.post("/api/repo-path")
async def set_repo_path(req: SetRepoPathRequest, username: str = Depends(verify_token)):
    path = str(Path(req.repo_path).resolve())
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
    USER_REPO_PATHS[username] = path
    _save_meta()
    return {"repo_path": path, "exists": True}


# ────────────────────────────────────────────────────────────
# Git / vulnerability / misc
# ────────────────────────────────────────────────────────────

@app.get("/api/git/impact")
async def git_impact_endpoint(repo_path: str = ".", mode: str = "staged", username: str = Depends(verify_token)):
    G = USER_GRAPHS.get(username)
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not built yet.")
    changed = get_changed_node_ids(G, repo_path, mode)
    results = []
    for n in changed:
        if n["node_id"] in G:
            results.append({"node": n, "impact": get_impact(G, n["node_id"])})
    return {"changed_nodes": results}


@app.get("/api/vulnerabilities")
async def vulnerabilities_endpoint(username: str = Depends(verify_token)):
    G = USER_GRAPHS.get(username)
    if G is None:
        return []
    try:
        return extract_vulnerabilities(G)
    except Exception as e:
        print(f"Vulnerability extraction failed: {str(e)}")
        return []


@app.get("/api/nodes")
async def list_nodes(language: str = None, type: str = None, username: str = Depends(verify_token)):
    G = USER_GRAPHS.get(username)
    if G is None:
        return {"nodes": []}
    nodes = []
    for node_id, data in G.nodes(data=True):
        if language and data.get("language") != language:
            continue
        if type and data.get("type") != type:
            continue
        nodes.append({"id": node_id, **data})
    return {"nodes": nodes}


@app.get("/api/health")
async def health():
    total_nodes = sum(g.number_of_nodes() for g in USER_GRAPHS.values() if g)
    total_edges = sum(g.number_of_edges() for g in USER_GRAPHS.values() if g)
    return {
        "status": "ok",
        "users_with_graphs": sum(1 for g in USER_GRAPHS.values() if g),
        "total_nodes": total_nodes,
        "total_edges": total_edges,
    }


@app.get("/api/logs")
async def get_logs(n: int = 100):
    logs = list(_LOG_BUFFER)[-n:]
    return {"count": len(logs), "logs": logs}


# ────────────────────────────────────────────────────────────
# WebSocket for progress streaming
# ────────────────────────────────────────────────────────────
@app.websocket("/ws/progress")
async def progress_ws(websocket: WebSocket):
    global _progress_ws
    await websocket.accept()
    _progress_ws = websocket
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _progress_ws = None


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
