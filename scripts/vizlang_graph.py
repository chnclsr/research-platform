"""Module-level handle on the pipeline graph, for VizLang Studio.

The VS Code extension loads a *file* -- `importlib.util.spec_from_file_location`, then
`inspect.getmembers` looking for a `StateGraph` or `CompiledStateGraph` bound to a
module-level name. `pipeline.py` satisfies neither half: it is a package module with
relative imports (loading it by path raises "attempted relative import with no known
parent package"), and its graph is built inside `ResearchPipeline._build_graph`, over
bound methods, so it only exists once a pipeline instance does.

Open *this* file in VizLang instead. Constructing `ResearchPipeline` costs no I/O -- the
session is unopened, the HTTP client unconnected, the registry and providers only built --
so the graph below is the real topology, not a hand-kept copy that could drift.

Note that Run and Step execute the real nodes: they hit the database, the connectors and
the LLM providers. For reading the shape of the graph, stay on the canvas.
"""

from __future__ import annotations

import httpx

from research_platform.config import get_settings
from research_platform.db import SessionLocal
from research_platform.pipeline import ResearchPipeline

graph = ResearchPipeline(get_settings(), SessionLocal(), httpx.AsyncClient()).graph


if __name__ == "__main__":
    drawable = graph.get_graph()
    print(f"{len(drawable.nodes)} nodes, {len(drawable.edges)} edges")
    for edge in drawable.edges:
        arrow = "-->" if not edge.conditional else "..>"
        print(f"  {edge.source} {arrow} {edge.target}{f' [{edge.data}]' if edge.data else ''}")
