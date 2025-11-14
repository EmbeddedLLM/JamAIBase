import base64
from typing import Any, Type

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from jamaibase.client import _ClientAsync
from owl.configs import ENV_CONFIG
from owl.version import __version__


class VictoriaMetricsAsync(_ClientAsync):
    def __init__(
        self,
        api_base: str = f"http://{ENV_CONFIG.victoria_metrics_host}:{ENV_CONFIG.victoria_metrics_port}",
        user: str = ENV_CONFIG.victoria_metrics_user,
        password: str = ENV_CONFIG.victoria_metrics_password_plain,
        timeout: float | None = 10.0,
    ) -> None:
        """
        Creates an async Emu client.

        Args:
            api_base (str, optional): The base URL for the API.
                Defaults to "http://{ENV_CONFIG.victoria_metrics_host}:{ENV_CONFIG.victoria_metrics_port}".
            user (str, optional): Victoria Metrics Basic authentication Username.
                Defaults to ENV_CONFIG.victoria_metrics_user.
            password (str, optional): Victoria Metrics Basic authentication Password.
                Defaults to ENV_CONFIG.victoria_metrics_password_plain.
            timeout (float | None, optional): The timeout to use when sending requests.
                Defaults to 10 seconds.
        """
        http_client = httpx.AsyncClient(
            timeout=timeout,
            transport=httpx.AsyncHTTPTransport(retries=3),
        )

        def basic_auth(username, password):
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            return f"Basic {token}"

        headers = {"Authorization": basic_auth(user, password)}
        kwargs = dict(
            user_id="",
            project_id="",
            token="",
            api_base=api_base,
            headers=headers,
            http_client=http_client,
            timeout=timeout,
        )
        super().__init__(**kwargs)

    async def _fetch_victoria_metrics(
        self, endpoint: str, params: dict | None = None
    ) -> httpx.Response:
        """
        Send a GET request to the specified VictoriaMetrics API endpoint.

        Args:
            endpoint (str): The API endpoint to send the request to.
            params (dict | None, optional): Query parameters to include in the request.

        Returns:
            httpx.Response | None: The HTTP response object if the request is successful, or None if the request fails.
        """
        return await self._get(endpoint, params=params)


class JamaiASGIAsync(_ClientAsync):
    def __init__(
        self,
        app: FastAPI,
        timeout: float | None = None,
    ) -> None:
        """
        Creates an async Owl ASGI client.

        Args:
            timeout (float | None, optional): The timeout to use when sending requests.
                Defaults to None.
        """
        super().__init__(
            user_id="",
            project_id="",
            token="",
            api_base="",
            headers=None,
            http_client=httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://apiserver",
                timeout=timeout,
            ),
            timeout=timeout,
        )

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        headers: dict[str, Any] | None = None,
        params: dict[str, Any] | BaseModel | None = None,
        body: BaseModel | None = None,
        response_model: Type[BaseModel] | None = None,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response | BaseModel:
        if headers is None:
            headers = {}
        headers["User-Agent"] = headers.get("User-Agent", f"MCP-Server/{__version__}")
        return await self._request(
            method=method,
            address="",
            endpoint=endpoint,
            headers=headers,
            params=params,
            body=body,
            response_model=response_model,
            timeout=timeout,
            ignore_code=None,
            process_body_kwargs=None,
            **kwargs,
        )
