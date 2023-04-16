from .infrastructure.middleware.fastapi import ProfyleMiddleware as fast_mid
from .infrastructure.middleware.flask import ProfyleMiddleware as flask_mid


ProfyleFlaskMiddleware = flask_mid
ProfyleFastApiMiddleware = fast_mid