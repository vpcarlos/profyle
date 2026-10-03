"""Flask integration: the generic WSGI middleware.

    app.wsgi_app = ProfyleMiddleware(app.wsgi_app)
"""

from profyle.infrastructure.middleware.wsgi import ProfyleMiddleware

__all__ = ["ProfyleMiddleware"]
