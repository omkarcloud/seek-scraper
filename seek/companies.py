"""/seek/companies/* — company name search, profiles, employee reviews,
salary ranges by role, open jobs, and the company directory.

A `company` param arrives resolved by refs.resolve_company: a company id
(the number on every /companies/<name>-<id> link), or a name that is looked
up through the site's own company search here (first hit)."""
import re

from seek import cache_config as ttl
from seek import fetch, gql, jobs as J
from seek import parsers as P
from seek.shared import site

COMPANY_LIMIT_MAX = 20


def _zone(country):
    return site(country)["zone"]


def _locale(country):
    return site(country)["locale"]


def search(query, country="AU", limit=10):
    """Companies whose profile name matches `query` (Seek's own name search)."""
    variables = {"name": query, "includeBranding": True, "limit": limit, "zone": _zone(country), "published": True}
    raw = fetch.graphql(gql.COMPANY_SEARCH, variables, country, label=f"company search {query!r}",
                        operation="SearchCompanies")
    return P.company_search(raw, country)


def resolve_id(company, country="AU"):
    """A resolved `company` ref -> its company id (a name is looked up on
    the site: first search hit, memoised + cached)."""
    if company.get("id"):
        return company["id"]
    name = company["name"]

    def build():
        hits = search(name, country, limit=5)["companies"]
        exact = [c for c in hits if (c.get("name") or "").lower() == name.lower()]
        hit = (exact or hits or [None])[0]
        if not hit:
            raise fetch.SeekNotFound(f"Seek has no company profile named {name!r}")
        return hit["id"]
    return fetch.shared_raw("company_lookup", {"name": name.lower(), "country": country}, build,
                            ttl.COMPANY_LOOKUP_CACHE)


def organisation(company_id, country="AU"):
    """{id, organisation_id, name, slug} of a company id (the organisation id
    is what the job-search API's company filter takes)."""
    def build():
        raw = fetch.graphql(gql.COMPANY_ORGANISATION, {"companyId": company_id}, country,
                            label=f"company {company_id}", operation="GetCompanyOrganisation")
        info = P.company_organisation(raw)
        if not info:
            raise fetch.SeekNotFound(f"Seek has no company profile with the id {company_id}")
        return info
    return fetch.shared_raw("company_organisation", {"id": company_id, "country": country}, build,
                            ttl.COMPANY_ORGANISATION_CACHE)


def details(company, country="AU"):
    """The full company profile with its ratings summary, AI review
    summary and the locations reviews come from."""
    company_id = resolve_id(company, company.get("country") or country)
    country = company.get("country") or country
    variables = {"companyId": company_id, "profileId": company_id, "zone": _zone(country), "locale": _locale(country)}
    raw = fetch.graphql(gql.COMPANY_DETAILS, variables, country, label=f"company {company_id}",
                        operation="GetCompanyDetails")
    result = P.company_details(raw, country, company_id)
    if result is None:
        raise fetch.SeekNotFound(f"Seek has no company profile with the id {company_id}")
    try:
        jobs = fetch.search_api({"companyid": result.get("organisation_id"), "pagesize": 1, "include": "nofeatured"},
                                country, label=f"company {company_id} jobs count") if result.get("organisation_id") else None
        result["jobs_count"] = (jobs or {}).get("totalCount") if jobs else None
    except fetch.SeekUpstreamError as e:
        print(f"seek: jobs count for company {company_id} skipped: {e}")
        result["jobs_count"] = None
    return result


def _location_id(location, country):
    """A review-location text ('All Melbourne VIC', 'Sydney') -> Seek location id."""
    if not location:
        return None
    if str(location).isdigit():
        return str(location)
    from seek import lookups
    # reviews are keyed on areas ("All Melbourne VIC"), never on suburbs
    hits = lookups.locations(location, country, limit=1, kinds=lookups.AREA_KINDS)["locations"]
    if not hits or hits[0].get("id") is None:
        raise fetch.SeekBadRequest(f"Seek knows no location matching {location!r}")
    return str(hits[0]["id"])


def reviews(company, country="AU", page=1, page_size=20, location=None):
    """One page of employee reviews (newest first) with the rating summary."""
    country = company.get("country") or country
    company_id = resolve_id(company, country)
    variables = {"companyId": company_id, "profileId": company_id, "zone": _zone(country), "locale": _locale(country),
                 "page": page, "perPage": page_size, "sort": "", "locationId": _location_id(location, country)}
    raw = fetch.graphql(gql.COMPANY_REVIEWS, variables, country, label=f"reviews {company_id} p{page}",
                        operation="CompanyReviews")
    result = P.company_reviews(raw, country, company_id, page, page_size)
    if result is None:
        raise fetch.SeekNotFound(f"Seek has no company profile with the id {company_id}")
    return result


def salaries(company, country="AU"):
    """Salary range per role at the company versus its industry."""
    country = company.get("country") or country
    company_id = resolve_id(company, country)
    raw = fetch.graphql(gql.COMPANY_SALARIES, {"companyId": company_id, "locale": _locale(country)}, country,
                        label=f"company salaries {company_id}", operation="GetCompanySalaryRange")
    result = P.company_salaries(raw, country, company_id)
    if result is None:
        raise fetch.SeekNotFound(f"Seek has no company profile with the id {company_id}")
    return result


def open_jobs(company, country="AU", query=None, page=1, page_size=20, sort=None):
    """The company's live job ads (the job-search API scoped to its organisation)."""
    country = company.get("country") or country
    company_id = resolve_id(company, country)
    info = organisation(company_id, country)
    if not info.get("organisation_id"):
        raise fetch.SeekNotFound(f"Seek lists no jobs for the company {company_id}")
    params = J.search_params(query=query, page=page, page_size=page_size, sort=sort,
                             organisation=info["organisation_id"], facets=False)
    params["include"] = "nofeatured"
    raw = fetch.search_api(params, country, label=f"company jobs {company_id} p{page}")
    result = P.search_result(raw, country, page, page_size)
    result.pop("location", None)
    result.pop("location_suggestions", None)
    result.pop("related_searches", None)
    result.pop("facets", None)
    return {"company": dict(info, link=P.S.company_link(country, info.get("slug") or company_id)), **result}


def industries(country="AU"):
    """The company directory's industries, grouped by category."""
    html = fetch.page("/companies/directory", country, label="company directory")
    return P.directory_industries(html, country)


def directory(industry, country="AU", page=1, page_size=50):
    """One page of the companies listed under a directory industry."""
    try:
        html = fetch.page(f"/companies/directory/{industry}", country, label=f"directory {industry}")
    except fetch.SeekNotFound:
        raise fetch.SeekNotFound(f"Seek's company directory has no industry {industry!r} (see /seek/companies/industries)")
    loader = fetch.hydration_data(html)
    result = P.directory_companies(loader, html, country, industry, page, page_size)
    if result is None:
        raise fetch.SeekNotFound(f"Seek's company directory has no industry {industry!r}")
    return result
