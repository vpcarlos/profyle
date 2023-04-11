from starlette.types import ASGIApp, Scope, Receive, Send

from profyle.models.profyle import profyle


class ProfyleMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
    ):
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.enabled and scope['type'] == 'http':
            with profyle(name=scope['raw_path']):
                await self.app(scope, receive, send)
            return
        await self.app(scope, receive, send)
