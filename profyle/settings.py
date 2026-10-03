import os

import viztracer

DATA_DIR = ".profyle"
PROJECT_MARKERS = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "manage.py",
    "requirements.txt",
    "Pipfile",
    ".git",
)


def find_project_root(start: str) -> str:
    """Closest directory from `start` upwards with a project marker (else `start`)."""
    current = os.path.abspath(start)
    while True:
        if any(os.path.exists(os.path.join(current, marker)) for marker in PROJECT_MARKERS):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start)
        current = parent


class Settings:
    app_name: str = "Profyle"
    project_dir: str = os.path.normpath(
        os.path.join(
            os.path.abspath(__file__),
            "..",
        )
    )

    def get_path(self, *args):
        return os.path.join(self.project_dir, *args)

    def get_db_path(self) -> str:
        """Where traces live. The app, `profyle start` and the MCP server must agree.

        1. PROFYLE_DB, if set.
        2. <project>/.profyle/profile.db, where <project> is PROFYLE_PROJECT_DIR (set by
           the Claude Code plugin, whose MCP server runs from the plugin directory) or the
           closest parent of the working directory that looks like a project root.
        """
        if os.getenv("PROFYLE_DB"):
            return os.environ["PROFYLE_DB"]
        project_dir = os.getenv("PROFYLE_PROJECT_DIR") or find_project_root(os.getcwd())
        return os.path.join(project_dir, DATA_DIR, "profile.db")

    def get_legacy_db_path(self) -> str:
        # Before 0.4 traces were stored inside the installed package.
        return self.get_path("profile.db")

    def get_viztracer_static_files(self):
        return os.path.normpath(os.path.join(os.path.abspath(viztracer.__file__), "..", "web_dist"))


settings = Settings()
