import hashlib
import ipaddress
import socket
from urllib.parse import urlparse

# --- Allowed PDF/Image magic bytes ---
MAGIC_PDF = b"%PDF-"
MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
MAGIC_JPEG = b"\xff\xd8\xff"
MAGIC_WEBP_RIFF = b"RIFF"
MAGIC_WEBP_LABEL = b"WEBP"

ALLOWED_MAGICS = (MAGIC_PDF, MAGIC_PNG, MAGIC_JPEG, MAGIC_WEBP_RIFF)

# Private/loopback ranges blocked by SSRF guard
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFBlockedError(ValueError):
    pass


class MagicByteError(ValueError):
    pass


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_ssrf(url: str) -> str:
    """
    Raise SSRFBlockedError if the URL resolves to a private/loopback address
    or uses a non-HTTP(S) scheme. Returns the validated URL string.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Scheme '{parsed.scheme}' is not allowed; use http or https.")
    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("URL is missing a hostname.")

    # Block raw IP addresses pointing to private ranges
    try:
        addr = ipaddress.ip_address(hostname)
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise SSRFBlockedError(f"IP address {hostname} is in a private/reserved range.")
    except ValueError:
        # It's a domain — resolve and check each resolved IP
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise SSRFBlockedError(f"DNS resolution failed for {hostname}: {exc}") from exc
        for _, _, _, _, sockaddr in infos:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    raise SSRFBlockedError(
                        f"Hostname {hostname} resolves to private IP {ip_str}."
                    )

    return url


def validate_file_magic(data: bytes) -> str:
    """
    Check the first bytes against allowed magic signatures.
    Returns 'pdf', 'png', 'jpeg', or 'webp'. Raises MagicByteError otherwise.
    """
    if data[:5] == MAGIC_PDF:
        return "pdf"
    if data[:8] == MAGIC_PNG:
        return "png"
    if data[:3] == MAGIC_JPEG:
        return "jpeg"
    if data[:4] == MAGIC_WEBP_RIFF and data[8:12] == MAGIC_WEBP_LABEL:
        return "webp"
    raise MagicByteError(
        "File does not start with a recognised magic signature (PDF, PNG, JPEG, WebP)."
    )
