"""Channel grouping and UTM normalisation.

Reports call ``classify_channel`` on stored source fields so the rules can
change later. The event row also stores the channel computed at write time.

Browser and platform privacy features often strip ``Referer``. A visit with
no campaign and no external referrer is classified as direct, which includes
some visits whose referrer was suppressed. That limitation is expected.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode, urlsplit, urlunsplit

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_UTM = re.compile(r"^[a-z0-9._~-]{1,80}$")
_CAMPAIGN_PART = re.compile(r"^[a-z0-9_]+$")
_PATH = re.compile(r"^/[A-Za-z0-9._~/-]{0,180}$")

# Sources we name explicitly. Any other valid slug is still kept and grouped
# as "<source> / campaign".
RECOGNISED_CAMPAIGN_SOURCES = frozenset({
    "linkedin",
    "youtube",
    "instagram",
    "facebook",
    "google",
    "bing",
    "newsletter",
    "email",
    "chatgpt",
    "direct",
})

_SOCIAL_ROOTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("linkedin", ("linkedin.com", "lnkd.in")),
    ("youtube", ("youtube.com", "youtu.be")),
    ("instagram", ("instagram.com",)),
    ("facebook", ("facebook.com", "fb.com", "m.facebook.com")),
    ("chatgpt", ("chatgpt.com", "chat.openai.com")),
)

_OTHER_SEARCH_ROOTS = (
    "yahoo.com",
    "search.yahoo.com",
    "ecosia.org",
    "baidu.com",
    "yandex.com",
    "yandex.ru",
    "search.brave.com",
    "brave.com",
)

OWN_SITE_HOSTS = frozenset({"hvac-calcs.app", "www.hvac-calcs.app"})

UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


def strip_controls(raw: str) -> str:
    return _CONTROL.sub("", raw).strip()


def normalise_utm(key: str, raw: object) -> str | None:
    """Lower-case a campaign value. Reject email-like and non-slug text."""
    if not isinstance(raw, str):
        return None
    text = strip_controls(raw).lower()
    if not text or "@" in text or any(ch.isspace() for ch in text):
        return None
    limit = 64 if key in {"utm_source", "utm_medium"} else 80
    text = text[:limit]
    if _UTM.fullmatch(text) is None:
        return None
    return text


def normalise_path(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = strip_controls(raw)
    if "?" in text:
        text = text.split("?", 1)[0]
    if "#" in text:
        text = text.split("#", 1)[0]
    if not text.startswith("/") or text.startswith("//") or "@" in text:
        return None
    text = text[:200]
    if _PATH.fullmatch(text) is None:
        return None
    return text


def host_matches(host: str, root: str) -> bool:
    return host == root or host.endswith("." + root)


def parse_referrer(raw: object, own_hosts: set[str] | None = None) -> tuple[str | None, str | None]:
    """Return (hostname, safe path). Query strings are discarded."""
    if not isinstance(raw, str):
        return None, None
    text = strip_controls(raw)
    if not text or len(text) > 500:
        text = text[:500] if text else ""
    if not text or "@" in text.split("/")[0]:
        return None, None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None, None
    host = (parsed.hostname or "").lower().strip(".")
    if not host or "@" in host or len(host) > 120:
        return None, None
    owners = {item.lower() for item in (own_hosts or set())}
    owners.update(OWN_SITE_HOSTS)
    if host in owners or any(host == item or host.endswith("." + item) for item in owners):
        return None, None
    path = normalise_path(parsed.path or "")
    return host[:120], path


def search_engine(host: str | None) -> str | None:
    if not host:
        return None
    name = host.lower().strip(".")
    bare = name[4:] if name.startswith("www.") else name
    if name not in {bare, "www." + bare}:
        return None
    if bare == "bing.com" or bare.endswith(".bing.com"):
        return "bing"
    if bare == "duckduckgo.com":
        return "duckduckgo"
    if bare == "google.com" or bare.startswith("google."):
        return "google"
    for root in _OTHER_SEARCH_ROOTS:
        if host_matches(name, root) or host_matches(bare, root):
            return "other_search"
    return None


def social_network(host: str | None) -> str | None:
    if not host:
        return None
    name = host.lower().strip(".")
    for label, roots in _SOCIAL_ROOTS:
        for root in roots:
            if host_matches(name, root):
                return label
    return None


def classify_channel(
    *,
    utm_source: str | None,
    referrer_host: str | None,
    captured: bool,
    utm_unusable: bool = False,
) -> str:
    """Group one touch. Missing capture stays ``unknown`` and is not called direct."""
    if not captured or utm_unusable:
        return "unknown"
    if utm_source:
        return f"{utm_source} / campaign"
    engine = search_engine(referrer_host)
    if engine == "google":
        return "google / organic"
    if engine == "bing":
        return "bing / organic"
    if engine == "duckduckgo":
        return "duckduckgo / organic"
    if engine == "other_search":
        return "other_search / organic"
    social = social_network(referrer_host)
    if social:
        return f"{social} / referral"
    if referrer_host:
        return "other_referral / referral"
    return "direct"


def build_campaign_url(
    base: str,
    *,
    source: str,
    medium: str,
    campaign: str,
    content: str,
) -> str | None:
    """https URL with the lowercase underscore UTM convention. None if invalid."""
    values = {
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
        "utm_content": content,
    }
    if any(not isinstance(value, str) or _CAMPAIGN_PART.fullmatch(value) is None for value in values.values()):
        return None
    text = (base or "").strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.netloc or "@" in parts.netloc:
        return None
    path = parts.path or "/"
    query = urlencode(values)
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))
