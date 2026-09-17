from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class ManifestError(ValueError):
    """Raised when a public gateway manifest violates the contract."""


SUPPORTED_ADAPTERS = {"caddy", "kong", "nginx", "apisix"}
SUPPORTED_AUTH = {"key-auth", "jwt"}
SUPPORTED_SCHEDULERS = {"round-robin", "least-connections", "chash"}
FORBIDDEN_KEYS = {
    "api_key",
    "apikey",
    "password",
    "oauth_token",
    "refresh_token",
    "id_token",
    "private_key",
    "session_secret",
    "crypto_secret",
    "auth_bundle",
}
OLD_VAULT_PATHS = (
    "/accounts/",
    "/instances/",
    "/clients/",
    "/cpa/",
    "/database/backup",
)


def load_yaml(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ManifestError(f"{source}: document root must be a mapping")
    return value


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{path}: expected mapping")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ManifestError(f"{path}: expected list")
    return value


def _unique_ids(items: list[Any], path: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        mapping = _require_mapping(item, item_path)
        identifier = mapping.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ManifestError(f"{item_path}.id: required non-empty string")
        if identifier in result:
            raise ManifestError(f"{item_path}.id: duplicate id {identifier!r}")
        result[identifier] = mapping
    return result


def _scan_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise ManifestError(f"{path}.{key}: sensitive field is not allowed")
            _scan_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]")
    elif isinstance(value, str):
        for old_path in OLD_VAULT_PATHS:
            if old_path in value:
                raise ManifestError(f"{path}: deprecated Vault path {old_path!r}")


def _host_kind(host: str) -> str:
    host = host.lower().rstrip(".")
    if host.startswith("direct.ai."):
        return "litellm"
    if host.startswith("ai."):
        return "new-api"
    return "unknown"


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    _scan_forbidden(manifest)

    if manifest.get("schema_version") != "v1":
        raise ManifestError("schema_version: must be 'v1'")

    gateway = _require_mapping(manifest.get("gateway"), "gateway")
    adapter = gateway.get("adapter")
    if adapter not in SUPPORTED_ADAPTERS:
        raise ManifestError(f"gateway.adapter: unsupported adapter {adapter!r}")
    environment = gateway.get("environment")
    if not isinstance(environment, str) or not environment:
        raise ManifestError("gateway.environment: required non-empty string")
    domains = gateway.get("domains")
    if not isinstance(domains, list) or not domains or any(
        not isinstance(domain, str) or not domain for domain in domains
    ):
        raise ManifestError("gateway.domains: must be a non-empty list of hostnames")
    allowed_domains = set(domains)

    if adapter == "kong":
        if gateway.get("mode") != "traditional":
            raise ManifestError("gateway.mode: Kong v1 requires traditional mode")
        if gateway.get("runtime_config_backend") != "postgresql":
            raise ManifestError("gateway.runtime_config_backend: Kong v1 requires postgresql")
        if gateway.get("etcd") is not False:
            raise ManifestError("gateway.etcd: Kong v1 must set etcd=false")

    upstreams = _unique_ids(_require_list(manifest.get("upstreams"), "upstreams"), "upstreams")
    tenants = _unique_ids(_require_list(manifest.get("tenants"), "tenants"), "tenants")
    routes = _require_list(manifest.get("routes"), "routes")

    for identifier, upstream in upstreams.items():
        nodes = upstream.get("nodes")
        if nodes is not None:
            nodes = _require_list(nodes, f"upstreams.{identifier}.nodes")
            if not nodes:
                raise ManifestError(f"upstreams.{identifier}.nodes: must not be empty")
            for node_index, node_value in enumerate(nodes):
                node = _require_mapping(node_value, f"upstreams.{identifier}.nodes[{node_index}]")
                if not isinstance(node.get("host"), str) or not node.get("host"):
                    raise ManifestError(
                        f"upstreams.{identifier}.nodes[{node_index}].host: required"
                    )
                if not isinstance(node.get("port"), int) or node.get("port") <= 0:
                    raise ManifestError(
                        f"upstreams.{identifier}.nodes[{node_index}].port: must be positive"
                    )
                if "weight" in node and (
                    not isinstance(node["weight"], int) or node["weight"] <= 0
                ):
                    raise ManifestError(
                        f"upstreams.{identifier}.nodes[{node_index}].weight: must be positive"
                    )
        else:
            if not isinstance(upstream.get("host"), str) or not upstream.get("host"):
                raise ManifestError(f"upstreams.{identifier}.host: required")
            if not isinstance(upstream.get("port"), int) or upstream.get("port") <= 0:
                raise ManifestError(f"upstreams.{identifier}.port: must be a positive integer")
        schedule = _require_mapping(upstream.get("schedule", {}), f"upstreams.{identifier}.schedule")
        algorithm = schedule.get("algorithm", "round-robin")
        if algorithm not in SUPPORTED_SCHEDULERS:
            raise ManifestError(
                f"upstreams.{identifier}.schedule.algorithm: unsupported {algorithm!r}"
            )
        for timeout_name in ("connect_timeout_ms", "read_timeout_ms", "write_timeout_ms"):
            if timeout_name in schedule and (
                not isinstance(schedule[timeout_name], int) or schedule[timeout_name] <= 0
            ):
                raise ManifestError(
                    f"upstreams.{identifier}.schedule.{timeout_name}: must be positive"
                )
        if upstream.get("public", False) is True:
            raise ManifestError(f"upstreams.{identifier}.public: AI upstreams must not be public")

    route_ids: set[str] = set()
    for index, route_value in enumerate(routes):
        path = f"routes[{index}]"
        route = _require_mapping(route_value, path)
        identifier = route.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ManifestError(f"{path}.id: required non-empty string")
        if identifier in route_ids:
            raise ManifestError(f"{path}.id: duplicate id {identifier!r}")
        route_ids.add(identifier)

        upstream_id = route.get("upstream")
        if upstream_id not in upstreams:
            raise ManifestError(f"{path}.upstream: unknown upstream {upstream_id!r}")
        tenant_id = route.get("tenant_ref")
        if tenant_id not in tenants:
            raise ManifestError(f"{path}.tenant_ref: unknown tenant {tenant_id!r}")

        hosts = _require_list(route.get("hosts"), f"{path}.hosts")
        if not hosts:
            raise ManifestError(f"{path}.hosts: must not be empty")
        expected_targets = set()
        for host_index, host_value in enumerate(hosts):
            if not isinstance(host_value, str) or not host_value:
                raise ManifestError(f"{path}.hosts[{host_index}]: required hostname")
            if host_value not in allowed_domains:
                raise ManifestError(
                    f"{path}.hosts[{host_index}]: host is not declared in gateway.domains"
                )
            kind = _host_kind(host_value)
            if kind == "unknown":
                raise ManifestError(f"{path}.hosts[{host_index}]: must use ai.* or direct.ai.*")
            expected_targets.add(kind)
        if len(expected_targets) != 1:
            raise ManifestError(f"{path}.hosts: cannot mix ai.* and direct.ai.* hosts")
        expected = expected_targets.pop()
        if upstream_id != expected:
            raise ManifestError(
                f"{path}.upstream: host family requires {expected!r}, got {upstream_id!r}"
            )

        paths = _require_list(route.get("paths"), f"{path}.paths")
        if not paths or any(not isinstance(item, str) or not item.startswith("/") for item in paths):
            raise ManifestError(f"{path}.paths: must contain absolute path strings")

        auth = _require_mapping(route.get("auth"), f"{path}.auth")
        if auth.get("mode") not in SUPPORTED_AUTH:
            raise ManifestError(f"{path}.auth.mode: must be one of {sorted(SUPPORTED_AUTH)}")

    for tenant_id, tenant in tenants.items():
        if tenant.get("enabled") not in (True, False):
            raise ManifestError(f"tenants.{tenant_id}.enabled: must be boolean")
        models = tenant.get("allowed_models", [])
        if not isinstance(models, list) or any(not isinstance(item, str) for item in models):
            raise ManifestError(f"tenants.{tenant_id}.allowed_models: must be a list of strings")

    return {
        "adapter": adapter,
        "environment": environment,
        "upstream_count": len(upstreams),
        "tenant_count": len(tenants),
        "route_count": len(routes),
    }
