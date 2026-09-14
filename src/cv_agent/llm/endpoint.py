"""Classify an LLM endpoint as local (self-hosted) vs a public provider.

Some knobs are local-inference-server concepts, not OpenAI API fields — notably
``extra_body.chat_template_kwargs.enable_thinking`` (a vLLM/SGLang/MLX way to switch
off a Qwen3 chat template's reasoning). Sending them to a public provider
(OpenRouter/DeepSeek/OpenAI) is a no-op at best and a 400 at worst, so the client
only sends them when the base URL points at a local endpoint.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_LOCAL_HOSTNAMES = {"localhost"}


def is_local_base_url(base_url: str | None) -> bool:
    """True if ``base_url`` points at a local / self-hosted inference server: a loopback
    or private-LAN IP, ``localhost``, an unspecified address, or a ``*.local`` name. Public
    provider hostnames (e.g. ``openrouter.ai``, ``api.deepseek.com``) return False."""
    if not base_url:
        return False
    # urlparse needs a scheme to find the host; synthesise one for bare "host:port" inputs.
    host = urlparse(base_url if "://" in base_url else f"//{base_url}").hostname
    if not host:
        return False
    host = host.lower()
    if host in _LOCAL_HOSTNAMES or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a resolvable public hostname
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified
