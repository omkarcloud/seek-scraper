"""Seek input parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention, never a sibling `url`/`id` pair).
Every resolver returns plain JSON values so validated params stay usable as
a response-cache key, and raises ValueError with a user-facing message.

  country   AU | au | Australia | nz | New Zealand | seek.co.nz
            | https://www.seek.com.au/jobs?...                  -> "AU" / "NZ"
  job       94722577 | https://www.seek.com.au/job/94722577?type=standard
            | au.seek.com/job/94722577 | /job/94722577/apply     -> "94722577"
  company   432301 | subway-432301 | https://www.seek.com.au/companies/subway-432301/reviews
            | Subway (a name, looked up on the site at call time)
                                        -> {"id": "432301", "slug": "subway-432301", "name": None, "country": None}
                                         | {"id": None, "slug": None, "name": "Subway", "country": None}
            (country is the link's market when a seek.co.nz / seek.com.au link was given)
  role      software-engineer | Software Engineer
            | https://www.seek.com.au/career-advice/role/software-engineer/salary
                                        -> {"alias": "software-engineer", "title": None}
                                         | {"alias": None, "title": "Software Engineer"} (normalised at call time)
  industry  information-technology-services | Information Technology Services
            | https://www.seek.com.au/companies/directory/information-technology-services
                                        -> "information-technology-services"
  location  (job search) free text, or a Seek location id (16351) -> as given
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

from seek import refdata

_SLUG_BAD = re.compile(r"[/?#\\<>\"]")


def _parse_url(value):
    """-> (host, path, query dict) when value looks like a Seek URL / host
    path, None when it is plain text. Raises ValueError for another site."""
    raw = (value or "").strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif not low.startswith(("http://", "https://")):
        head = low.split("/", 1)[0]
        if "seek." not in head:
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in refdata.HOST_COUNTRIES and not host.endswith((".seek.com.au", ".seek.co.nz", ".seek.com")):
        raise ValueError("Must be a seek.com.au or seek.co.nz link.")
    return host, unquote(parsed.path), parse_qs(parsed.query)


def _country_of_host(host):
    host = (host or "").lower()
    if host in refdata.HOST_COUNTRIES:
        return refdata.HOST_COUNTRIES[host]
    if host.endswith(".seek.co.nz") or host.startswith("nz."):
        return "NZ"
    if host.endswith(".seek.com.au") or host.startswith("au."):
        return "AU"
    return None


# ---- country ------------------------------------------------------------------------------------

COUNTRY_HINT = "Must be a Seek market: AU (Australia) or NZ (New Zealand), its name, or a seek.com.au / seek.co.nz link."


def resolve_country(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COUNTRY_HINT)
    try:
        url = _parse_url(raw) if ("." in raw or "/" in raw) else None
    except ValueError:
        raise ValueError(COUNTRY_HINT)
    if url:
        code = _country_of_host(url[0])
        if code:
            return code
        raise ValueError(COUNTRY_HINT)
    low = raw.lower()
    if low in refdata.COUNTRY_NAMES:
        return refdata.COUNTRY_NAMES[low]
    code = raw.upper()
    if code in refdata.SITES:
        return code
    raise ValueError(f"Seek has no site for '{raw}'. " + COUNTRY_HINT)


def country_of_link(value):
    """The country of a Seek link's host, or None."""
    try:
        url = _parse_url(value or "")
    except ValueError:
        return None
    return _country_of_host(url[0]) if url else None


# ---- jobs -------------------------------------------------------------------------------------------

JOB_HINT = "Must be a Seek job id (digits, e.g. 94722577) or a seek.com.au / seek.co.nz job link (/job/<id>)."


def resolve_job(value):
    raw = (value or "").strip()
    if raw.isdigit():
        return raw
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(JOB_HINT)
    if not url:
        raise ValueError(JOB_HINT)
    _, path, query = url
    match = re.search(r"/job/(\d+)(?:[/?#]|$)", path)
    if match:
        return match.group(1)
    for name in ("jobId", "jobid", "id"):
        for candidate in query.get(name, []):
            if candidate.strip().isdigit():
                return candidate.strip()
    raise ValueError(JOB_HINT)


# ---- companies ----------------------------------------------------------------------------------------

COMPANY_HINT = ("Must be a Seek company id (432301), the slug from a company page link (subway-432301), "
                "a seek.com.au / seek.co.nz /companies/ link, or a company name.")


def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    if raw.isdigit():
        return {"id": raw, "slug": None, "name": None, "country": None}
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(COMPANY_HINT)
    country = None
    if url:
        match = re.search(r"/companies/([^/?#]+)", url[1])
        if not match or match.group(1) in ("directory", "search", "write-a-review"):
            raise ValueError("Seek links must be company pages (/companies/<name>-<id>).")
        raw = match.group(1)
        country = _country_of_host(url[0])   # a seek.co.nz link means the NZ profile zone
    match = re.fullmatch(r"([a-z0-9][a-z0-9-]*)-(\d+)", raw.lower())
    if match and " " not in raw:
        return {"id": match.group(2), "slug": raw.lower(), "name": None, "country": country}
    name = " ".join(raw.split())
    if _SLUG_BAD.search(name) or len(name) > 150:
        raise ValueError(COMPANY_HINT)
    return {"id": None, "slug": None, "name": name, "country": country}


# ---- roles (career guide) ---------------------------------------------------------------------------------

ROLE_HINT = ("Must be a role title (Software Engineer), a Seek career-guide role alias (software-engineer) "
             "or a seek.com.au / seek.co.nz /career-advice/role/ link.")


def resolve_role(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(ROLE_HINT)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(ROLE_HINT)
    if url:
        match = re.search(r"/career-advice/role/([^/?#]+)", url[1])
        if not match:
            raise ValueError("Seek links must be career-guide role pages (/career-advice/role/<alias>).")
        return {"alias": match.group(1).lower(), "title": None}
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", raw) and len(raw) <= 120:
        return {"alias": raw, "title": None}
    title = " ".join(raw.split())
    if _SLUG_BAD.search(title) or len(title) > 120:
        raise ValueError(ROLE_HINT)
    return {"alias": None, "title": title}


def slugify_role(title):
    """'Software Engineer' -> 'software-engineer' (the career guide's alias shape)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return slug or None


# ---- company directory industries ---------------------------------------------------------------------------

INDUSTRY_HINT = ("Must be a Seek company-directory industry: its name (Information Technology Services), "
                 "its slug (information-technology-services) or a /companies/directory/<slug> link.")


def resolve_industry(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(INDUSTRY_HINT)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(INDUSTRY_HINT)
    if url:
        match = re.search(r"/companies/directory/([^/?#]+)", url[1])
        if not match:
            raise ValueError("Seek links must be directory industry pages (/companies/directory/<slug>).")
        return match.group(1).lower()
    return slugify_industry(raw)


def slugify_industry(name):
    """'Architectural & Design Services' -> 'architectural-n-design-services'
    (Seek spells '&' as 'n' in directory slugs)."""
    low = (name or "").lower().replace("&", " n ")
    slug = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
    if not slug or len(slug) > 120:
        raise ValueError(INDUSTRY_HINT)
    return slug


# ---- locations ----------------------------------------------------------------------------------------------

def resolve_location(value):
    """Free text as typed in Seek's 'Where' box, or a Seek location id."""
    raw = " ".join((value or "").split())
    if not raw:
        return None
    if len(raw) > 120:
        raise ValueError("Location must be at most 120 characters.")
    return raw
