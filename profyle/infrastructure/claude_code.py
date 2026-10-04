"""`profyle init`: set up Claude Code for this project.

Writes two files that Claude Code reads when it opens the project, and that can be
committed so the whole team gets the same setup:

- `.mcp.json`: registers the `profyle` MCP server (other servers in it are kept);
- `.claude/skills/fix-slow-endpoint/SKILL.md`: how Claude fixes a slow endpoint with it.
"""

import json
import os
from importlib.resources import files

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
