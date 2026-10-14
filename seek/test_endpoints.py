"""Live endpoint smoke tests: one call per /seek/* route against a running
service, with example values proven to return data (2026-10-14). The
listing tooling (derive_facts.py) reads each route's FIRST call from this
file's AST as its working example, so the values stay literals.

Skipped unless SEEK_BASE points at a running service:

    SCRAPERS_PORT=6071 ONLY_SCRAPER=seek python run.py
    SEEK_BASE=http://127.0.0.1:6071 python -m pytest seek/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("SEEK_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set SEEK_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_job_search():
    body = call("/seek/jobs/search", query="python developer", location="Sydney NSW")
    assert body["count"] > 50 and len(body["jobs"]) == 20 and body["next"]
    job = body["jobs"][0]
    assert job["id"].isdigit() and job["title"] and job["link"].startswith("https://www.seek.com.au/job/")
    assert job["classifications"] and job["listed_at"] and body["facets"]["work_types"]
    page2 = call("/seek/jobs/search", query="python developer", location="Sydney NSW", page=2)
    assert page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    body = call("/seek/jobs/search", query="nurse", country="NZ", work_type="full_time", date_range="last_30_days",
                sort="date", page_size=5)
    assert body["jobs"] and all(j["link"].startswith("https://www.seek.co.nz/") for j in body["jobs"])
    assert all(w["value"] == "full_time" for j in body["jobs"] for w in j["work_types"])
    body = call("/seek/jobs/search", query="engineer", classification="Information & Communication Technology",
                work_arrangement="remote", salary_min=120000, page_size=5)
    assert body["jobs"] and all(c["id"] == "6281" for j in body["jobs"] for c in j["classifications"])
    assert status("/seek/jobs/search", query="nurse", page=30, page_size=22) == 400


def test_job_details():
    listing = call("/seek/jobs/search", query="registered nurse", location="Melbourne VIC", page_size=1)
    job_id = listing["jobs"][0]["id"]
    body = call("/seek/jobs/details", job=f"https://www.seek.com.au/job/{job_id}")
    assert body["id"] == job_id and body["description_html"] and body["description_text"]
    assert body["classification"]["id"] and body["location"]["country_code"] == "AU" and body["advertiser"]["name"]
    assert body["apply"]["link"].endswith(f"/job/{job_id}/apply") and body["listed_at"]
    assert status("/seek/jobs/details", job="1") == 404
    assert status("/seek/jobs/details", job="abc") == 400


def test_job_batch():
    listing = call("/seek/jobs/search", query="accountant", page_size=3)
    ids = sorted({j["id"] for j in listing["jobs"]})      # sponsored cards can repeat an id
    body = call("/seek/jobs/batch", jobs=",".join(ids + ["1"]))
    assert body["count"] == len(ids) and body["errors"] == {"1": "not found"}


def test_company_search_and_details():
    body = call("/seek/companies/search", query="Atlassian")
    assert body["companies"][0]["name"] == "Atlassian" and body["companies"][0]["id"] == "437216"
    body = call("/seek/companies/details", company="Atlassian")
    assert body["id"] == "437216" and body["industry"]["name"] and body["ratings"]["review_count"] > 5
    assert body["description"] and body["link"] == "https://www.seek.com.au/companies/atlassian-437216"
    body = call("/seek/companies/details", company="https://www.seek.co.nz/companies/air-new-zealand-171714173960985")
    assert body["name"] == "Air New Zealand" and body["link"].startswith("https://www.seek.co.nz/")
    assert status("/seek/companies/details", company="zzqqxx nonexistent corp") == 404


def test_company_reviews_salaries_jobs():
    body = call("/seek/companies/reviews", company="subway-432301", page_size=5)
    assert body["count"] > 500 and len(body["reviews"]) == 5 and body["reviews"][0]["created_at"]
    assert body["reviews"][0]["rating"] and body["company"]["rating"]
    body = call("/seek/companies/reviews", company="432301", location="Melbourne", page_size=5)
    assert body["reviews"] and all("Melbourne" in (r["work_location"] or "") or " VIC" in (r["work_location"] or "")
                                   for r in body["reviews"])
    body = call("/seek/companies/salaries", company="Subway")
    assert body["count"] > 0 and body["roles"][0]["company"]["min"] and body["last_updated"]
    body = call("/seek/companies/jobs", company="Subway", page_size=5)
    assert body["count"] > 10 and body["jobs"] and body["company"]["organisation_id"] == "3009"
    assert all(j["company"]["id"] == "432301" for j in body["jobs"])


def test_company_directory():
    body = call("/seek/companies/industries")
    assert body["count"] >= 70 and body["industries"][0]["category"]["name"]
    body = call("/seek/companies/directory", industry="Information Technology Services", page_size=10)
    assert body["count"] > 200 and len(body["companies"]) == 10 and body["industry"]["id"] == "I0050"
    assert status("/seek/companies/directory", industry="no-such-industry") == 404


def test_roles():
    body = call("/seek/roles/search", query="nurse")
    assert body["count"] > 10 and body["roles"][0]["alias"] and body["roles"][0]["typical_salary"]
    body = call("/seek/roles/details", role="Software Engineer")
    assert body["alias"] == "software-engineer" and body["salary"]["typical"]["min"] > 50000
    assert body["skills"]["experience"] and body["salary"]["by_location"] and body["tasks_and_duties"]
    nz = call("/seek/roles/details", role="software-engineer", country="NZ")
    assert nz["salary"]["currency"] == "NZD" and nz["link"].startswith("https://www.seek.co.nz/")
    body = call("/seek/roles/reviews", role="software-engineer", page_size=5)
    assert body["count"] > 50 and len(body["reviews"]) == 5 and body["reviews"][0]["good_things"]
    assert status("/seek/roles/details", role="zzqx-no-role") == 404


def test_lookups():
    body = call("/seek/autocomplete", query="melb")
    assert body["locations"][0]["id"] and "Melbourne" in body["locations"][0]["name"]
    body = call("/seek/autocomplete", query="data sci", type="keywords", country="NZ")
    assert body["keywords"][0]["name"].startswith("Data Sci")
    body = call("/seek/classifications")
    assert body["count"] == 30
    body = call("/seek/countries")
    assert [c["code"] for c in body["countries"]] == ["AU", "NZ"]
    assert status("/seek/jobs/search", query="x", bogus=1) == 400
