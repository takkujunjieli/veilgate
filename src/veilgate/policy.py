"""Deterministic authorization, independent of HTTP and model behavior."""

from veilgate.config import Resource, Settings
from veilgate.errors import GatewayError


class Policy:
    def __init__(self, settings: Settings) -> None:
        self.version = settings.policy_version
        self._resources = {resource.id: resource for resource in settings.resources}

    def authorize(self, principal: str, resource_id: str) -> Resource:
        resource = self._resources.get(resource_id)
        if resource is None or principal not in resource.allowed_principals:
            # Do not disclose whether another principal's resource exists.
            raise GatewayError("resource_unavailable", 404)
        return resource

    def fields(self, resource: Resource, requested: list[str] | None) -> tuple[str, ...]:
        if requested is None:
            return tuple(resource.published_fields)
        if len(requested) != len(set(requested)) or not set(requested).issubset(
            resource.published_fields
        ):
            raise GatewayError("fields_not_allowed", 403)
        return tuple(requested)
