"""Opaque, high-entropy service credentials mapped to operator-defined identities."""

import hashlib
import hmac

from veilgate.errors import GatewayError


class Authenticator:
    def __init__(self, tokens: dict[str, str]) -> None:
        self._digests = tuple(
            (principal, hashlib.sha256(token.encode("ascii")).digest())
            for principal, token in tokens.items()
        )

    def authenticate(self, headers: list[tuple[bytes, bytes]]) -> str:
        values = [value for key, value in headers if key.lower() == b"authorization"]
        if len(values) != 1 or len(values[0]) > 263:
            raise GatewayError("unauthorized", 401)
        scheme, separator, credential = values[0].partition(b" ")
        if scheme.lower() != b"bearer" or not separator or not credential:
            raise GatewayError("unauthorized", 401)
        digest = hashlib.sha256(credential).digest()
        match = None
        for principal, expected in self._digests:
            if hmac.compare_digest(digest, expected):
                match = principal
        if match is None:
            raise GatewayError("unauthorized", 401)
        return match
