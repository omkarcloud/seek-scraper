"""/seek/autocomplete, /seek/classifications, /seek/countries — the search
box's location and role-title suggestions (chalice GraphQL) and the static
reference tables the search filters take."""
import uuid

from seek import fetch, gql, refdata
from seek import parsers as P
from seek.shared import site


# The area / region / state kinds (no suburbs): what company review
# locations ("All Melbourne VIC") are keyed on.
AREA_KINDS = ["SEEKLocation", "SEEKArea", "Region", "State", "Country"]


def locations(query, country="AU", limit=10, kinds=None):
    """Suburbs, areas, regions and states matching `query`, with the Seek
    location ids the job search's `location` param accepts."""
    variables = {"searchText": query, "session": uuid.uuid4().hex, "kind": kinds or gql.LOCATION_KINDS,
                 "zone": site(country)["zone"], "languageCode": "en", "countries": [country.upper()]}
    raw = fetch.graphql(gql.LOCATION_SUGGEST, variables, country, label=f"locations {query!r}",
                        operation="MKLocationSuggestions")
    return {"locations": P.location_suggestions(raw, limit)}


def keywords(query, country="AU", limit=10):
    """Role titles Seek's search box would suggest for `query`."""
    variables = {"query": query, "count": limit, "session": uuid.uuid4().hex, "countryCode2": country.upper(),
                 "languageCode": "en"}
    raw = fetch.graphql(gql.KEYWORD_SUGGEST, variables, country, label=f"keywords {query!r}",
                        operation="OntologyRoleTitlesSeniority")
    return {"keywords": P.keyword_suggestions(raw, limit)}


def autocomplete(query, type="locations", country="AU", limit=10):
    if type == "keywords":
        return keywords(query, country, limit)
    return locations(query, country, limit)


def classifications():
    """Seek's 30 job classifications with their sub-classifications (the ids
    the job search's classification / subclassification params take)."""
    subs = {}
    for sid, (parent, name) in refdata.SUBCLASSIFICATIONS.items():
        subs.setdefault(parent, []).append({"id": sid, "name": name})
    out = []
    for cid, name in sorted(refdata.CLASSIFICATIONS.items(), key=lambda kv: kv[1]):
        out.append({"id": cid, "name": name,
                    "subclassifications": sorted(subs.get(cid, []), key=lambda s: s["name"])})
    return {"classifications": out, "count": len(out)}


def countries():
    """The Seek markets this API serves and the filter vocabularies."""
    return {
        "countries": [{"code": code, "name": s["name"], "host": s["host"], "currency": s["currency"]}
                      for code, s in refdata.SITES.items()],
        "work_types": [{"value": k, "name": refdata.WORK_TYPE_LABELS[v]} for k, v in refdata.WORK_TYPES.items()],
        "work_arrangements": [{"value": k, "name": refdata.WORK_ARRANGEMENT_LABELS[v]}
                              for k, v in refdata.WORK_ARRANGEMENTS.items()],
        "date_ranges": list(refdata.DATE_RANGES),
        "sorts": list(refdata.SORT_MODES),
        "salary_types": list(refdata.SALARY_TYPES),
        "max_results_per_search": refdata.MAX_RESULTS,
    }
