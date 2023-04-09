from profyle.models.profyle import profyle


class ProfyleMiddleware:

    def __init__(self, app, enabled: bool = True):
        self.app = app
        self.enabled = enabled

    def __call__(self, environ, start_response):
        if environ.get('wsgi.url_scheme') == 'http' and self.enabled:
            with profyle(name=environ['REQUEST_URI']):
                return self.app(environ, start_response)
        return self.app(environ, start_response)
