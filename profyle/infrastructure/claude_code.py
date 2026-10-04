"""`profyle init` and `profyle uninstall`: set up Claude Code for this project, and undo it.

`init` writes two files that Claude Code reads when it opens the project, and that can be
committed so the whole team gets the same setup:

- `.mcp.json`: registers the `profyle` MCP server (other servers in it are kept);
- `.claude/skills/fix-slow-endpoint/SKILL.md`: how Claude fixes a slow endpoint with it.

`uninstall` removes them, and the traces in `.profyle/`.
"""

import json
import os
import shutil
from importlib.resources import files

from profyle.settings import DATA_DIR

SKILL_PATH = os.path.join(".claude", "skills", "fix-slow-endpoint", "SKILL.md")
MCP_PATH = ".mcp.json"


def skill_text() -> str:
    return files("profyle.claude").joinpath("SKILL.md").read_text(encoding="utf-8")


def mcp_server(project_dir: str) -> dict:
    """How Claude Code starts `profyle mcp` in this project's environment."""
    if os.path.exists(os.path.join(project_dir, "uv.lock")):
        return {"command": "uv", "args": ["run", "profyle", "mcp"]}
    if os.path.exists(os.path.join(project_dir, "poetry.lock")):
        return {"command": "poetry", "args": ["run", "profyle", "mcp"]}
    return {"command": "profyle", "args": ["mcp"]}


def init_project(project_dir: str) -> list[tuple[str, str]]:
    """Write the setup; returns (path, what happened) for each file."""
    return [
        (MCP_PATH, _register_mcp_server(project_dir)),
        (SKILL_PATH, _write(os.path.join(project_dir, SKILL_PATH), skill_text())),
    ]


def _register_mcp_server(project_dir: str) -> str:
    path = os.path.join(project_dir, MCP_PATH)
    config: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                config = json.load(f)
        except ValueError:
            return "not changed: it is not valid JSON, add the profyle server by hand"
    servers = config.setdefault("mcpServers", {})
    server = mcp_server(project_dir)
    if servers.get("profyle") == server:
        return "already set up"
    status = "updated" if "profyle" in servers else ("added profyle" if servers else "created")
    servers["profyle"] = server
    _write(path, json.dumps(config, indent=2) + "\n")
    return status


def _write(path: str, text: str) -> str:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return "already set up"
        status = "updated"
    else:
        status = "created"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return status


def uninstall_project(project_dir: str, remove_traces: bool) -> list[tuple[str, str]]:
    """Remove what `init` and tracing added; returns (path, what happened) for each."""
    removed = [
        (MCP_PATH, _unregister_mcp_server(project_dir)),
        (os.path.dirname(SKILL_PATH), _remove_skill(project_dir)),
    ]
    traces = os.path.join(project_dir, DATA_DIR)
    if not os.path.isdir(traces):
        removed.append((DATA_DIR, "not found"))
    elif remove_traces:
        shutil.rmtree(traces)
        removed.append((DATA_DIR, "removed"))
    else:
        removed.append((DATA_DIR, "kept"))
    return removed


def _unregister_mcp_server(project_dir: str) -> str:
    path = os.path.join(project_dir, MCP_PATH)
    if not os.path.exists(path):
        return "not found"
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except ValueError:
        return "not changed: it is not valid JSON, remove the profyle server by hand"
    servers = config.get("mcpServers", {})
    if "profyle" not in servers:
        return "no profyle server in it"
    del servers["profyle"]
    if not servers and set(config) == {"mcpServers"}:
        os.remove(path)
        return "removed"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(config, indent=2) + "\n")
    return "profyle server removed, other servers kept"


def _remove_skill(project_dir: str) -> str:
    skill_dir = os.path.join(project_dir, os.path.dirname(SKILL_PATH))
    if not os.path.isdir(skill_dir):
        return "not found"
    shutil.rmtree(skill_dir)
    # Leave no empty .claude/skills or .claude behind.
    for directory in (os.path.dirname(skill_dir), os.path.join(project_dir, ".claude")):
        if os.path.isdir(directory) and not os.listdir(directory):
            os.rmdir(directory)
    return "removed"
