#!/usr/bin/env python3
"""Merge per-agent *.kg.json fragments into one knowledge graph.

Usage: build_kg.py <workdir>            -> writes kg/graph.json + kg/GRAPH.md
       build_kg.py <workdir> q <term>   -> print nodes/edges/claims matching term
"""
import json, sys, glob, os, re
from collections import defaultdict

W = sys.argv[1]
frags = sorted(glob.glob(os.path.join(W, "*", "*.kg.json")))

# Optional alias map: <workdir>/kg/aliases.json {"dup:id": "canonical:id"}
AP = os.path.join(W, "kg", "aliases.json")
ALIAS = json.load(open(AP)) if os.path.exists(AP) else {}
A = lambda i: ALIAS.get(i, i)

nodes, edges, claims, sources, bad = {}, [], [], [], []
for f in frags:
    try:
        d = json.load(open(f))
    except Exception as e:
        bad.append(f"{f}: {e}")
        continue
    src = d.get("source", {})
    sid = src.get("id") or os.path.basename(f).split(".")[0]
    sources.append({**src, "id": sid, "file": os.path.relpath(f, W)})
    for n in d.get("nodes", []):
        nid = A(n.get("id"))
        if not nid:
            continue
        cur = nodes.setdefault(nid, {"id": nid, "type": n.get("type"), "label": n.get("label"),
                                     "props": {}, "sources": []})
        cur["props"].update(n.get("props") or {})
        if sid not in cur["sources"]:
            cur["sources"].append(sid)
    for e in d.get("edges", []):
        if e.get("src") and e.get("dst"):
            e = {**e, "src": A(e["src"]), "dst": A(e["dst"])}
            for k in ("src", "dst"):
                nodes.setdefault(e[k], {"id": e[k], "type": e[k].split(":")[0].title(),
                                        "label": e[k].split(":", 1)[-1], "props": {}, "sources": [sid]})
            edges.append({**e, "source": sid})
    for c in d.get("claims", []):
        claims.append({**c, "source": sid})

# claims corroborated by >1 independent fragment on the same URL host count as corroborated
graph = {"sources": sources, "nodes": list(nodes.values()), "edges": edges, "claims": claims,
         "stats": {"fragments": len(sources), "nodes": len(nodes), "edges": len(edges),
                   "claims": len(claims), "parse_errors": bad}}

if len(sys.argv) > 3 and sys.argv[2] == "q":
    t = sys.argv[3].lower()
    for n in nodes.values():
        if t in json.dumps(n).lower():
            print("NODE", n["id"], n["label"], n["sources"])
    for e in edges:
        if t in json.dumps(e).lower():
            print("EDGE", e["src"], e["rel"], e["dst"], "|", e.get("evidence", "")[:160], "|", e.get("url"))
    for c in claims:
        if t in json.dumps(c).lower():
            print("CLAIM", c["source"], c.get("confidence"), c["text"][:160], "|", c.get("url"))
    sys.exit(0)

os.makedirs(os.path.join(W, "kg"), exist_ok=True)
json.dump(graph, open(os.path.join(W, "kg", "graph.json"), "w"), indent=1)

by_type = defaultdict(list)
for n in nodes.values():
    by_type[n["type"] or "?"].append(n)
deg = defaultdict(int)
for e in edges:
    deg[e["src"]] += 1
    deg[e["dst"]] += 1
conf = defaultdict(int)
for c in claims:
    conf[c.get("confidence", "?")] += 1

L = ["# Research knowledge graph", "",
     f"Fragments: {len(sources)} · nodes: {len(nodes)} · edges: {len(edges)} · claims: {len(claims)}",
     f"Claim confidence: {dict(conf)}", f"Parse errors: {bad or 'none'}", "", "## Sources", ""]
for s in sources:
    L.append(f"- **{s['id']}** ({s.get('kind')}, fetched={s.get('fetched')}): {s.get('title')} — {s.get('url')}")
L += ["", "## Hub nodes (top 25 by degree)", ""]
for nid, d in sorted(deg.items(), key=lambda x: -x[1])[:25]:
    L.append(f"- `{nid}` — {d} edges — {nodes[nid]['label']} (from {', '.join(nodes[nid]['sources'])})")
L += ["", "## Nodes by type", ""]
for t in sorted(by_type):
    L.append(f"### {t} ({len(by_type[t])})")
    for n in sorted(by_type[t], key=lambda x: x["id"]):
        L.append(f"- `{n['id']}` {n['label']} [{', '.join(n['sources'])}]")
    L.append("")
L += ["## Edges", ""]
for e in edges:
    L.append(f"- `{e['src']}` —{e['rel']}→ `{e['dst']}` [{e['source']}] {e.get('url','')}")
open(os.path.join(W, "kg", "GRAPH.md"), "w").write("\n".join(L) + "\n")
print(json.dumps(graph["stats"], indent=1))
