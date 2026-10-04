"""`profyle init`: Claude Code setup written into the project."""

import json
import sys
from pathlib import Path

from profyle import main as cli
from profyle.infrastructure.claude_code import MCP_PATH, SKILL_PATH, skill_text

REPO = Path(__file__).resolve().parents[2]


def init(project, monkeypatch, capsys) -> str:
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["profyle", "init"])
    cli.run()
    return capsys.readouterr().out


def mcp_config(project):
    return json.loads((project / MCP_PATH).read_text())


def test_init_writes_the_mcp_server_and_the_skill(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text("")

    out = init(tmp_path, monkeypatch, capsys)

    assert mcp_config(tmp_path) == {
        "mcpServers": {"profyle": {"command": "profyle", "args": ["mcp"]}}
    }
    assert (tmp_path / SKILL_PATH).read_text() == skill_text()
    assert out.count("created") == 2 and "profyle run" in out

    assert init(tmp_path, monkeypatch, capsys).count("already set up") == 2


def test_init_keeps_other_mcp_servers_and_runs_profyle_through_uv(tmp_path, monkeypatch, capsys):
    (tmp_path / "uv.lock").write_text("")
    other = {"command": "other-server"}
    (tmp_path / MCP_PATH).write_text(json.dumps({"mcpServers": {"other": other}}))

    assert "added profyle" in init(tmp_path, monkeypatch, capsys)
    assert mcp_config(tmp_path)["mcpServers"] == {
        "other": other,
        "profyle": {"command": "uv", "args": ["run", "profyle", "mcp"]},
    }


def test_init_updates_an_outdated_setup(tmp_path, monkeypatch, capsys):
    (tmp_path / "poetry.lock").write_text("")
    (tmp_path / MCP_PATH).write_text(json.dumps({"mcpServers": {"profyle": {"command": "x"}}}))
    (tmp_path / SKILL_PATH).parent.mkdir(parents=True)
    (tmp_path / SKILL_PATH).write_text("old skill")

    assert init(tmp_path, monkeypatch, capsys).count("updated") == 2
    assert mcp_config(tmp_path)["mcpServers"]["profyle"]["command"] == "poetry"
    assert (tmp_path / SKILL_PATH).read_text() == skill_text()


def test_init_leaves_an_invalid_mcp_json_alone(tmp_path, monkeypatch, capsys):
    (tmp_path / MCP_PATH).write_text("{not json")

    assert "not valid JSON" in init(tmp_path, monkeypatch, capsys)
    assert (tmp_path / MCP_PATH).read_text() == "{not json"


def test_the_plugin_ships_the_same_skill():
    # The Claude Code plugin (claude-plugin/) and `profyle init` must teach the same thing.
    plugin_skill = REPO / "claude-plugin" / "skills" / "fix-slow-endpoint" / "SKILL.md"
    assert plugin_skill.read_text() == skill_text()
