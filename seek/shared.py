"""Value helpers shared by every Seek parser: safe nested access, numbers,
text, dates, site links, salary labels and HTML descriptions. Pure
functions, no network; every helper tolerates None and junk.

The generic helpers (g / as_list / as_dict, num ... iso_date) mirror
indeed/parsers.py and indeed/shared.py with the same semantics; they live
here so the seek package stands alone (it ships as its own open-source
repo, which must not pull in other sites' modules)."""
import html as html_lib
import re
from datetime import datetime
from html.parser import HTMLParser

from seek import refdata

# ---- safe access ---------------------------------------------------------------------------

def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


# ---- numbers -------------------------------------------------------------------------------

def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None


def to_int(value):
    out = num(value)
    return int(round(out)) if out is not None else None


def rounded(value, digits=2):
    out = num(value)
    return round(out, digits) if out is not None else None


def amount(value):
    """A money amount: whole numbers as int, others rounded to cents."""
    out = num(value)
    if out is None:
        return None
    return int(out) if float(out).is_integer() else round(out, 2)


def rating(value):
    """A 0-5 star rating rounded to 2 places; 0 / missing -> None."""
    out = num(value)
    return round(out, 2) if out else None


# ---- text ----------------------------------------------------------------------------------

def text(value):
    """Whitespace-collapsed, HTML-unescaped string; '' -> None. Accepts
    {"text": ...} wrappers."""
    if isinstance(value, dict):
        value = value.get("text")
    if value is None:
        return None
    out = " ".join(html_lib.unescape(str(value)).replace("\xa0", " ").split())
    return out or None


def multiline(value):
    """Like text() but keeps line breaks (review bodies, descriptions)."""
    if isinstance(value, dict):
        value = value.get("text")
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None


_LONG_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")


def iso_date(value):
    """'21 Sep 2026' / '2026-09-22T…' / 'September 22, 2026' -> 'YYYY-MM-DD'."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return "-".join(match.groups())
    for fmt in _LONG_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

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


# ---- dates ------------------------------------------------------------------------------------

def iso_datetime(value):
    """'2026-09-18T04:30:49.433Z' -> '2026-09-18T04:30:49Z' (UTC, second precision)."""
    if isinstance(value, dict):
        value = value.get("dateTimeUtc") or value.get("dateTime")
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", value)
    if match:
        return f"{match.group(1)}T{match.group(2)}Z"
    return iso_date(value)


# ---- labels --------------------------------------------------------------------------------------

def lower_snake(value):
    """'Work/Life balance' / 'Benefits & perks' -> 'work_life_balance' / 'benefits_perks'."""
    value = text(value)
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or None


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


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in ("li", "br"):
            return
        elif tag in ("ul", "ol"):
            self.parts.append("\n\n")      # a list ends its paragraph
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(value):
    """An HTML fragment -> readable plain text: block elements become line
    breaks, list items get a dash, runs of blank lines collapse."""
    value = value if isinstance(value, str) else None
    if not value:
        return None
    if "<" not in value:
        return multiline(value)
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return multiline(re.sub(r"<[^>]+>", " ", value))
    raw = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"\n\n(- )", r"\n\1", out).strip()   # list items stay tight
    return out or None
