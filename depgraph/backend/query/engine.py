import re
import networkx as nx
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from backend.query.severity import compute_severity_score


def get_impact(G: nx.DiGraph, node_id: str) -> dict:
    """
    Fast mode: BFS traversal — no LLM, instant response.
    Returns all downstream descendants with path confidence and max break risk.
    """
    if node_id not in G:
        return {"error": "node not found", "node_id": node_id}

    descendants = list(nx.descendants(G, node_id))
    chain = []

    for desc in descendants:
        try:
            path = nx.shortest_path(G, node_id, desc)
            edges_on_path = [G.edges[path[i], path[i + 1]] for i in range(len(path) - 1)]

            path_confidence = 1.0
            for e in edges_on_path:
                path_confidence *= e.get("confidence", 1.0)

            risk_order = ["none", "low", "medium", "high"]
            max_risk = max(
                (e.get("break_risk", "none") for e in edges_on_path),
                key=lambda x: risk_order.index(x) if x in risk_order else 0
            )

            node_data = dict(G.nodes[desc])
            node_data["id"] = desc
            chain.append({
                "node": node_data,
                "distance": len(path) - 1,
                "path": path,
                "path_confidence": round(path_confidence, 3),
                "max_break_risk": max_risk
            })
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

    severity = compute_severity_score(G, node_id, chain)

    return {
        "source": dict(G.nodes[node_id]),
        "affected_count": len(descendants),
        "languages_affected": list(set(
            G.nodes[d].get("language", "?") for d in descendants
        )),
        "chain": sorted(chain, key=lambda x: x["distance"]),
        "has_critical_breaks": any(c["max_break_risk"] == "high" for c in chain),
        "severity": severity
    }


def _extract_context_nodes(G: nx.DiGraph, question: str, selected_node_id: str | None) -> set[str]:
    """
    Find graph nodes relevant to the question via keyword matching, then expand 1-2 hops.
    Falls back to top-degree nodes per language if nothing matches.
    """
    q = question.lower()

    # Tokenise question into words (strip punctuation)
    q_tokens = set(re.split(r'[\s\.,;:()\[\]{}\'"!?/\\]+', q)) - {"", "the", "a", "an", "in",
        "of", "for", "to", "is", "are", "was", "what", "how", "why", "where", "which",
        "this", "that", "with", "from", "does", "do", "can", "my", "its", "their"}

    # Score every node by how many question tokens it matches
    scored: list[tuple[float, str]] = []
    for nid, data in G.nodes(data=True):
        score = 0.0
        name = data.get("name", "").lower()
        file_parts = set(re.split(r'[/\\.]', data.get("file", "").lower()))
        summary = data.get("summary", "").lower()
        source = (data.get("source_lines") or "").lower()

        for tok in q_tokens:
            if len(tok) < 3:
                continue
            if tok == name:
                score += 3.0
            elif tok in name:
                score += 1.5
            elif tok in file_parts:
                score += 1.0
            elif tok in summary:
                score += 0.5
            elif tok in source:
                score += 0.3

        if score > 0:
            scored.append((score, nid))

    # Take top keyword-matched nodes
    scored.sort(reverse=True)
    seed_nodes: set[str] = {nid for _, nid in scored[:15]}

    # Always include selected node
    if selected_node_id and selected_node_id in G:
        seed_nodes.add(selected_node_id)

    # Expand seeds 1-hop in both directions
    expanded: set[str] = set(seed_nodes)
    for nid in seed_nodes:
        expanded.update(G.predecessors(nid))
        expanded.update(G.successors(nid))

    # If no keyword match, fall back to top-N per language for breadth
    if not seed_nodes:
        nodes_by_lang: dict[str, list] = {}
        for nid, data in G.nodes(data=True):
            lang = data.get("language", "other")
            nodes_by_lang.setdefault(lang, []).append((G.degree(nid), nid))
        for lang_nodes in nodes_by_lang.values():
            lang_nodes.sort(reverse=True)
            for _, nid in lang_nodes[:12]:
                expanded.add(nid)

    # Cap at 60 to keep context manageable
    if len(expanded) > 60:
        # Priority: selected > seeds > rest by degree
        priority = list(seed_nodes)
        if selected_node_id:
            priority = [selected_node_id] + [n for n in priority if n != selected_node_id]
        rest = sorted(expanded - set(priority), key=lambda n: G.degree(n), reverse=True)
        expanded = set(priority[:30]) | set(rest[:30])

    return expanded


def _build_rag_context(G: nx.DiGraph, context_nodes: set[str]) -> str:
    """
    Build a structured text block describing the relevant subgraph.
    Includes source code snippets and cross-language edge data.
    """
    LANG_ABBR = {"sql": "SQL", "python": "PY", "typescript": "TS",
                 "javascript": "JS", "react": "RX"}

    # Group by layer for readability
    LAYER_ORDER = ["sql", "python", "typescript", "javascript", "react"]
    by_lang: dict[str, list] = {}
    for nid in context_nodes:
        if nid not in G:
            continue
        lang = G.nodes[nid].get("language", "other")
        by_lang.setdefault(lang, []).append(nid)

    sections: list[str] = []

    for lang in LAYER_ORDER + [l for l in by_lang if l not in LAYER_ORDER]:
        nodes = by_lang.get(lang, [])
        if not nodes:
            continue
        abbr = LANG_ABBR.get(lang, lang.upper()[:2])
        lang_lines: list[str] = []
        for nid in nodes:
            data = G.nodes[nid]
            name = data.get("name", nid.split("::")[-1])
            ntype = data.get("type", "?")
            file_ = data.get("file", "?")
            line = data.get("line_start", "?")
            summary = data.get("summary", "")
            source = (data.get("source_lines") or "")[:250].strip()
            sensitivity = data.get("sensitivity", "")
            data_in = data.get("data_in", [])
            data_out = data.get("data_out", [])

            entry = f"  [{abbr}] {ntype} `{name}` — {file_}:{line}"
            if summary:
                entry += f"\n    summary: {summary}"
            if sensitivity and sensitivity not in ("none", ""):
                entry += f"\n    sensitivity: {sensitivity}"
            if data_in:
                entry += f"\n    data_in: {data_in}"
            if data_out:
                entry += f"\n    data_out: {data_out}"
            if source:
                # indent source lines for readability
                indented = "\n".join("    | " + l for l in source.split("\n")[:12])
                entry += f"\n    code:\n{indented}"
            lang_lines.append(entry)

        if lang_lines:
            sections.append(f"--- {lang.upper()} LAYER ---\n" + "\n\n".join(lang_lines))

    # Cross-language edges within context
    edge_lines: list[str] = []
    for src, tgt, edata in G.edges(data=True):
        if src not in context_nodes or tgt not in context_nodes:
            continue
        src_name = G.nodes[src].get("name", src.split("::")[-1])
        tgt_name = G.nodes[tgt].get("name", tgt.split("::")[-1])
        src_lang = LANG_ABBR.get(G.nodes[src].get("language", ""), "?")
        tgt_lang = LANG_ABBR.get(G.nodes[tgt].get("language", ""), "?")
        etype = edata.get("type", "FLOWS_TO")
        conf = edata.get("confidence", 1.0)
        risk = edata.get("break_risk", "none")
        reason = edata.get("break_reason", "")
        line = f"  [{src_lang}]{src_name} -[{etype} conf={conf:.2f} risk={risk}]-> [{tgt_lang}]{tgt_name}"
        if reason:
            line += f"  # {reason[:80]}"
        edge_lines.append(line)

    result = "\n\n".join(sections)
    if edge_lines:
        result += "\n\n--- RELATIONSHIPS ---\n" + "\n".join(edge_lines[:60])

    return result


async def answer_query(
    G: nx.DiGraph,
    question: str,
    selected_node_id: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """
    Graph RAG chat.
    1. Extract relevant subgraph from keyword matching + selected node
    2. Build structured context with source code + edges
    3. Call LLM with conversation history
    """
    import os
    from openai import AsyncOpenAI
    from dotenv import load_dotenv
    load_dotenv()

    llm_client = AsyncOpenAI(
        base_url=os.getenv("FEATHERLESS_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.getenv("FEATHERLESS_API_KEY", ""),
        timeout=35.0,
        max_retries=0,
    )
    model = os.getenv("FEATHERLESS_MODEL", "meta-llama/llama-3.1-8b-instruct")

    context_nodes = _extract_context_nodes(G, question, selected_node_id)
    rag_context = _build_rag_context(G, context_nodes)

    all_languages = set(nx.get_node_attributes(G, "language").values())
    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()

    selected_info = ""
    if selected_node_id and selected_node_id in G:
        d = G.nodes[selected_node_id]
        selected_info = (
            f"\nCURRENTLY SELECTED NODE: `{d.get('name', selected_node_id)}` "
            f"({d.get('type','?')} in {d.get('language','?')}, {d.get('file','?')}:{d.get('line_start','?')})"
        )

    system = f"""You are DepGraph.ai, an expert code analyst for a polyglot codebase.

CODEBASE: {total_nodes} symbols, {total_edges} dependency edges, languages: {', '.join(sorted(all_languages))}.{selected_info}

RELEVANT GRAPH CONTEXT ({len(context_nodes)} nodes):
{rag_context}

INSTRUCTIONS:
- Answer ONLY from the graph context above. Do not hallucinate file names or function names not shown.
- Reference specific files, line numbers, and symbol names when you can.
- For data flow questions: trace the DB -> Python -> TypeScript/React path across the relationship edges.
- For "what breaks" questions: focus on edges where break_risk=high.
- Format code references as `backtick quoted` and file paths as file.ext:line.
- Be concise and direct. Use bullet points for lists of items."""

    messages: list[dict] = [{"role": "system", "content": system}]

    # Include up to 6 previous turns (3 exchanges) for multi-turn context
    if history:
        messages.extend(history[-6:])

    messages.append({"role": "user", "content": question})

    try:
        response = await llm_client.chat.completions.create(
            model=model,
            max_tokens=600,
            temperature=0.2,
            messages=messages,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Query unavailable: {e}"


async def narrate_impact(G: nx.DiGraph, node_id: str) -> str:
    """LLM-narrated explanation of the impact chain."""
    import json
    import os
    from openai import AsyncOpenAI
    from dotenv import load_dotenv
    load_dotenv()

    llm_client = AsyncOpenAI(
        base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
        api_key=os.getenv("FEATHERLESS_API_KEY", ""),
        timeout=60.0,
        max_retries=0,
    )
    model = os.getenv("FEATHERLESS_MODEL", "meta-llama/llama-3.1-8b-instruct")

    impact = get_impact(G, node_id)
    subgraph_data = {
        "source_node": impact["source"],
        "chain": impact["chain"][:10],
        "severity": impact["severity"]
    }

    prompt = f"""A developer is considering modifying this symbol in their polyglot codebase.

Source node: {json.dumps(impact['source'], indent=2)}
Severity: {impact['severity']['tier']} (ImpactScore: {impact['severity']['score']})

Full downstream dependency chain (across all language layers):
{json.dumps(subgraph_data['chain'], indent=2)}

Write a developer-friendly explanation covering:
1. What this field is, what data it holds, and its sensitivity level
2. The complete data flow journey across each language layer (include exact transformations)
3. Exactly what will break and why if this field is renamed or deleted (file + line)
4. Correct order of changes for a safe rename

Use specific file names, line numbers, and field names. Be direct and actionable."""

    try:
        response = await llm_client.chat.completions.create(
            model=model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Narration unavailable: {e}"


async def generate_migration(G: nx.DiGraph, node_id: str, new_name: str) -> dict:
    """Generate a complete cross-language migration plan for renaming a field."""
    import json
    import os
    from openai import AsyncOpenAI
    from dotenv import load_dotenv
    load_dotenv()

    llm_client = AsyncOpenAI(
        base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
        api_key=os.getenv("FEATHERLESS_API_KEY", ""),
        timeout=60.0,
        max_retries=0,
    )
    model = os.getenv("FEATHERLESS_MODEL", "meta-llama/llama-3.1-8b-instruct")

    impact = get_impact(G, node_id)
    source_node = impact["source"]

    prompt = f"""Generate a complete, safe migration plan for renaming a field in a polyglot codebase.

Field being renamed: '{source_node.get('name', node_id)}' to '{new_name}'
Source: {source_node.get('file', '?')} line {source_node.get('line_start', '?')}
Language: {source_node.get('language', '?')}

All affected nodes across all language layers:
{json.dumps(impact['chain'], indent=2)}

Account for ALL transformations:
- If SQL: use ALTER TABLE RENAME COLUMN
- If Python ORM: update Column() argument or attribute name
- If Pydantic: update field name (keep camelCase alias if present)
- If TypeScript interface: update field name preserving camelCase
- If React: update prop access and destructuring

Return ONLY this JSON (no markdown):
{{
  "summary": "X changes across Y files in Z languages",
  "safe_order": ["apply SQL first, then Python ORM, then schema, then TypeScript, then React"],
  "files": [
    {{
      "file": "filename",
      "language": "sql|python|typescript|react",
      "line": 12,
      "old_code": "exact current line",
      "new_code": "exact replacement line",
      "change_type": "rename|update_reference|update_serializer|update_interface"
    }}
  ]
}}"""

    try:
        response = await llm_client.chat.completions.create(
            model=model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.choices[0].message.content.strip()
        if "```" in text:
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"summary": "Parse error — LLM returned invalid JSON", "files": [], "safe_order": []}
    except Exception as e:
        return {"summary": f"Migration unavailable: {e}", "files": [], "safe_order": []}
