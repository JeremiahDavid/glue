from __future__ import annotations


def dns_record_name(hostname: str, zone_name: str) -> str | None:
    """Return Route53 record name relative to zone (None for zone apex)."""
    normalized_zone = zone_name.strip().lower().rstrip(".")
    normalized_host = hostname.strip().lower().rstrip(".")
    if normalized_host == normalized_zone:
        return None
    suffix = f".{normalized_zone}"
    if normalized_host.endswith(suffix):
        return normalized_host[: -len(suffix)]
    raise ValueError(f"Hostname {hostname!r} is not inside zone {zone_name!r}")


def expand_hostnames(
    *,
    zone_name: str,
    primary_hostname: str,
    alternate_hostnames: list[str],
) -> list[str]:
    normalized_zone = zone_name.strip().lower().rstrip(".")
    primary = primary_hostname.strip().lower().rstrip(".")
    hostnames = [primary]
    for item in alternate_hostnames:
        token = str(item).strip().lower().rstrip(".")
        if not token:
            continue
        hostname = token if "." in token else f"{token}.{normalized_zone}"
        if hostname not in hostnames:
            hostnames.append(hostname)
    return hostnames
