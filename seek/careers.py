"""/seek/roles/* — Seek's career guide: role pages (what the job is like,
how to become one, skills, salary by state / city / classification, growth,
review statistics, similar and pathway roles), role reviews and role
search. All from career-guide-api.cloud.seek.com.au (fetch.career_graphql),
country-scoped: AU and NZ carry their own salary figures."""
from seek import cache_config as ttl
from seek import fetch, gql, refdata, refs
from seek import parsers as P

SPEC_REQ_INPUT = {"types": refdata.SPEC_REQ_TYPES, "size": 30}


def resolve_alias(role, country="AU"):
    """A resolved `role` ref -> the career guide alias. A free-text title
    goes through Seek's role normaliser (memoised + cached), then the role
    search, then a plain slug."""
    if role.get("alias"):
        return role["alias"]
    title = role["title"]

    def build():
        raw = fetch.career_graphql(gql.ROLE_NORMALISE, {"roleTitles": [title]}, country,
                                   label=f"role normalise {title!r}", operation="GetNormalisedRoles")
        alias = P.normalised_role_alias(raw)
        if alias:
            return alias
        hits = search(title, country, page=1, page_size=1)["roles"]
        if hits and hits[0].get("alias"):
            return hits[0]["alias"]
        return refs.slugify_role(title)
    return fetch.shared_raw("role_alias", {"title": title.lower(), "country": country}, build, ttl.ROLE_ALIAS_CACHE)


def details(role, country="AU"):
    """The full role guide. 404 when the career guide has no such role."""
    alias = resolve_alias(role, country)
    raw = fetch.career_graphql(gql.ROLE, {"alias": alias, "specReqInput": SPEC_REQ_INPUT}, country,
                               label=f"role {alias}", operation="GetRole")
    role_raw = (raw.get("roleByAlias") if isinstance(raw, dict) else None) or {}
    if not role_raw.get("alias") and not role_raw.get("id"):
        raise fetch.SeekNotFound(f"Seek's career guide has no role {alias!r}")
    salaries_raw = {}
    try:
        salaries_raw = fetch.career_graphql(gql.ROLE_SALARIES, {"roleId": alias, "roleTitle": role_raw.get("title") or alias},
                                            country, label=f"role salaries {alias}", operation="GetRoleSalaries")
    except fetch.SeekUpstreamError as e:
        print(f"seek: role salaries for {alias} skipped: {e}")
    return P.role_details(raw, salaries_raw, country)


def reviews(role, country="AU", page=1, page_size=10):
    """One page of reviews written by people in the role."""
    alias = resolve_alias(role, country)
    variables = {"roleId": alias, "sentiment": "ALL", "from": (page - 1) * page_size, "size": page_size}
    raw = fetch.career_graphql(gql.ROLE_REVIEWS, variables, country, label=f"role reviews {alias} p{page}",
                               operation="GetRoleReviews")
    return P.role_reviews(raw, country, alias, page, page_size)


def search(query, country="AU", page=1, page_size=10, sort=None):
    """Career-guide roles matching `query`, with the classification counts."""
    variables = {"term": query, "size": page_size, "from": (page - 1) * page_size, "filter": {"type": "ROLE"}}
    if sort:
        variables["sortBy"] = sort
    raw = fetch.career_graphql(gql.ROLE_SEARCH, variables, country, label=f"role search {query!r} p{page}",
                               operation="SearchV2")
    result = P.role_search(raw, country, page, page_size)
    result["query"] = query
    return result
