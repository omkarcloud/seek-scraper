"""/seek/jobs/* — job search, job details and batch lookup, from Seek's
job-search API (fetch.search_api) and the chalice GraphQL (jobDetails)."""
from seek import fetch, gql, refdata
from seek import parsers as P

MAX_BATCH = 10


def search_params(query=None, location=None, page=1, page_size=20, sort=None, date_range=None, work_type=None,
                  work_arrangement=None, classification=None, subclassification=None, salary_min=None,
                  salary_max=None, salary_type=None, distance=None, advertiser=None, organisation=None,
                  facets=True):
    """Public params -> the search API's own query (Seek's names and ids)."""
    params = {
        "keywords": query,
        "page": page,
        "pageSize": page_size,
        "sortmode": sort,
        "daterange": date_range,
        "worktype": ",".join(work_type) if work_type else None,
        "workarrangement": ",".join(work_arrangement) if work_arrangement else None,
        "classification": ",".join(classification) if classification else None,
        "subclassification": ",".join(subclassification) if subclassification else None,
        "distance": distance,
        "advertiserid": advertiser,
        "companyid": organisation,
        "include": "seodata,relatedsearches",
        "facets": refdata.SEARCH_FACETS if facets else None,
    }
    if location:
        if str(location).isdigit():
            params["whereid"] = location
        else:
            params["where"] = location
    if salary_min is not None or salary_max is not None:
        params["salaryrange"] = f"{salary_min or ''}-{salary_max or ''}"
        params["salarytype"] = salary_type or "annual"
    return params


def search(query=None, location=None, country="AU", page=1, page_size=20, sort=None, date_range=None,
           work_type=None, work_arrangement=None, classification=None, subclassification=None, salary_min=None,
           salary_max=None, salary_type=None, distance=None, advertiser=None):
    """One page of job cards with Seek's facets, related searches and the
    resolved location. `sort` / `date_range` / `work_type` / ... arrive as
    Seek's own tokens (the schema maps the public values)."""
    params = search_params(query, location, page, page_size, sort, date_range, work_type, work_arrangement,
                           classification, subclassification, salary_min, salary_max, salary_type, distance,
                           advertiser)
    raw = fetch.search_api(params, country, label=f"job search {query!r} p{page}")
    result = P.search_result(raw, country, page, page_size)
    result["query"] = query
    return result


def details_raw(job_id, country):
    variables = dict(fetch.standard_variables(country), jobId=job_id)
    return fetch.graphql(gql.JOB_DETAILS, variables, country, label=f"job {job_id}", operation="jobDetails")


def details(job, country="AU"):
    """The full job ad: description, bullets, screening questions, applicant
    counts, salary, advertiser, employer profile. 404 when Seek has no such
    job (expired ads still come back, flagged is_expired)."""
    raw = details_raw(job, country)
    result = P.job_details(raw, country)
    if result is None:
        raise fetch.SeekNotFound(f"Seek has no job with the id {job}")
    return result


def batch(jobs, country="AU"):
    """Up to MAX_BATCH jobs by id / link, fetched in parallel. Jobs Seek no
    longer has are listed under `errors` instead of failing the call."""
    import config
    results = fetch.run_parallel([lambda j=j: details(j, country) for j in jobs], config.SEEK_BATCH_WORKERS)
    out, errors = [], {}
    for job_id, (status, value) in zip(jobs, results):
        if status == "ok":
            out.append(value)
        elif isinstance(value, fetch.SeekNotFound):
            errors[job_id] = "not found"
        else:
            raise value
    return {"jobs": out, "count": len(out), "errors": errors or None}
