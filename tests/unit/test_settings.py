import os

from profyle.infrastructure.sqlite3.get_connection import ensure_data_dir
from profyle.settings import find_project_root, settings


def test_db_lives_in_the_project_root_found_from_a_subdirectory(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("")
    subdir = tmp_path / "src" / "app"
    subdir.mkdir(parents=True)
    monkeypatch.delenv("PROFYLE_DB", raising=False)
    monkeypatch.delenv("PROFYLE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(subdir)

    assert find_project_root(str(subdir)) == str(tmp_path)
    assert settings.get_db_path() == str(tmp_path / ".profyle" / "profile.db")


def test_explicit_settings_win(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFYLE_PROJECT_DIR", str(tmp_path))
    assert settings.get_db_path() == str(tmp_path / ".profyle" / "profile.db")

    monkeypatch.setenv("PROFYLE_DB", "/tmp/custom.db")
    assert settings.get_db_path() == "/tmp/custom.db"


def test_data_dir_is_ignored_by_git(tmp_path):
    data_dir = tmp_path / ".profyle"

    ensure_data_dir(str(data_dir))

    assert os.path.isdir(data_dir)
    assert (data_dir / ".gitignore").read_text().splitlines()[-1] == "*"


def test_project_root_falls_back_to_the_start_directory(tmp_path, monkeypatch):
    import profyle.settings as settings_module

    monkeypatch.setattr(settings_module, "PROJECT_MARKERS", ("no-such-marker-xyz",))

    assert find_project_root(str(tmp_path)) == str(tmp_path)


def test_custom_database_directory_gets_no_gitignore(tmp_path):
    ensure_data_dir(str(tmp_path / "traces"))

    assert (tmp_path / "traces").is_dir()
    assert not (tmp_path / "traces" / ".gitignore").exists()
