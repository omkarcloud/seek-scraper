"""Offline tests: refs resolvers, marshmallow schemas, value helpers, parsers
and the endpoint functions with the transport monkeypatched to serve
fixtures (seek/fixtures/*.json.gz, raw payloads captured 2026-10-14) — no
network.

    python -m pytest seek/test_parsers.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seek import (careers, companies, fetch, jobs, lookups, parsers as P, refs,  # noqa: E402
                  schemas, shared as S)
from schema_fields import load_query  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    with gzip.open(os.path.join(FX, name + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


# ---- refs ------------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("AU", "AU"), ("au", "AU"), ("Australia", "AU"), ("nz", "NZ"), ("New Zealand", "NZ"),
    ("seek.co.nz", "NZ"), ("https://www.seek.com.au/jobs?keywords=x", "AU"), ("https://nz.seek.com/job/1", "NZ"),
])
def test_resolve_country(value, expected):
    assert refs.resolve_country(value) == expected


@pytest.mark.parametrize("value", ["", "US", "Atlantis", "https://example.com/x"])
def test_resolve_country_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_country(value)


@pytest.mark.parametrize("value", [
    "94722577", "https://www.seek.com.au/job/94722577?type=promoted", "https://au.seek.com/job/94722577",
    "www.seek.co.nz/job/94722577/apply", "https://www.seek.com.au/job/94722577#sol=abc",
])
def test_resolve_job(value):
    assert refs.resolve_job(value) == "94722577"


@pytest.mark.parametrize("value", ["", "abc", "https://www.seek.com.au/jobs?keywords=x", "https://example.com/job/1"])
def test_resolve_job_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_job(value)


@pytest.mark.parametrize("value,expected", [
    ("432301", {"id": "432301", "slug": None, "name": None, "country": None}),
    ("subway-432301", {"id": "432301", "slug": "subway-432301", "name": None, "country": None}),
    ("https://www.seek.com.au/companies/subway-432301/reviews?page=2",
     {"id": "432301", "slug": "subway-432301", "name": None, "country": "AU"}),
    ("https://www.seek.co.nz/companies/air-new-zealand-171714173960985",
     {"id": "171714173960985", "slug": "air-new-zealand-171714173960985", "name": None, "country": "NZ"}),
    ("Bank of  Queensland", {"id": None, "slug": None, "name": "Bank of Queensland", "country": None}),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


@pytest.mark.parametrize("value", ["", "https://www.seek.com.au/companies/directory/construction",
                                   "https://example.com/companies/x-1"])
def test_resolve_company_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


@pytest.mark.parametrize("value,expected", [
    ("software-engineer", {"alias": "software-engineer", "title": None}),
    ("Software Engineer", {"alias": None, "title": "Software Engineer"}),
    ("https://www.seek.com.au/career-advice/role/software-engineer/salary", {"alias": "software-engineer", "title": None}),
])
def test_resolve_role(value, expected):
    assert refs.resolve_role(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("information-technology-services", "information-technology-services"),
    ("Information Technology Services", "information-technology-services"),
    ("Architectural & Design Services", "architectural-n-design-services"),
    ("https://www.seek.com.au/companies/directory/building-supplies", "building-supplies"),
])
def test_resolve_industry(value, expected):
    assert refs.resolve_industry(value) == expected


# ---- schemas ---------------------------------------------------------------------------------------

def test_job_search_schema_maps_filters():
    data, error = load_query(schemas.JobSearchSchema, {
        "query": "nurse", "location": "Melbourne VIC", "country": "nz", "sort": "date", "date_range": "last_7_days",
        "work_type": "full_time,casual", "work_arrangement": "remote", "classification": "Healthcare & Medical,6281",
        "subclassification": "6290", "salary_min": "80000", "salary_max": "120000", "salary_type": "Annual",
        "distance": "25", "advertiser": "49879715", "page": "2", "page_size": "50"})
    assert error is None
    assert data["country"] == "NZ" and data["sort"] == "ListedDate" and data["date_range"] == "7"
    assert data["work_type"] == ["242", "245"] and data["work_arrangement"] == ["3"]
    assert data["classification"] == ["1211", "6281"] and data["subclassification"] == ["6290"]
    assert data["salary_min"] == 80000 and data["salary_type"] == "annual" and data["page_size"] == 50


@pytest.mark.parametrize("query,field", [
    ({"page": "30", "page_size": "22"}, "page"),
    ({"salary_min": "100", "salary_max": "50"}, "salary_max"),
    ({"classification": "Astrology"}, "classification"),
    ({"work_type": "weekend"}, "work_type"),
    ({"advertiser": "acme"}, "advertiser"),
    ({"bogus": "1"}, "bogus"),
    ({"page_size": "101"}, "page_size"),
])
def test_job_search_schema_rejects(query, field):
    data, error = load_query(schemas.JobSearchSchema, query)
    assert data is None and field in error["errors"]


def test_batch_schema():
    data, error = load_query(schemas.JobBatchSchema, {"jobs": "94722577, https://www.seek.com.au/job/80000000,94722577"})
    assert error is None and data["jobs"] == ["94722577", "80000000"]
    data, error = load_query(schemas.JobBatchSchema, {"jobs": ",".join(str(i) for i in range(11))})
    assert data is None and "jobs" in error["errors"]


def test_company_and_role_schemas():
    data, error = load_query(schemas.CompanyReviewsSchema, {"company": "subway-432301", "page": "3", "location": "Melbourne"})
    assert error is None and data["company"]["id"] == "432301" and data["page"] == 3 and data["page_size"] == 20
    data, error = load_query(schemas.RoleSearchSchema, {"query": "nurse", "sort": "salary"})
    assert error is None and data["sort"] == "SALARY" and data["page_size"] == 10
    data, error = load_query(schemas.AutocompleteSchema, {"query": "melb", "type": "Keywords"})
    assert error is None and data["type"] == "keywords"
    data, error = load_query(schemas.DirectorySchema, {"industry": "Information Technology Services"})
    assert error is None and data["industry"] == "information-technology-services"


# ---- value helpers ----------------------------------------------------------------------------------

@pytest.mark.parametrize("label,low,high,period", [
    ("$160,000 to $200,000 + super", 160000, 200000, "yearly"),
    ("$74K - $95K", 74000, 95000, "yearly"),
    ("$45 – $50 per hour", 45, 50, "hourly"),
    ("Up to $120k", None, 120000, "yearly"),
    ("$1,100 per day", 1100, 1100, "daily"),
    ("From $90k", 90000, None, "yearly"),
    ("Competitive salary", None, None, None),
])
def test_salary_from_label(label, low, high, period):
    out = S.salary_from_label(label, "AUD")
    assert (out["min"], out["max"], out["period"], out["currency"]) == (low, high, period, "AUD")


def test_salary_from_label_empty():
    assert S.salary_from_label("", "AUD") is None and S.salary_from_label(None, "AUD") is None


def test_html_to_text():
    out = S.html_to_text("<p>Hello <b>world</b></p><ul><li>a</li><li>b</li></ul>x &amp; y<br>z<script>no()</script>")
    assert out == "Hello world\n- a\n- b\n\nx & y\nz"
    assert S.html_to_text("plain") == "plain" and S.html_to_text(None) is None


def test_iso_datetime_and_ids():
    assert S.iso_datetime({"dateTimeUtc": "2026-09-18T04:30:49.433Z"}) == "2026-09-18T04:30:49Z"
    assert S.iso_date("21 Sep 2026") == "2026-09-21"
    assert S.seek_id("seek-16351") == 16351 and S.seek_id(16351) == 16351 and S.seek_id(None) is None
    assert S.company_slug_id("subway-432301") == ("subway", "432301")


# ---- parsers: jobs ----------------------------------------------------------------------------------------

def test_search_result():
    out = P.search_result(fx("search_au"), "AU", 1, 20)
    assert out["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 14, "total_count": 275}
    assert out["location"]["id"] == 16351 and out["location"]["type"] == "suburb"
    assert out["facets"]["work_types"][0]["value"] == "full_time" and out["facets"]["locations"][0]["id"] == 3101
    assert out["related_searches"][0]["keywords"] == "python" and out["related_searches"][0]["location"]["id"] == 16351
    job = out["jobs"][0]
    assert job["id"] == "94722577" and job["link"] == "https://www.seek.com.au/job/94722577"
    assert job["is_sponsored"] and job["ad_type"] == "sponsored" and job["listed_at"] == "2026-09-18T04:30:49Z"
    assert job["classifications"][0]["subclassification"] == {"id": "6290", "name": "Engineering - Software"}
    assert job["work_arrangements"] == [{"value": "hybrid", "label": "Hybrid"}]
    assert job["recruiter"]["name"] == "Reece Richardson" and job["tags"][0]["type"] == "expires_soon"
    assert "solMetadata" not in json.dumps(out) and "tracking" not in job


def test_search_result_cap_and_empty():
    big = dict(fx("search_au"), totalCount=9152)
    out = P.search_result(big, "AU", 1, 100)
    assert out["pagination"]["total_pages"] == 6 and out["results_limit"] == 550
    out = P.search_result(fx("search_empty"), "AU", 1, 5)
    assert out["jobs"] == [] and out["pagination"]["total_pages"] == 0 and out["facets"] is None


def test_search_card_nz_salary_and_company_link():
    job = P.job_card(fx("search_nz")["data"][0], "NZ")
    assert job["link"].startswith("https://www.seek.co.nz/job/") and job["salary"]["currency"] == "NZD"
    assert job["salary"]["period"] == "hourly" and job["work_types"][0]["value"] == "casual"
    job = P.job_card(fx("search_company")["data"][0], "AU")
    assert job["company"] == {"id": "432301", "name": "Subway", "link": "https://au.seek.com/companies/subway-432301",
                              "logo": None}


def test_job_details():
    job = P.job_details(fx("job_details"), "AU")
    assert job["title"] == "Senior AI Engineer (LLM /GenAI)" and job["status"] == "active" and not job["is_expired"]
    assert job["description_text"].startswith("We're working with") and "<" not in job["description_text"]
    assert job["applicants"] == {"count": 331, "count_label": "More than 150 applicants",
                                 "volume_label": "High application volume", "with_resume_percent": 100,
                                 "with_cover_letter_percent": 48}
    assert job["work_arrangement"]["value"] == "hybrid" and job["work_type"]["value"] == "full_time"
    assert job["classification"]["id"] == "6281" and job["classification"]["subclassification"]["name"] == "Engineering - Software"
    assert job["location"]["postcode"] == "2000" and job["location"]["state"] == "New South Wales"
    assert job["screening_questions"] and job["apply"]["link"].endswith("/job/94722577/apply")
    assert job["advertiser"]["registered_at"] == "2021-07-13T01:23:42Z" and job["advertiser"]["is_verified"]
    assert job["recruiter"]["rating"] == 4.98 and job["expires_at"] == "2026-10-18T03:30:00Z"
    assert job["branding"]["logo"] and job["company"] is None


def test_job_details_company_expired_missing():
    job = P.job_details(fx("job_details_company"), "AU")
    assert job["company"]["id"] == "432301" and job["company"]["review_count"] == 583
    assert job["company"]["link"] == "https://www.seek.com.au/companies/subway-432301"
    assert job["badges"] == ["responsive_hirer", "onsite"] and job["work_arrangement"]["value"] == "on_site"
    expired = P.job_details(fx("job_details_expired"), "AU")
    assert expired["is_expired"] and expired["status"] == "expired" and expired["expired_at"]
    assert P.job_details(fx("job_details_missing"), "AU") is None
    nz = P.job_details(fx("job_details_nz"), "NZ")
    assert nz["link"].startswith("https://www.seek.co.nz/job/") and nz["location"]["country_code"] == "NZ"


# ---- parsers: companies ---------------------------------------------------------------------------------------

def test_company_search():
    out = P.company_search(fx("company_search"), "AU")
    assert out["companies"][0] == {"id": "437216", "organisation_id": "1913", "name": "Atlassian",
                                   "slug": "atlassian-437216",
                                   "link": "https://www.seek.com.au/companies/atlassian-437216",
                                   "logo": "https://image-service-cdn.seek.com.au/6acd9349d0004a04ee96e6025a0769806fa01c74",
                                   "rating": 2.6, "review_count": 12, "is_published": True}


def test_company_details():
    out = P.company_details(fx("company_details"), "AU", "432301")
    assert out["name"] == "Subway" and out["organisation_id"] == "3009" and out["slug"] == "subway-432301"
    assert out["industry"] == {"id": "I0033", "name": "Fast Food/Takeaway Outlets"} and out["size"] == "1,001-5,000"
    assert out["ratings"]["overall"] == 3.1 and out["ratings"]["review_count"] == 583
    assert out["ratings"]["recommended_percent"] == 55 and out["ratings"]["distribution"]["5"] == 125
    assert out["ratings"]["categories"]["work_life_balance"] == {"rating": 3.3, "count": 582}
    assert out["ratings"]["salary"] == {"poor_percent": 42, "fair_percent": 51, "generous_percent": 7}
    assert out["review_summary"]["reviews_count"] == 30 and "<strong>" not in out["review_summary"]["text"]
    assert out["review_locations"][0]["link"] == "https://www.seek.com.au/companies/subway-432301/reviews/locations/All-Adelaide-SA"
    atl = P.company_details(fx("company_details_atlassian"), "AU", "437216")
    assert atl["is_claimed"] and atl["specialities"] == ["b2b enterprise software", "bug tracker"]
    assert atl["graduates"]["link"].startswith("https://www.atlassian.com") and atl["traditional_land"] == "Gadigal Country"


def test_company_reviews():
    out = P.company_reviews(fx("company_reviews"), "AU", "432301", 1, 20)
    assert out["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 30, "total_count": 583}
    assert out["company"]["rating"] == 3.1 and len(out["reviews"]) == 20
    review = out["reviews"][1]
    assert review["created_at"] == "2026-07-14" and review["is_recommended"] is False and review["rating"] == 2.0
    assert review["ratings"]["work_life_balance"] == 3.0 and review["salary_summary"] == "Low"
    assert review["employment_status"] == "2 to 3 years in the role, former employee"


def test_company_salaries_and_organisation():
    out = P.company_salaries(fx("company_salaries"), "AU", "432301")
    assert out["last_updated"] == "2026-10-02" and out["count"] == len(out["roles"]) > 0
    role = out["roles"][0]
    assert role["company"]["min"] == 74000 and role["company"]["max"] == 95000 and role["company"]["jobs_count"] == 1
    assert role["company"]["currency"] == "AUD" and role["company"]["period"] == "yearly"
    assert P.company_organisation(fx("company_organisation")) == {"id": "432301", "organisation_id": "3009",
                                                                   "name": "Subway", "slug": "subway-432301"}
    # an unknown company id (live shape, 2026-10-14): no profile, no roles -> not found
    missing = {"companyDetails": {"id": "999999", "companyProfile": None,
                                  "companySalaryRange": {"lastUpdatedAt": {"shortAbsoluteLabel": "2 Oct 2026"},
                                                         "salaryRangeByRoles": []}}}
    assert P.company_salaries(missing, "AU", "999999") is None


def test_graphql_not_found_domain_error():
    """data: null + a DOMAIN_ERROR 'CompanyDetails not found' (what chalice
    answers for an unknown company id) is a 404, not a retried 502."""
    class Resp:
        status_code, headers = 200, {}
        text = json.dumps({"data": None, "errors": [{"message": "CompanyDetails not found",
                                                      "extensions": {"kind": "domain_error", "code": "DOMAIN_ERROR"}}]})
    with pytest.raises(fetch.SeekNotFound):
        fetch._graphql_data(Resp(), "company 999999")
    Resp.text = json.dumps({"data": None, "errors": [{"message": "upstream timeout", "extensions": {"code": "INTERNAL"}}]})
    with pytest.raises(fetch.SeekUpstreamError):
        fetch._graphql_data(Resp(), "company 432301")


def test_directory():
    out = P.directory_industries(fx("directory_home_html")["html"], "AU")
    assert out["count"] >= 70 and out["industries"][0]["slug"] == "architectural-n-design-services"
    assert out["industries"][0]["category"]["name"] == "Construction, Design & Engineering"
    assert sum(c["industry_count"] for c in out["categories"]) == out["count"]
    html = fx("directory_industry_html")["html"]
    out = P.directory_companies(fetch.hydration_data(html), html, "AU", "information-technology-services", 2, 50)
    assert out["industry"] == {"id": "I0050", "slug": "information-technology-services",
                               "name": "Information Technology Services",
                               "link": "https://www.seek.com.au/companies/directory/information-technology-services"}
    assert out["pagination"]["total_count"] == 301 and out["pagination"]["total_pages"] == 7
    assert len(out["companies"]) == 50 and out["companies"][0]["link"].startswith("https://www.seek.com.au/companies/")
    assert isinstance(out["companies"][0]["has_reviews"], bool)
    assert P.directory_companies({}, "", "AU", "x", 1, 50) is None


# ---- parsers: suggestions + careers -------------------------------------------------------------------------

def test_suggestions():
    assert P.location_suggestions(fx("location_suggest"), 2) == [
        {"id": 16351, "name": "Sydney NSW 2000", "country_code": "AU"},
        {"id": 16352, "name": "Sydney Olympic Park NSW 2127", "country_code": "AU"}]
    assert P.keyword_suggestions(fx("keyword_suggest"), 1) == [{"id": "python-developer", "name": "Python Developer"}]


def test_role_details():
    out = P.role_details(fx("role"), fx("role_salaries"), "AU")
    assert out["alias"] == "software-engineer" and out["link"].endswith("/career-advice/role/software-engineer")
    assert out["salary"]["typical"] == {"min": 105000, "max": 125000} and out["salary"]["currency"] == "AUD"
    assert out["salary"]["national"]["median"] == 107410 and out["salary"]["national"]["location"] == "Australia"
    states = [l for l in out["salary"]["by_location"] if l["location"]["type"] == "state"]
    assert states[0]["location"]["name"] == "Australian Capital Territory" and states[0]["median"] == 121250
    assert out["salary"]["by_classification"][0]["classification"]["id"] == "6281"
    assert "Software Development" in out["skills"]["experience"]
    assert out["growth"]["percent"] == 27 and out["growth"]["source"]["organisation"] == "National Skills Commission"
    assert out["review_statistics"]["job_satisfaction"] == 4.1 and out["review_statistics"]["review_count"] == 122
    assert out["review_statistics"]["working_hours"]["overtime_percent"]["sometimes"] == 61.5
    assert len(out["tasks_and_duties"]) >= 3 and out["how_to_become"]["steps"]
    assert out["similar_roles"][0]["alias"] and out["pathway_roles"][0]["alias"]
    assert out["classifications"][0]["subclassification"]["name"] == "Engineering - Software"
    nz = P.role_details(fx("role_nz"), fx("role_salaries_nz"), "NZ")
    assert nz["salary"]["currency"] == "NZD" and nz["salary"]["by_location"][0]["location"]["name"] == "Auckland"
    assert P.role_details(fx("role_missing"), {}, "AU") is None


def test_role_reviews_and_search():
    out = P.role_reviews(fx("role_reviews"), "AU", "software-engineer", 1, 10)
    assert out["pagination"]["total_count"] == 115 and out["pagination"]["total_pages"] == 12
    review = out["reviews"][0]
    assert review["rating"] == 4.0 and review["submitted_at"] == "2023-08-08T07:01:54Z"
    assert review["reviewer"]["organisation_size"] == "Large (200+ employees)" and review["good_things"]
    out = P.role_search(fx("role_search"), "AU", 1, 10)
    assert out["pagination"]["total_count"] == 25 and out["roles"][0]["alias"] == "nurse"
    assert out["roles"][0]["video"] == "https://www.youtube.com/watch?v=lP6hDRgDnT0"
    assert out["classifications"][0] == {"name": "Healthcare & Medical", "slug": "healthcare-medical", "count": 27}
    assert P.normalised_role_alias(fx("role_normalise")) == "software-engineer"


# ---- endpoint functions on fixtures (transport monkeypatched) -------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    calls = []

    def search_api(params, country=None, label=""):
        calls.append(("search", dict(params)))
        if params.get("companyid"):
            return fx("search_company")
        return fx("search_au") if (country or "AU") == "AU" else fx("search_nz")

    def graphql(query, variables=None, country=None, label="", operation=None):
        calls.append((operation, dict(variables or {})))
        return {
            "jobDetails": fx("job_details"), "SearchCompanies": fx("company_search"),
            "GetCompanyDetails": fx("company_details"), "CompanyReviews": fx("company_reviews"),
            "GetCompanySalaryRange": fx("company_salaries"), "GetCompanyOrganisation": fx("company_organisation"),
            "MKLocationSuggestions": fx("location_suggest"), "OntologyRoleTitlesSeniority": fx("keyword_suggest"),
        }[operation]

    def career_graphql(query, variables=None, country=None, label="", operation=None):
        calls.append((operation, dict(variables or {})))
        return {"GetRole": fx("role"), "GetRoleSalaries": fx("role_salaries"), "GetRoleReviews": fx("role_reviews"),
                "SearchV2": fx("role_search"), "GetNormalisedRoles": fx("role_normalise")}[operation]

    def page(path, country=None, label=None):
        calls.append(("page", path))
        return fx("directory_industry_html")["html"] if "/directory/" in path else fx("directory_home_html")["html"]

    monkeypatch.setattr(fetch, "search_api", search_api)
    monkeypatch.setattr(fetch, "graphql", graphql)
    monkeypatch.setattr(fetch, "career_graphql", career_graphql)
    monkeypatch.setattr(fetch, "page", page)
    monkeypatch.setattr(fetch, "shared_raw", lambda name, params, build, ttl: build())
    return calls


def test_jobs_endpoints(offline):
    out = jobs.search("python developer", "Sydney NSW", "AU", page=2, page_size=20, sort="ListedDate",
                      work_type=["242"], salary_min=100000)
    sent = offline[-1][1]
    assert sent["keywords"] == "python developer" and sent["where"] == "Sydney NSW" and sent["page"] == 2
    assert sent["sortmode"] == "ListedDate" and sent["worktype"] == "242" and sent["salaryrange"] == "100000-"
    assert sent["salarytype"] == "annual" and out["query"] == "python developer" and len(out["jobs"]) == 20
    jobs.search(location="16351")
    assert offline[-1][1]["whereid"] == "16351" and "where" not in offline[-1][1]
    assert jobs.details("94722577")["id"] == "94722577" and offline[-1][1]["jobId"] == "94722577"
    out = jobs.batch(["94722577", "94722577"])
    assert out["count"] == 2 and out["errors"] is None


def test_companies_endpoints(offline):
    assert companies.search("atlassian")["companies"][0]["id"] == "437216"
    out = companies.details({"id": None, "slug": None, "name": "Atlassian", "country": None})
    assert out["id"] == "432301" and out["jobs_count"] == 88          # fixture-served profile + jobs count
    assert [c for c in offline if c[0] == "SearchCompanies"][-1][1]["name"] == "Atlassian"
    out = companies.reviews({"id": "432301", "slug": None, "name": None, "country": None}, page=1, page_size=20,
                            location="Melbourne")
    assert offline[-1][1]["locationId"] == "16351" and out["pagination"]["total_count"] == 583
    assert companies.salaries({"id": "432301", "slug": None, "name": None, "country": None})["count"] > 0
    out = companies.open_jobs({"id": "432301", "slug": None, "name": None, "country": None}, page_size=20)
    assert offline[-1][1]["companyid"] == "3009" and out["company"]["organisation_id"] == "3009" and out["jobs"]
    assert "facets" not in out
    assert companies.industries()["count"] >= 70
    assert companies.directory("information-technology-services", page=1, page_size=10)["pagination"]["total_count"] == 301


def test_careers_and_lookups(offline):
    out = careers.details({"alias": None, "title": "Software Engineer"})
    assert out["alias"] == "software-engineer" and offline[0][0] == "GetNormalisedRoles"
    assert careers.reviews({"alias": "software-engineer", "title": None}, page=2, page_size=10)["pagination"]["page"] == 2
    assert offline[-1][1]["from"] == 10
    out = careers.search("nurse", page=1, page_size=10, sort="SALARY")
    assert out["query"] == "nurse" and offline[-1][1]["sortBy"] == "SALARY"
    assert lookups.autocomplete("melb", "locations", "AU", 2)["locations"][0]["id"] == 16351
    assert lookups.autocomplete("pyth", "keywords", "NZ", 1)["keywords"][0]["name"] == "Python Developer"
    assert offline[-1][1]["countryCode2"] == "NZ"
    table = lookups.classifications()
    assert table["count"] == 30 and all(c["subclassifications"] for c in table["classifications"])
    assert lookups.countries()["countries"][1]["code"] == "NZ"


def test_hydration_and_apollo_parsing():
    assert fetch.hydration_data("<html>nothing</html>") == {}
    assert fetch.apollo_state("<script>window.__APOLLO_STATE__ = {\"a\": 1};</script>") == {"a": 1}
    assert fetch.hydration_data(fx("directory_industry_html")["html"])["company-directory-industry"]["industryId"] == "I0050"
