import httpx
from loguru import logger

http_client = httpx.Client(timeout=5)


class VictoriaMetricsClient:
    def __init__(self, host: str, port: int, user: str = None, password: str = None):
        """Initialize a class for communicating with Victoria Metrics server.

        Args:
            host (str): The hostname or IP address of the VictoriaMetrics server.
            port (int): The port number of the VictoriaMetrics server.
            user (str | None, optional): The username for authentication.
            password (str | None, optional): The password for authentication.
        """
        self.endpoint = f"http://{host}:{port}"
        self.user = user or ""
        self.password = password or ""

    def _fetch_victoria_metrics(
        self, endpoint: str, params: dict | None = None
    ) -> httpx.Response | None:
        """Send a GET request to the specified VictoriaMetrics API endpoint.

        Args:
            endpoint (str): The API endpoint to send the request to.
            params (dict | None, optional): Query parameters to include in the request.

        Returns:
            httpx.Response | None: The HTTP response object if the request is successful, or None if the request fails.

        Raises:
            httpx.HTTPError: If the HTTP request returns an error status code.

        """
        try:
            response = http_client.get(
                f"{self.endpoint}{endpoint}", params=params, auth=(self.user, self.password)
            )
            response.raise_for_status()
            return response
        except httpx.HTTPError as e:
            logger.warning(f"Error querying VictoriaMetrics: {e}")
            return None
