"""Value helpers shared by every Seek parser: safe nested access, numbers,
text, dates, site links, salary labels and HTML descriptions. Pure
functions, no network; every helper tolerates None and junk.

The generic helpers (g / as_list / as_dict, num ... iso_date) mirror
indeed/parsers.py and indeed/shared.py with the same semantics; the ones every
site shares come from scraper_utils and the rest live here (the seek package
ships as its own open-source repo, which must not pull in other sites'
modules)."""
import re
from datetime import datetime
from html.parser import HTMLParser

from seek import refdata
from scraper_utils.text import clean as text, html_to_text, lower_snake, multiline
from scraper_utils.values import amount, as_dict, as_list, g, num, rating, rounded, to_int_round as to_int
from scraper_utils.dates import iso_date, iso_datetime

# ---- text ----------------------------------------------------------------------------------


_LONG_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")


# ---- sites / links -------------------------------------------------------------------------

def site(country):
    return refdata.SITES.get((country or refdata.DEFAULT_COUNTRY).upper(), refdata.SITES[refdata.DEFAULT_COUNTRY])


def host(country):
    return site(country)["host"]


def currency(country):
    return site(country)["currency"]


def link(country, path):
    """A site-relative path (or absolute URL) -> absolute https link on the
    country's Seek host; '' / None -> None."""
    path = text(path) if isinstance(path, str) else None
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    if path.startswith("//"):
        return "https:" + path
    return f"https://{host(country)}/{path.lstrip('/')}"


def job_link(country, job_id):
    return f"https://{host(country)}/job/{job_id}" if job_id else None


def company_link(country, slug):
    return f"https://{host(country)}/companies/{slug}" if slug else None


def role_link(country, alias):
    return f"https://{host(country)}/career-advice/role/{alias}" if alias else None


def company_slug_id(slug):
    """'subway-432301' -> ('subway', '432301'); '432301' -> (None, '432301')."""
    slug = text(slug) if isinstance(slug, str) else None
    if not slug:
        return None, None
    match = re.fullmatch(r"(?:(.+)-)?(\d+)", slug)
    if not match:
        return slug, None
    return match.group(1), match.group(2)


# ---- labels --------------------------------------------------------------------------------------


def seek_id(value):
    """'seek-16351' / 16351 -> 16351 (the numeric Seek location id)."""
    value = text(value) if not isinstance(value, (int, float)) else str(int(value))
    if not value:
        return None
    match = re.search(r"(\d+)$", value)
    return int(match.group(1)) if match else None


# ---- salary labels ----------------------------------------------------------------------------------

_PERIOD_WORDS = [
    ("hourly", r"\b(?:per|an|/)\s*(?:hour|hr)\b|\bp\.?h\.?\b|\bhourly\b"),
    ("daily", r"\b(?:per|a|/)\s*day\b|\bdaily\b|\bday rate\b"),
    ("weekly", r"\b(?:per|a|/)\s*week\b|\bweekly\b"),
    ("fortnightly", r"\b(?:per|a|/)\s*fortnight\b|\bfortnightly\b"),
    ("monthly", r"\b(?:per|a|/)\s*month\b|\bmonthly\b"),
    ("yearly", r"\b(?:per|a|/)\s*(?:year|annum|yr)\b|\bp\.?a\.?\b|\bannual(?:ly)?\b|\byearly\b"),
]
_AMOUNT_RE = re.compile(r"\$?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kK])?")


def _amounts(label):
    out = []
    for match in _AMOUNT_RE.finditer(label):
        raw, k = match.group(1), match.group(2)
        value = num(raw.replace(",", ""))
        if value is None:
            continue
        if k:
            value *= 1000
        out.append(value)
    return out


def salary_from_label(label, currency_code=None):
    """'$160,000 to $200,000 + super' -> {label, min, max, currency, period,
    includes_super}; a label with no figure keeps min/max None. '' -> None."""
    label = text(label)
    if not label:
        return None
    amounts = [a for a in _amounts(label) if a >= 1]
    period = None
    low = label.lower()
    for name, pattern in _PERIOD_WORDS:
        if re.search(pattern, low):
            period = name
            break
    # figures >= 1000 with no stated period are annual packages; small
    # figures (hourly rates) stay unclassified unless the label says so
    if period is None and amounts and min(amounts) >= 10_000:
        period = "yearly"
    # drop superannuation percentages ("+ 12% super") and year numbers
    figures = [a for a in amounts if not (a <= 100 and "%" in label)]
    figures = [a for a in figures if a < 10_000_000]
    low_v = amount(min(figures)) if figures else None
    high_v = amount(max(figures)) if figures else None
    if low_v is not None and high_v is not None and low_v == high_v and len(figures) == 1:
        # "up to $120k" / "from $80k" / a single figure
        if re.search(r"\bup to\b|\bmax(?:imum)?\b", low):
            low_v = None
        elif re.search(r"\bfrom\b|\bmin(?:imum)?\b|\bstarting\b|\+", low):
            high_v = None
    return {
        "label": label,
        "min": low_v,
        "max": high_v,
        "currency": currency_code,
        "period": period,
        "includes_super": ("super" in low) if "super" in low else None,
    }


# ---- HTML -> text ------------------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt", "dl"}
_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}
