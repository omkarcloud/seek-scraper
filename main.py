"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from seek.companies import details as company_details
from seek.jobs import details as job_details
from seek.jobs import search as search_jobs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a job id or any seek.com.au / seek.co.nz job link
    save("job_95216242.json", job_details("95216242"))

    # 20 jobs per page; country "AU" (seek.com.au) or "NZ" (seek.co.nz)
    save("search_software_engineer_sydney.json", search_jobs("software engineer", "Sydney NSW", "AU"))

    # a company id, a /companies/ link or a name
    save("company_apple.json", company_details({"id": None, "slug": None, "name": "Apple", "country": None}))
