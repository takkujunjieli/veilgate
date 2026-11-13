"""Only fixed public error codes cross the trust boundary."""


class GatewayError(Exception):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class StartupError(Exception):
    """Intentionally contains neither config contents nor paths."""
