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


def uninstall(project, monkeypatch, capsys, *flags) -> str:
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["profyle", "uninstall", *flags])
    cli.run()
    return capsys.readouterr().out


def project_with_profyle(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text("")
    init(tmp_path, monkeypatch, capsys)
    (tmp_path / ".profyle").mkdir()
    (tmp_path / ".profyle" / "profile.db").write_text("traces")
    return tmp_path


def test_uninstall_removes_everything(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PROFYLE_DB", raising=False)
    project = project_with_profyle(tmp_path, monkeypatch, capsys)

    out = uninstall(project, monkeypatch, capsys, "--yes")

    assert sorted(p.name for p in project.iterdir()) == ["pyproject.toml"]
    assert out.count("removed") == 3 and "pip uninstall profyle" in out


def test_uninstall_keeps_what_profyle_did_not_add(tmp_path, monkeypatch, capsys):
    project = project_with_profyle(tmp_path, monkeypatch, capsys)
    config = mcp_config(project)
    config["mcpServers"]["other"] = {"command": "other-server"}
    (project / MCP_PATH).write_text(json.dumps(config))
    (project / ".claude" / "settings.json").write_text("{}")

    out = uninstall(project, monkeypatch, capsys, "--keep-traces")

    assert mcp_config(project) == {"mcpServers": {"other": {"command": "other-server"}}}
    assert "other servers kept" in out
    assert (project / ".claude" / "settings.json").exists()
    assert not (project / ".claude" / "skills").exists()
    assert (project / ".profyle" / "profile.db").exists()


def test_uninstall_asks_before_deleting_traces(tmp_path, monkeypatch, capsys):
    project = project_with_profyle(tmp_path, monkeypatch, capsys)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)

    monkeypatch.setattr("builtins.input", lambda question: "n")
    uninstall(project, monkeypatch, capsys)
    assert (project / ".profyle").exists()

    monkeypatch.setattr("builtins.input", lambda question: "y")
    uninstall(project, monkeypatch, capsys)
    assert not (project / ".profyle").exists()


def test_uninstall_without_a_terminal_keeps_traces(tmp_path, monkeypatch, capsys):
    project = project_with_profyle(tmp_path, monkeypatch, capsys)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)

    assert "pass --yes to delete them" in uninstall(project, monkeypatch, capsys)
    assert (project / ".profyle").exists()


def test_uninstall_when_nothing_is_installed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PROFYLE_DB", str(tmp_path / "elsewhere.db"))

    out = uninstall(tmp_path, monkeypatch, capsys)

    assert out.count("not found") == 3
    assert "PROFYLE_DB points to" in out


def test_uninstall_leaves_unexpected_mcp_json_alone(tmp_path, monkeypatch, capsys):
    (tmp_path / MCP_PATH).write_text("{not json")
    assert "not valid JSON" in uninstall(tmp_path, monkeypatch, capsys)

    other = {"mcpServers": {"other": {}}}
    (tmp_path / MCP_PATH).write_text(json.dumps(other))
    assert "no profyle server in it" in uninstall(tmp_path, monkeypatch, capsys)
    assert mcp_config(tmp_path) == other

    extra = {"mcpServers": {"profyle": {}}, "comment": "kept"}
    (tmp_path / MCP_PATH).write_text(json.dumps(extra))
    uninstall(tmp_path, monkeypatch, capsys)
    assert mcp_config(tmp_path) == {"mcpServers": {}, "comment": "kept"}
