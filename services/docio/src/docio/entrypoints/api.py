"""
API server.

```shell
$ python -m docio.entrypoints.api
$ CUDA_VISIBLE_DEVICES=1 WORKERS=2 python -m docio.entrypoints.api
```
"""

from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import ORJSONResponse
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from docio.routers import loader
from docio.utils.logging import replace_logging_handlers, setup_logger_sinks


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", cli_parse_args=True
    )
    docio_port: int = 6979
    docio_host: str = "0.0.0.0"
    docio_workers: int = 2
    service: str | None = None
    prefix: str = "/api/docio"


config = Config()
setup_logger_sinks()
# We purposely don't intercept uvicorn logs since it is typically not useful
# We also don't intercept transformers logs
replace_logging_handlers(["uvicorn.access"], False)


app = FastAPI(
    logger=logger,
    openapi_url=f"{config.prefix}/openapi.json",
    docs_url=f"{config.prefix}/docs",
    redoc_url=f"{config.prefix}/redoc",
)
services = {
    "loader": (loader.router, ["Document loader"]),
}
if config.service:
    try:
        router, tags = services[config.service]
    except KeyError:
        logger.error(f"Invalid service '{config.service}', choose from: {list(services.keys())}")
        raise
    app.include_router(router, prefix=config.prefix, tags=tags)
else:
    # Mount everything
    for router, tags in services.values():
        app.include_router(router, prefix=config.prefix, tags=tags)


@app.on_event("startup")
async def startup():
    # Temporary for backwards compatibility
    logger.info(f"Using configuration: {config}")


# Order of handler does not matter
@app.exception_handler(FileNotFoundError)
async def file_not_found_exc_handler(request: Request, exc: FileNotFoundError):
    return ORJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": [{"type": "file_not_found", "msg": str(exc)}]},
    )


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    return ORJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(
            [
                {
                    "type": "unexpected_error",
                    "msg": f"Encountered error: {repr(exc)}",
                }
            ]
        ),
    )


@app.get("/health")
async def health() -> Response:
    """Health check."""
    return Response(status_code=200)


if __name__ == "__main__":
    import uvicorn
    import os

    if os.name == "nt":
        import asyncio
        from multiprocessing import freeze_support

        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        freeze_support()
        logger.info("The system is Windows.")
    else:
        logger.info("The system is not Windows.")

    uvicorn.run(
        "docio.entrypoints.api:app",
        reload=False,
        host=config.docio_host,
        port=config.docio_port,
        workers=config.docio_workers,
    )
