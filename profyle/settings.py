import os

import viztracer


class Settings:
    app_name: str = "Profyle"
    project_dir: str = os.path.normpath(
        os.path.join(
            os.path.abspath(__file__),
            "..",
        )
    )

    def get_path(self, *args):
        return os.path.join(
            self.project_dir,
            *args
        )

    def get_db_path(self) -> str:
        # PROFYLE_DB lets each project (and its MCP server) keep its own traces.
        if os.getenv("PROFYLE_DB"):
            return os.environ["PROFYLE_DB"]
        # Set by the Claude Code plugin, whose MCP server runs from the plugin directory.
        project_dir = os.getenv("PROFYLE_PROJECT_DIR")
        if project_dir and os.path.exists(os.path.join(project_dir, "profile.db")):
            return os.path.join(project_dir, "profile.db")
        return self.get_path("profile.db")

    def get_viztracer_static_files(self):
        return os.path.normpath(os.path.join(
            os.path.abspath(viztracer.__file__),
            "..",
            "web_dist"
        ))


settings = Settings()
