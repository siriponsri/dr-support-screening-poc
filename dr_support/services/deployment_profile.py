"""Pure, fail-closed endpoint checks for the Hospital M1 deployment modes.

These checks do not resolve DNS, open connections, read private files or mutate
the environment. Passing validation is configuration evidence only; it does not
establish hospital network approval, model readiness or successful inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
import os
import re
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit


PROFILE_VARIABLE = "DR_SUPPORT_DEPLOYMENT_PROFILE"
QA_SERVER = "QA_SERVER"
QA_LOCAL = "QA_LOCAL"
_PROFILES = frozenset({QA_SERVER, QA_LOCAL})
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.I)


class DeploymentProfileError(ValueError):
    """A deployment setting would violate the selected private boundary."""


@dataclass(frozen=True)
class DeploymentConfiguration:
    """Sanitized deployment selection; credentials are never included."""

    profile: str | None
    model_endpoint: str | None


def resolve_deployment_profile(environ: Mapping[str, str] | None = None) -> str | None:
    """Resolve an explicit M1 selector without changing legacy developer mode."""

    settings = os.environ if environ is None else environ
    selected = settings.get(PROFILE_VARIABLE, "").strip()
    if not selected:
        return None
    if selected not in _PROFILES:
        raise DeploymentProfileError(
            "DR_SUPPORT_DEPLOYMENT_PROFILE must be QA_SERVER or QA_LOCAL."
        )
    return selected


def _normalized_endpoint(url: str) -> tuple[str, str]:
    # Do not echo invalid input: an accidentally pasted URL can contain secrets.
    if not isinstance(url, str):
        raise DeploymentProfileError("Model API URL must be a string.")
    cleaned = url.strip().rstrip("/")
    if not cleaned or any(character.isspace() or ord(character) < 32 for character in cleaned):
        raise DeploymentProfileError("Model API URL must not contain whitespace.")
    if "\\" in cleaned:
        raise DeploymentProfileError("Model API URL must not contain backslashes.")
    try:
        parsed = urlsplit(cleaned)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise DeploymentProfileError("Model API URL has an invalid host or port.") from None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not host:
        raise DeploymentProfileError("Model API URL must use http or https with an explicit host.")
    if "@" in parsed.netloc:
        raise DeploymentProfileError("Model API URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise DeploymentProfileError("Model API URL must not contain a query or fragment.")
    if parsed.netloc.endswith(":") or port == 0:
        raise DeploymentProfileError("Model API URL has an invalid host or port.")
    if "%" in host:
        raise DeploymentProfileError("Model API URL has an invalid host.")
    try:
        literal = ip_address(host)
    except ValueError:
        if len(host) > 253 or not all(_HOST_LABEL.fullmatch(label) for label in host.split(".")):
            raise DeploymentProfileError("Model API URL has an invalid host.") from None
        # Ambiguous numeric addresses must not be treated as DNS names.
        if all(character.isdigit() or character == "." for character in host):
            raise DeploymentProfileError("Model API URL must use an unambiguous host.") from None
        normalized_host = host.lower()
    else:
        normalized_host = f"[{literal.compressed}]" if literal.version == 6 else str(literal)
    effective_port = None if port == {"http": 80, "https": 443}[parsed.scheme] else port
    authority = normalized_host + (f":{effective_port}" if effective_port is not None else "")
    return urlunsplit((parsed.scheme, authority, parsed.path.rstrip("/"), "", "")), host.lower()


def _require_local_host(host: str) -> None:
    if host in {"localhost", "gateway"}:
        return
    try:
        if ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise DeploymentProfileError(
        "QA_LOCAL requires a loopback Model API or the gateway Compose service."
    )


def validate_model_endpoint(
    url: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Validate an endpoint before construction/probing; never follow redirects.

    QA modes require an operator-configured endpoint. QA_LOCAL also pins manual
    connection changes to that endpoint, so another local port cannot silently
    replace the selected local service. The HTTP clients independently disable
    redirect following; this function does not make a request.
    """

    settings = os.environ if environ is None else environ
    profile = resolve_deployment_profile(settings)
    if profile is None:
        return _normalized_endpoint(url)[0]
    configured = settings.get("REMOTE_MODEL_URL", "").strip()
    if not configured:
        raise DeploymentProfileError("The selected QA profile requires an explicit REMOTE_MODEL_URL.")
    normalized, host = _normalized_endpoint(url)
    configured_endpoint, configured_host = _normalized_endpoint(configured)
    if profile == QA_LOCAL:
        _require_local_host(host)
        _require_local_host(configured_host)
        if normalized != configured_endpoint:
            raise DeploymentProfileError(
                "QA_LOCAL Model API changes require updating the private deployment configuration and restarting."
            )
    return normalized


def validate_deployment_environment(
    environ: Mapping[str, str] | None = None,
) -> DeploymentConfiguration:
    """Pure preflight for release launchers; no reachability/readiness claim."""

    settings = os.environ if environ is None else environ
    profile = resolve_deployment_profile(settings)
    if profile is None:
        return DeploymentConfiguration(None, None)
    if settings.get("APP_PROFILE") != "review" or settings.get("MODEL_RUNTIME") != "remote":
        raise DeploymentProfileError("QA deployments require APP_PROFILE=review and MODEL_RUNTIME=remote.")
    endpoint = validate_model_endpoint(settings.get("REMOTE_MODEL_URL", ""), environ=settings)
    return DeploymentConfiguration(profile, endpoint)
