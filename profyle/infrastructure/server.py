import uvicorn

from profyle.infrastructure.api.routes import app


async def start_server(port: int = 0, host: str = "127.0.0.1"):
    config = uvicorn.Config(app, port=port, log_level="info", host=host)
    server = uvicorn.Server(config)
    await server.serve()