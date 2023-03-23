import os

from pydantic import BaseSettings
import viztracer


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

    def get_viztracer_static_files(self):
        return os.path.normpath(os.path.join(
            os.path.abspath(viztracer.__file__),
            '..',
            'web_dist'
        ))


settings = Settings()
