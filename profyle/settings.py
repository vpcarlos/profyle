import os

from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = 'Profyle'
    project_dir: str = os.path.normpath(
        os.path.join(
            os.path.abspath(__file__),
            '..',
        )
    )

    def get_path(self, *args):
        return os.path.join(
            self.project_dir,
            *args
        )


settings = Settings()
