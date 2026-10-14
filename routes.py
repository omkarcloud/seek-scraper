"""The 16 Seek endpoints. Every path is served with and without the `/seek`
prefix, so code generated against the hosted API on RapidAPI (paths like
/jobs/details) runs unchanged against this server.

Params are validated by the same marshmallow schemas the hosted API uses
(seek/schemas.py), and paginated endpoints answer in the same shape:
count / per_page / current_page / total_pages / next / previous, then the
data."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, NotFound
from seek import careers, companies, jobs, lookups, schemas


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Māori" would arrive garbled)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    host = request.urlparts.netloc or "localhost:8000"
    return f"{request.urlparts.scheme or 'http'}://{host}{path}?{urlencode(query, doseq=True)}"


def paginate(result, path, raw):
    """Lift the scraper's `pagination` block into the flat API shape."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = _as_int(pagination.get("page")) or _as_int(raw.get("page")) or 1
    total_pages = max(_as_int(pagination.get("total_pages")), 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, raw, page + 1 if page < total_pages else None),
        "previous": _page_link(path, raw, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(path, schema, impl, paginated=False):
    """Validate -> run -> shared error mapping: bad params -> 400, missing
    entity -> 404, transport / blocks -> 500."""
    raw = query_dict()
    data, error = load_query(schema, raw)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:                # bad params
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:                # upstream rejected the request
        return json_response({"error": f"seek rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                 # retries exhausted / blocked
        return json_response({"error": f"seek {path.strip('/')} failed: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, raw)
    return json_response(result)


ENDPOINTS = [
    # jobs
    ("/jobs/details", schemas.JobSchema, jobs.details, False),
    ("/jobs/search", schemas.JobSearchSchema, jobs.search, True),
    ("/jobs/batch", schemas.JobBatchSchema, jobs.batch, False),
    # companies
    ("/companies/details", schemas.CompanySchema, companies.details, False),
    ("/companies/reviews", schemas.CompanyReviewsSchema, companies.reviews, True),
    ("/companies/salaries", schemas.CompanySchema, companies.salaries, False),
    ("/companies/jobs", schemas.CompanyJobsSchema, companies.open_jobs, True),
    ("/companies/search", schemas.CompanySearchSchema, companies.search, False),
    # career guide
    ("/roles/details", schemas.RoleSchema, careers.details, False),
    ("/roles/search", schemas.RoleSearchSchema, careers.search, True),
    ("/roles/reviews", schemas.RoleReviewsSchema, careers.reviews, True),
    # lookups
    ("/autocomplete", schemas.AutocompleteSchema, lookups.autocomplete, False),
    ("/companies/industries", schemas.CountrySchema, companies.industries, False),
    ("/companies/directory", schemas.DirectorySchema, companies.directory, True),
    ("/classifications", schemas.EmptySchema, lookups.classifications, False),
    ("/countries", schemas.EmptySchema, lookups.countries, False),
]


def mount(path, schema, impl, paginated):
    """Serve one endpoint at /path and /seek/path."""
    def handler():
        return call(path, schema, impl, paginated)
    handler.__name__ = "seek_" + path.strip("/").replace("/", "_")
    route(path, method="GET")(handler)
    route("/seek" + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
