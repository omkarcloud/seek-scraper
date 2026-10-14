"""Raw Seek payloads -> clean API objects. Pure functions, no network; every
parser tolerates missing / null / wrong-typed fields and never raises on a
partial payload.

Job cards come from the job-search API (search_result / job_card); job
details, company profiles / reviews / salaries and suggestions from the
chalice GraphQL; role data from the career-guide GraphQL; the company
directory from the directory pages' hydration JSON.

Intentionally dropped everywhere: tracking / session tokens (solMetadata
request tokens, `tracking` blobs, userQueryId, experiment tags, visitor
ids), presentation-only duplicates (displayStyle, localisedDescriptions,
label wrappers around a string we already return, the `url` field that
repeats the link we build), internal source-system names (job.source), the
chalice `zone` echoes, `__typename`, the review `schemaVersion` / flag
state, and the per-industry "urlToSearch" when it only repeats a search we
can rebuild. Nothing with information content is left out.
"""
import html as html_lib
import re
from math import ceil

from seek import refdata
from seek import shared as S
from seek.shared import as_dict, as_list, g, text

# ---- small shared pieces ---------------------------------------------------------------------------

def _labels(items):
    """[{label: 'x'}, 'y', {label: {text: 'z'}}] -> ['x', 'y', 'z']."""
    out = []
    for item in as_list(items):
        value = text(item.get("label") if isinstance(item, dict) else item)
        if value and value not in out:
            out.append(value)
    return out


def _classification(cid, name=None, sub_id=None, sub_name=None):
    cid = text(cid)
    sub_id = text(sub_id)
    if not cid and not name:
        return None
    sub = None
    if sub_id or sub_name:
        parent, known = refdata.SUBCLASSIFICATIONS.get(sub_id, (None, None))
        sub = {"id": sub_id, "name": text(sub_name) or known}
        cid = cid or parent
    return {"id": cid, "name": text(name) or refdata.CLASSIFICATIONS.get(cid), "subclassification": sub}


def classification_pair(item):
    """A search card's {classification: {id, description}, subclassification: {...}}."""
    item = as_dict(item)
    main, sub = as_dict(item.get("classification")), as_dict(item.get("subclassification"))
    return _classification(main.get("id"), main.get("description"), sub.get("id"), sub.get("description"))


def work_arrangement(value, label=None):
    """Seek's arrangement id ('2') or badge ('HYBRID') -> {value, label}."""
    raw = text(value)
    if not raw:
        return None
    key = raw
    if raw.upper() in ("ONSITE", "ON_SITE", "ON-SITE"):
        key = "1"
    elif raw.upper() == "HYBRID":
        key = "2"
    elif raw.upper() == "REMOTE":
        key = "3"
    public = refdata.WORK_ARRANGEMENT_VALUES.get(key)
    if not public:
        return None
    return {"value": public, "label": text(label) or refdata.WORK_ARRANGEMENT_LABELS.get(key)}


def work_type(value, label=None):
    """Seek's work type id ('242') or label -> {value, label}."""
    raw = text(value) or text(label)
    if not raw:
        return None
    ids = {v: k for k, v in refdata.WORK_TYPES.items()}
    by_label = {v.lower(): k for k, v in refdata.WORK_TYPE_LABELS.items()}
    tid = raw if raw in ids else by_label.get(raw.lower())
    if not tid:
        # labels like "Full time" / "Casual/Vacation" / "FULL_TIME"
        norm = re.sub(r"[^a-z]", "", raw.lower())
        for k, v in refdata.WORK_TYPE_LABELS.items():
            if re.sub(r"[^a-z]", "", v.lower()).startswith(norm[:8]):
                tid = k
                break
    if not tid:
        return {"value": S.lower_snake(raw), "label": text(label) or raw}
    return {"value": ids[tid], "label": text(label) or refdata.WORK_TYPE_LABELS[tid]}


def _bool(value):
    return value if isinstance(value, bool) else None


def _location_ref(item):
    """{id: 'seek-1002', label: {text}} / {whereId, description} -> {id, name}."""
    item = as_dict(item)
    name = text(item.get("label")) or text(item.get("description")) or text(item.get("text")) \
        or text(g(item, "contextualName"))
    lid = S.seek_id(item.get("id") if item.get("id") is not None else item.get("whereId"))
    if lid is None and name is None:
        return None
    return {"id": lid, "name": name}


# ---- job search ----------------------------------------------------------------------------------------

def search_location(raw):
    raw = as_dict(raw)
    if not raw:
        return None
    return {
        "id": S.seek_id(raw.get("whereId")),
        "name": text(raw.get("description")),
        "short_name": text(raw.get("locationDescription")),
        "type": S.lower_snake(raw.get("type")),
        "default_distance_km": S.to_int(raw.get("defaultDistanceKms")),
    }


def facets(raw):
    raw = as_dict(raw)
    out = {}
    names = {"title": "titles", "workType": "work_types", "workArrangement": "work_arrangements",
             "location": "locations", "advertiser": "advertisers"}
    for key, public in names.items():
        items = []
        for item in as_list(raw.get(key)):
            item = as_dict(item)
            entry = {"id": text(item.get("id")), "name": text(item.get("label")), "count": S.to_int(item.get("count"))}
            if key == "location":
                entry["id"] = S.seek_id(item.get("id"))
            elif key == "workType":
                entry = {"value": (work_type(item.get("id")) or {}).get("value"), "name": entry["name"],
                         "count": entry["count"]}
            elif key == "workArrangement":
                entry = {"value": (work_arrangement(item.get("id")) or {}).get("value"), "name": entry["name"],
                         "count": entry["count"]}
            if entry.get("name"):
                items.append(entry)
        if items:
            out[public] = items
    return out or None


def related_searches(raw):
    out = []
    for item in as_list(as_dict(raw).get("relatedSearches")):
        item = as_dict(item)
        keywords = text(item.get("keywords"))
        if not keywords:
            continue
        locations = [loc for loc in (_location_ref(l) for l in as_list(item.get("locations"))) if loc]
        out.append({"keywords": keywords, "total_jobs": S.to_int(item.get("totalJobs")),
                    "location": locations[0] if locations else None})
    return out


def recruiter_card(card):
    for ref in as_list(card.get("externalReferences")):
        ref = as_dict(ref)
        if text(ref.get("type")) != "recruiter":
            continue
        meta = as_dict(ref.get("metadata"))
        name = text(meta.get("name"))
        if name:
            return {"name": name, "photo": text(g(meta, "assets", "profilePhotoUrl"))}
    return None


def job_card(card, country):
    card = as_dict(card)
    job_id = text(card.get("id"))
    employer = as_dict(card.get("employer"))
    advertiser = as_dict(card.get("advertiser"))
    sol = as_dict(card.get("solMetadata"))
    ad_type = S.lower_snake(sol.get("jobAdType"))
    arrangements = [a for a in (work_arrangement(g(x, "id"), g(x, "label", "text"))
                                for x in as_list(g(card, "workArrangements", "data"))) if a]
    locations = []
    for loc in as_list(card.get("locations")):
        loc = as_dict(loc)
        label = text(loc.get("label"))
        if not label:
            continue
        locations.append({
            "label": label,
            "country_code": text(loc.get("countryCode")),
            "areas": [a for a in (text(g(h, "contextualName")) for h in as_list(loc.get("seoHierarchy"))) if a],
        })
    company_id = text(employer.get("companyId"))
    return {
        "id": job_id,
        "title": text(card.get("title")),
        "link": S.job_link(country, job_id),
        "teaser": text(card.get("teaser")),
        "bullet_points": [b for b in (text(x) for x in as_list(card.get("bulletPoints"))) if b],
        "role_id": (text(card.get("roleId")) or "").lower() or None,
        "listed_at": S.iso_datetime(card.get("listingDate")),
        "listed_at_label": text(card.get("listingDateDisplay")),
        "salary": S.salary_from_label(card.get("salaryLabel"), S.currency(country)),
        "work_types": [w for w in (work_type(None, x) for x in as_list(card.get("workTypes"))) if w],
        "work_arrangements": arrangements,
        "classifications": [c for c in (classification_pair(x) for x in as_list(card.get("classifications"))) if c],
        "locations": locations,
        "company": {
            "id": company_id,
            "name": text(card.get("companyName")) or text(employer.get("name")),
            "link": text(employer.get("companyUrl")) or (S.company_link(country, company_id) if company_id else None),
            "logo": text(g(card, "branding", "serpLogoUrl")),
        },
        "advertiser": {"id": text(advertiser.get("id")), "name": text(advertiser.get("description"))},
        "recruiter": recruiter_card(card),
        "is_featured": bool(card.get("isFeatured")),
        "is_sponsored": ad_type == "sponsored",
        "ad_type": ad_type,
        "tags": [{"type": S.lower_snake(g(t, "type")), "label": text(g(t, "label"))}
                 for t in as_list(card.get("tags")) if text(g(t, "label"))],
    }


def search_result(raw, country, page, page_size):
    raw = as_dict(raw)
    total = S.to_int(raw.get("totalCount")) or 0
    reachable = min(total, refdata.MAX_RESULTS)
    suggestions = as_dict(raw.get("suggestions"))
    out = {
        "jobs": [job_card(c, country) for c in as_list(raw.get("data")) if isinstance(c, dict)],
        "location": search_location(raw.get("location")),
        "location_suggestions": [loc for loc in (_location_ref(l) for l in as_list(suggestions.get("location"))) if loc],
        "related_searches": related_searches(suggestions),
        "facets": facets(raw.get("facets")),
        "pagination": {"page": page, "items_per_page": page_size,
                       "total_pages": ceil(reachable / page_size) if reachable and page_size else 0,
                       "total_count": total},
    }
    if total > refdata.MAX_RESULTS:
        out["results_limit"] = refdata.MAX_RESULTS   # Seek never serves past its 550th result
    return out


# ---- job details -----------------------------------------------------------------------------------------

_BADGE_ARRANGEMENTS = {"ONSITE", "HYBRID", "REMOTE"}


def applicants(insights):
    out = {"count": None, "count_label": None, "volume_label": None,
           "with_resume_percent": None, "with_cover_letter_percent": None}
    found = False
    for item in as_list(insights):
        item = as_dict(item)
        message = (text(item.get("message")) or "").lower()
        if "count" in item or "applied" in message:
            out["count"] = S.to_int(item.get("count"))
            out["count_label"] = text(item.get("countLabel"))
            out["volume_label"] = text(item.get("volumeLabel"))
            found = True
        elif "percentage" in item:
            if "cover letter" in message:
                out["with_cover_letter_percent"] = S.to_int(item.get("percentage"))
            else:
                out["with_resume_percent"] = S.to_int(item.get("percentage"))
            found = True
    return out if found else None


def job_company(profile, country):
    profile = as_dict(profile)
    if not profile:
        return None
    slug = text(profile.get("companyNameSlug"))
    rating = as_dict(g(profile, "reviewsSummary", "overallRating"))
    overview = as_dict(profile.get("overview"))
    return {
        "id": text(profile.get("id")),
        "organisation_id": text(profile.get("organisationId")),
        "name": text(profile.get("name")),
        "slug": slug,
        "link": S.company_link(country, slug),
        "logo": text(g(profile, "branding", "logo")),
        "website": text(g(overview, "website", "url")),
        "industry": text(overview.get("industry")),
        "size": text(g(overview, "size", "description")),
        "description": S.multiline("\n\n".join(p for p in as_list(g(overview, "description", "paragraphs")) if p)),
        "rating": S.rating(rating.get("value")),
        "review_count": S.to_int(g(rating, "numberOfReviews", "value")),
        "has_reviews": _bool(profile.get("shouldDisplayReviews")),
        "perks_and_benefits": [p for p in (text(g(x, "title")) for x in as_list(profile.get("perksAndBenefits"))) if p],
    }


def job_details(raw, country):
    """jobDetails payload -> the job object, or None when Seek has no such job."""
    jd = as_dict(as_dict(raw).get("jobDetails"))
    job = as_dict(jd.get("job"))
    job_id = text(job.get("id"))
    if not job_id:
        return None
    seo = as_dict(jd.get("seoInfo"))
    gfj = as_dict(g(jd, "gfjInfo", "location"))
    products = as_dict(job.get("products"))
    branding = as_dict(products.get("branding"))
    advertiser = as_dict(job.get("advertiser"))
    recruiter = as_dict(jd.get("sourcrRecruiter"))
    badges = [text(g(b, "badge")) for b in as_list(g(jd, "badges", "badges"))]
    badges = [b for b in badges if b]
    arrangement = next((work_arrangement(b) for b in badges if b.upper() in _BADGE_ARRANGEMENTS), None)
    class_ids = [c for c in (text(x) for x in as_list(seo.get("classification"))) if c]
    sub_ids = [c for c in (text(x) for x in as_list(seo.get("subClassification"))) if c]
    classification = _classification(class_ids[0] if class_ids else None, None, sub_ids[0] if sub_ids else None)
    if classification and not classification.get("name"):
        # fall back to the label "Sub (Parent)" when the id table lacks it
        label = text(g(job, "classifications", 0, "label")) or ""
        match = re.match(r"(.*)\((.*)\)\s*$", label)
        if match:
            classification["name"] = text(match.group(2))
            if classification.get("subclassification") and not classification["subclassification"].get("name"):
                classification["subclassification"]["name"] = text(match.group(1))
    salary = S.salary_from_label(g(job, "salary", "label"), text(g(job, "salary", "currencyLabel")) or S.currency(country))
    content = job.get("content") if isinstance(job.get("content"), str) else None
    link = S.job_link(country, job_id)
    video = as_dict(products.get("video"))
    return {
        "id": job_id,
        "title": text(job.get("title")),
        "link": link,
        "status": S.lower_snake(job.get("status")),
        "is_expired": bool(job.get("isExpired")),
        "teaser": text(job.get("abstract")),
        "bullet_points": [b for b in (text(x) for x in as_list(products.get("bullets"))) if b],
        "description_html": content,
        "description_text": S.html_to_text(content),
        "salary": salary,
        "work_type": work_type(seo.get("workType"), g(job, "workTypes", "label")),
        "work_arrangement": arrangement,
        "classification": classification,
        "normalised_role_title": text(seo.get("normalisedRoleTitle")),
        "location": {
            "label": text(g(job, "location", "label")),
            "suburb": text(gfj.get("suburb")),
            "region": text(gfj.get("region")),
            "state": text(gfj.get("state")),
            "postcode": text(gfj.get("postcode")),
            "country": text(gfj.get("country")),
            "country_code": text(gfj.get("countryCode")),
            "area": text(seo.get("broaderLocationName")),
            "search_label": text(seo.get("where")),
        },
        "applicants": applicants(jd.get("insights")),
        "screening_questions": [q for q in (text(x) for x in as_list(g(products, "questionnaire", "questions"))) if q],
        "apply": {
            "link": f"{link}/apply" if link else None,
            "is_external": _bool(job.get("isLinkOut")),
            "is_profile_apply": _bool(job.get("isProfileApply")),
            "restriction": text(g(jd, "restrictedApplication", "label")),
        },
        "contact": {
            "phone_number": text(job.get("phoneNumber")),
            "matches": [{"type": S.lower_snake(g(m, "type")), "value": text(g(m, "value"))}
                        for m in as_list(job.get("contactMatches")) if text(g(m, "value"))],
        },
        "badges": [S.lower_snake(b) for b in badges],
        "display_tags": _labels(products.get("displayTags")),
        "branding": {"logo": text(g(branding, "logo", "url")), "cover": text(g(branding, "cover", "url"))}
        if branding else None,
        "video": {"link": text(video.get("url")), "position": S.lower_snake(video.get("position"))} if video else None,
        "advertiser": {
            "id": text(advertiser.get("id")),
            "name": text(advertiser.get("name")) or text(seo.get("normalisedOrganisationName")),
            "is_verified": _bool(advertiser.get("isVerified")),
            "registered_at": S.iso_datetime(advertiser.get("registrationDate")),
            "jobs_link": text(jd.get("companySearchUrl")),
        },
        "company": job_company(jd.get("companyProfile"), country),
        "recruiter": {
            "name": text(recruiter.get("name")),
            "job_title": text(recruiter.get("jobTitle")),
            "rating": S.rating(recruiter.get("overallRating")),
            "review_count": S.to_int(recruiter.get("reviewCount")),
            "photo": text(recruiter.get("avatarImageUrl")),
            "agency_name": text(recruiter.get("agencyName")),
            "agency_logo": text(recruiter.get("agencyImageUrl")),
            "link": text(recruiter.get("contactUrl")),
        } if text(recruiter.get("name")) else None,
        "company_tags": [{"key": text(g(t, "key")), "value": text(g(t, "value"))}
                         for t in as_list(jd.get("companyTags")) if text(g(t, "key"))],
        "created_at": S.iso_datetime(job.get("createdAt")),
        "updated_at": S.iso_datetime(job.get("updatedAt")),
        "listed_at": S.iso_datetime(job.get("listedAt")),
        "listed_at_label": text(g(job, "listedAt", "label")),
        "expires_at": S.iso_datetime(job.get("expiresAt")),
        "expired_at": S.iso_datetime(job.get("expiredAt")),
    }


# ---- companies --------------------------------------------------------------------------------------------

def company_search_item(item, country):
    item = as_dict(item)
    data = as_dict(item.get("data"))
    slug = text(data.get("slug"))
    cid = text(item.get("companyId"))
    return {
        "id": cid,
        "organisation_id": text(item.get("organisationId")),
        "name": text(data.get("name")),
        "slug": slug,
        "link": S.company_link(country, slug or cid),
        "logo": text(g(data, "branding", "logo")),
        "rating": S.rating(data.get("reviewRating")),
        "review_count": S.to_int(data.get("reviewCount")),
        "is_published": _bool(data.get("published")),
    }


def company_search(raw, country):
    items = [company_search_item(i, country) for i in as_list(as_dict(raw).get("searchCompanyProfilesByName"))
             if isinstance(i, dict)]
    return {"companies": [i for i in items if i.get("id")]}


def _rating_block(block):
    block = as_dict(block)
    return {"rating": S.rating(block.get("rating")), "count": S.to_int(block.get("count"))}


def company_ratings(review_rating, summary=None):
    """companyReviewRating -> the ratings summary: overall, categories,
    star distribution, recommendation and salary-fairness percentages."""
    rr = as_dict(review_rating)
    summary = as_dict(summary)
    overall = as_dict(rr.get("company"))
    if not rr and not summary:
        return None
    categories = {}
    for key, public in refdata.REVIEW_CATEGORIES.items():
        if key in rr:
            categories[public] = _rating_block(rr.get(key))
    distribution = {}
    for star in range(1, 6):
        block = rr.get(f"companyRating{star}Star")
        if isinstance(block, dict):
            distribution[str(star)] = S.to_int(block.get("count"))
    return {
        "overall": S.rating(overall.get("rating")) if overall else S.rating(summary.get("value")),
        "review_count": S.to_int(overall.get("count")) if overall else S.to_int(g(summary, "numberOfReviews", "value")),
        "recommended_percent": S.to_int(g(rr, "companyRecommended", "percentage")),
        "categories": categories or None,
        "distribution": distribution or None,
        "salary": {
            "poor_percent": S.to_int(g(rr, "salaryPoor", "percentage")),
            "fair_percent": S.to_int(g(rr, "salaryFair", "percentage")),
            "generous_percent": S.to_int(g(rr, "salaryGenerous", "percentage")),
        } if any(k in rr for k in ("salaryPoor", "salaryFair", "salaryGenerous")) else None,
    }


def _titled(items):
    out = []
    for item in as_list(items):
        item = as_dict(item)
        title = text(item.get("title"))
        if title or text(item.get("description")):
            out.append({"title": title, "description": S.multiline(item.get("description"))})
    return out


def company_details(raw, country, company_id):
    """GetCompanyDetails payload -> the company object, or None when the
    profile does not exist."""
    raw = as_dict(raw)
    details = as_dict(raw.get("companyDetails"))
    profile = as_dict(details.get("companyProfile"))
    data = as_dict(profile.get("data"))
    summary = as_dict(raw.get("companyProfile"))
    if not data.get("name") and not summary:
        return None
    overview = as_dict(data.get("overview"))
    branding = as_dict(data.get("branding"))
    ai = as_dict(details.get("companyReviewsAISummary"))
    canonical = text(data.get("canonicalUrl"))
    slug = canonical.rsplit("/", 1)[-1] if canonical else None
    cid = text(details.get("id")) or text(company_id)
    featured = as_dict(data.get("featured"))
    culture = as_dict(data.get("cultureAndValues"))
    custom = as_dict(data.get("customStatement"))
    graduates = as_dict(g(data, "graduates", "overview"))
    ai_text = text(g(ai, "aISummaryContent", "positiveAndChallengesSummary"))
    return {
        "id": cid,
        "organisation_id": text(profile.get("organisationId")),
        "name": text(data.get("name")),
        "slug": slug,
        "link": S.company_link(country, slug or cid),
        "logo": text(branding.get("logo")) or text(g(summary, "branding", "logo")),
        "cover": text(branding.get("cover")),
        "website": text(g(overview, "website", "url")),
        "industry": {"id": text(overview.get("industryId")),
                     "name": text(overview.get("industryName")) or text(overview.get("industry"))}
        if (overview.get("industryId") or overview.get("industry")) else None,
        "size": text(overview.get("size")),
        "headquarters": text(overview.get("primaryLocation")),
        "specialities": [s for s in (text(x) for x in as_list(overview.get("specialities"))) if s],
        "description": S.multiline("\n\n".join(p for p in as_list(overview.get("description")) if p)),
        "traditional_land": text(overview.get("traditionalLand")),
        "traditional_place": text(overview.get("traditionalPlace")),
        "mission_statement": S.multiline(data.get("missionStatement")),
        "custom_statement": {"title": text(custom.get("title")), "description": S.multiline(custom.get("description"))}
        if custom else None,
        "featured": {"title": text(featured.get("title")), "description": S.multiline(featured.get("description")),
                     "image": text(featured.get("imageUrl")), "video": text(featured.get("videoUrl"))}
        if featured else None,
        "awards": [{"name": text(g(a, "name")), "year": S.to_int(g(a, "year")), "image": text(g(a, "imageUrl"))}
                   for a in as_list(data.get("awards")) if text(g(a, "name"))],
        "culture_and_values": {
            "title": text(culture.get("title")),
            "description": S.multiline(culture.get("description")),
            "image": text(culture.get("imageUrl")),
            "values": _titled(culture.get("values")),
        } if culture else None,
        "perks_and_benefits": _titled(data.get("perksAndBenefits")),
        "gallery": [{"title": text(g(x, "title")), "date": S.iso_date(g(x, "date")), "link": text(g(x, "linkUrl"))}
                    for x in as_list(data.get("gallery")) if text(g(x, "linkUrl"))],
        "graduates": {"description": S.multiline("\n\n".join(p for p in as_list(graduates.get("richTextBody")) if p)),
                      "link": text(graduates.get("externalUrl"))} if graduates else None,
        "is_claimed": _bool(data.get("isClaimed")),
        "ratings": company_ratings(profile.get("companyReviewRating"), g(summary, "reviewsSummary", "overallRating")),
        "review_summary": {
            "text": S.html_to_text(ai_text),
            "html": ai_text,
            "reviews_count": S.to_int(ai.get("reviewsCount")),
            "from": S.iso_date(ai.get("reviewsDateFrom")),
            "to": S.iso_date(ai.get("reviewsDateTo")),
        } if ai_text else None,
        "review_locations": [{"name": text(g(x, "contextualName")), "link": S.link(country, g(x, "relativeUrl"))}
                             for x in as_list(details.get("companyReviewLocations")) if text(g(x, "contextualName"))],
    }


def company_review(item):
    item = as_dict(item)
    ratings = {}
    for r in as_list(item.get("ratings")):
        key = S.lower_snake(g(r, "description"))
        if key:
            ratings[key] = S.rating(g(r, "value"))
    reply = as_dict(item.get("reply"))
    upvotes = as_dict(item.get("upvotes"))
    return {
        "id": text(item.get("id")),
        "title": text(item.get("title")),
        "rating": S.rating(item.get("overallRating")),
        "job_title": text(item.get("jobTitle")),
        "work_location": text(item.get("workLocation")),
        "employment_status": text(item.get("employmentStatus")),
        "salary_summary": text(item.get("salarySummary")),
        "is_recommended": _bool(g(item, "recommended", "value")),
        "pros": S.multiline(item.get("pros")),
        "cons": S.multiline(item.get("cons")),
        "overall_experience": S.multiline(item.get("overallExperienceDetails")),
        "ratings": ratings or None,
        "upvotes": S.to_int(upvotes.get("count")),
        "reply": {"text": S.multiline(reply.get("text")), "from": text(reply.get("from")),
                  "created_at": S.iso_datetime(reply.get("createdAt"))} if text(reply.get("text")) else None,
        "created_at": S.iso_date(g(item, "createdAt", "shortAbsoluteLabel")),
    }


def company_reviews(raw, country, company_id, page, per_page):
    raw = as_dict(raw)
    details = as_dict(raw.get("companyDetails"))
    block = as_dict(details.get("companyReviews"))
    profile = as_dict(raw.get("companyProfile"))
    if not block and not profile:
        return None
    paging = as_dict(block.get("paging"))
    rating = as_dict(g(profile, "reviewsSummary", "overallRating"))
    slug = text(profile.get("companyNameSlug"))
    cid = text(details.get("id")) or text(company_id)
    total = S.to_int(paging.get("total")) or 0
    return {
        "company": {
            "id": cid,
            "name": text(profile.get("name")),
            "slug": slug,
            "link": S.company_link(country, slug or cid),
            "logo": text(g(profile, "branding", "logo")),
            "rating": S.rating(rating.get("value")),
            "review_count": S.to_int(g(rating, "numberOfReviews", "value")),
        },
        "reviews": [company_review(r) for r in as_list(block.get("data")) if isinstance(r, dict)],
        "pagination": {"page": S.to_int(paging.get("page")) or page,
                       "items_per_page": S.to_int(paging.get("perPage")) or per_page,
                       "total_pages": S.to_int(paging.get("totalPages")) or 0,
                       "total_count": total},
    }


def _salary_range(block, currency_code):
    block = as_dict(block)
    label = text(block.get("label"))
    if not label and block.get("jobsCount") is None:
        return None
    parsed = S.salary_from_label(label, currency_code) or {"label": None, "min": None, "max": None,
                                                          "currency": currency_code, "period": None}
    stype = S.lower_snake(block.get("salaryType"))
    if stype and "annual" in stype:
        parsed["period"] = "yearly"
    elif stype and "hour" in stype:
        parsed["period"] = "hourly"
    return {
        "label": parsed.get("label"),
        "min": parsed.get("min"),
        "max": parsed.get("max"),
        "currency": currency_code,
        "period": parsed.get("period"),
        "salary_type": stype,
        "jobs_count": S.to_int(block.get("jobsCount")),
        "industry_comparison": text(block.get("industryAverageDescription")),
    }


def company_salaries(raw, country, company_id):
    raw = as_dict(raw)
    details = as_dict(raw.get("companyDetails"))
    profile = as_dict(details.get("companyProfile"))
    data = as_dict(profile.get("data"))
    srange = as_dict(details.get("companySalaryRange"))
    if not details or (not profile and not as_list(srange.get("salaryRangeByRoles"))):
        # an unknown company id still answers {id, companyProfile: null,
        # companySalaryRange: {salaryRangeByRoles: []}}
        return None
    canonical = text(data.get("canonicalUrl"))
    slug = canonical.rsplit("/", 1)[-1] if canonical else None
    cid = text(details.get("id")) or text(company_id)
    cur = S.currency(country)
    roles = []
    for item in as_list(srange.get("salaryRangeByRoles")):
        item = as_dict(item)
        title = text(item.get("roleTitle"))
        if not title:
            continue
        roles.append({
            "role_id": text(item.get("roleId")),
            "title": title,
            "company": _salary_range(item.get("salaryRangeByCompany"), cur),
            "industry": _salary_range(item.get("salaryRangeByIndustry"), cur),
        })
    return {
        "company": {"id": cid, "organisation_id": text(profile.get("organisationId")), "name": text(data.get("name")),
                    "slug": slug, "link": S.company_link(country, slug or cid)},
        "last_updated": S.iso_date(g(srange, "lastUpdatedAt", "shortAbsoluteLabel")),
        "roles": roles,
        "count": len(roles),
    }


def company_organisation(raw):
    """GetCompanyOrganisation -> {id, organisation_id, name, slug} or None."""
    details = as_dict(as_dict(raw).get("companyDetails"))
    profile = as_dict(details.get("companyProfile"))
    data = as_dict(profile.get("data"))
    if not details.get("id"):
        return None
    canonical = text(data.get("canonicalUrl"))
    return {
        "id": text(details.get("id")),
        "organisation_id": text(profile.get("organisationId")),
        "name": text(data.get("name")),
        "slug": canonical.rsplit("/", 1)[-1] if canonical else None,
    }


# ---- company directory (pages) ---------------------------------------------------------------------------

_CATEGORY_RE = re.compile(r'data-testid="industry-category-([A-Za-z0-9]+)"[^>]*>(.*?)</h3>(.*?)(?=<h3[^>]*data-testid="industry-category-|<footer|$)',
                          re.S)
_INDUSTRY_LINK_RE = re.compile(r'href="/companies/directory/([a-z0-9-]+)"[^>]*>(.*?)</a>', re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)


def _clean_html(value):
    return text(html_lib.unescape(re.sub(r"<[^>]+>", " ", value or "")))


def directory_industries(html, country):
    """The /companies/directory page -> {industries: [...], categories: [...]}."""
    industries, categories, seen = [], [], set()
    for cat_id, cat_name, body in _CATEGORY_RE.findall(html or ""):
        cat = {"id": text(cat_id), "name": _clean_html(cat_name)}
        count = 0
        for slug, name in _INDUSTRY_LINK_RE.findall(body):
            if slug in seen:
                continue
            seen.add(slug)
            count += 1
            industries.append({"slug": slug, "name": _clean_html(name), "category": cat,
                               "link": S.link(country, f"/companies/directory/{slug}")})
        categories.append(dict(cat, industry_count=count))
    if not industries:
        for slug, name in _INDUSTRY_LINK_RE.findall(html or ""):
            if slug not in seen:
                seen.add(slug)
                industries.append({"slug": slug, "name": _clean_html(name), "category": None,
                                   "link": S.link(country, f"/companies/directory/{slug}")})
    return {"industries": industries, "categories": categories, "count": len(industries)}


def directory_companies(loader, html, country, slug, page, page_size):
    """A /companies/directory/<slug> page -> one page of its companies."""
    block = as_dict(as_dict(loader).get("company-directory-industry"))
    rows = [r for r in as_list(block.get("companies")) if isinstance(r, dict)]
    if not block:
        return None
    heading = _H1_RE.search(html or "")
    name = _clean_html(heading.group(1)) if heading else None
    name = re.sub(r"\s+companies in .*$", "", name) if name else None
    start = (page - 1) * page_size
    out_rows = []
    for row in rows[start:start + page_size]:
        cid = text(row.get("company_id"))
        cname = text(row.get("company_name"))
        row_slug = f"{re.sub(r'[^a-z0-9]+', '-', (cname or '').lower()).strip('-')}-{cid}" if cid else None
        out_rows.append({
            "id": cid,
            "name": cname,
            "link": S.company_link(country, row_slug),
            "country_code": text(row.get("country")),
            "has_about": text(row.get("has_about")) == "true",
            "has_culture": text(row.get("has_culture")) == "true",
            "has_jobs": text(row.get("has_jobs")) == "true",
            "has_salaries": text(row.get("has_salaries")) == "true",
            "has_reviews": text(row.get("has_reviews")) == "true",
        })
    total = S.to_int(block.get("companyCount")) or len(rows)
    return {
        "industry": {"id": text(block.get("industryId")), "slug": slug, "name": name,
                     "link": S.link(country, f"/companies/directory/{slug}")},
        "companies": out_rows,
        "pagination": {"page": page, "items_per_page": page_size,
                       "total_pages": ceil(len(rows) / page_size) if rows else 0, "total_count": total},
    }


# ---- suggestions -----------------------------------------------------------------------------------------

def location_suggestions(raw, limit=None):
    out = []
    for item in as_list(as_dict(raw).get("mkLocationSuggestions")):
        item = as_dict(item)
        name = text(item.get("text"))
        if not name:
            continue
        out.append({"id": S.seek_id(item.get("id")), "name": name, "country_code": text(item.get("countryCode"))})
    return out[:limit] if limit else out


def keyword_suggestions(raw, limit=None):
    out = []
    for item in as_list(as_dict(raw).get("ontologyRoleTitlesSeniority")):
        item = as_dict(item)
        name = text(item.get("normalisedText"))
        if not name:
            continue
        ident = text(item.get("id")) or ""
        out.append({"id": ident.rsplit("/", 1)[-1].lower() or None, "name": name})
    return out[:limit] if limit else out


# ---- career guide --------------------------------------------------------------------------------------------

def _salary_pair(block):
    block = as_dict(block)
    low, high = S.amount(block.get("salary_min")), S.amount(block.get("salary_max"))
    if low is None and high is None:
        return None
    return {"min": low, "max": high}


def _suggestion(block):
    block = as_dict(block)
    sugg = as_dict(block.get("suggestion"))
    if not block:
        return None
    return {
        "min": S.amount(block.get("salary_min")),
        "max": S.amount(block.get("salary_max")),
        "median": S.amount(block.get("salary_median")),
        "typical_range": {"min": S.amount(sugg.get("min")), "max": S.amount(sugg.get("max"))} if sugg else None,
    }


def role_card(item, country):
    item = as_dict(item)
    alias = text(item.get("alias")) or text(item.get("id"))
    stats = as_dict(item.get("roleReviewStatistics"))
    return {
        "alias": alias,
        "title": text(item.get("title")),
        "link": S.role_link(country, alias),
        "typical_salary": _salary_pair(item.get("typicalSalary")) or (
            {"min": S.amount(item.get("typicalSalaryMin")), "max": S.amount(item.get("typicalSalaryMax"))}
            if item.get("typicalSalaryMin") is not None or item.get("typicalSalaryMax") is not None else None),
        "job_satisfaction": S.rating(item.get("jobSatisfaction") if "jobSatisfaction" in item else stats.get("jobSatisfaction")),
        "growth_percent": S.rounded(item.get("growthValue")),
        "image": text(item.get("image")),
        "video": (f"https://www.youtube.com/watch?v={text(item.get('video'))}" if text(item.get("video")) else None),
        "classifications": [c for c in (text(g(x, "class")) for x in as_list(item.get("classifications"))) if c],
        "is_released": _bool(item.get("isReleased")),
    }


def role_search(raw, country, page, page_size):
    block = as_dict(as_dict(raw).get("searchV2"))
    total = S.to_int(block.get("total")) or 0
    return {
        "roles": [role_card(i, country) for i in as_list(block.get("items")) if isinstance(i, dict)],
        "classifications": [{"name": text(g(c, "class")), "slug": text(g(c, "classSegmentUrl")),
                             "count": S.to_int(g(c, "count"))}
                            for c in as_list(block.get("classifications")) if text(g(c, "class"))],
        "pagination": {"page": page, "items_per_page": page_size,
                       "total_pages": ceil(total / page_size) if total and page_size else 0,
                       "total_count": total},
    }


def _steps(items):
    return [t for t in (S.html_to_text(g(x, "text")) for x in as_list(items)) if t]


def _frequency(block):
    block = as_dict(block)
    if not block:
        return None
    return {k: S.rounded(block.get(k), 1) for k in ("never", "sometimes", "often")}


def role_details(raw, salaries_raw, country):
    """GetRole (+ GetRoleSalaries) payloads -> the role object, or None."""
    role = as_dict(as_dict(raw).get("roleByAlias"))
    alias = text(role.get("alias")) or text(role.get("id"))
    if not alias:
        return None
    wil = as_dict(role.get("whatsItLike"))
    htb = as_dict(role.get("howToBecome"))
    stats = as_dict(role.get("roleReviewStatistics"))
    growth = as_dict(role.get("growth"))
    source = as_dict(growth.get("source"))
    sal = as_dict(salaries_raw)
    skills = {public: [] for public in refdata.SPEC_REQ_LABELS.values()}
    for item in as_list(role.get("specReqs")):
        item = as_dict(item)
        label = text(item.get("label"))
        if not label:
            continue
        kind = re.sub(r"[^a-z]", "", (text(item.get("type")) or "").lower())
        public = next((v for k, v in refdata.SPEC_REQ_LABELS.items() if k.lower() == kind), "experience")
        if label not in skills[public]:
            skills[public].append(label)
    cur = S.currency(country)
    locations = []
    for kind, key in (("state", "states"), ("city", "cities")):
        for item in as_list(sal.get(key)):
            item = as_dict(item)
            name = text(item.get("locationName"))
            if not name:
                continue
            locations.append(dict({"location": {"id": S.to_int(item.get("locationId")), "name": name, "type": kind}},
                                  **(_suggestion(item) or {}), currency=cur,
                                  jobs_link=text(item.get("urlToSearch"))))
    class_salaries = [{"classification": {"id": text(g(c, "class_id")), "name": text(g(c, "class_title"))},
                       "average": S.amount(g(c, "avg_salary")), "currency": cur}
                      for c in as_list(g(sal, "role", "classSalaries")) if text(g(c, "class_title"))]
    return {
        "alias": alias,
        "title": text(role.get("title")),
        "link": S.role_link(country, alias),
        "summary": text(g(role, "hero", "title")),
        "description": S.html_to_text("\n\n".join(p for p in as_list(wil.get("introduction")) + as_list(wil.get("extraContent"))
                                                  if isinstance(p, str) and p)),
        "tasks_and_duties": _steps(wil.get("tasksAndDuties")),
        "how_to_become": {"summary": S.html_to_text(htb.get("content")), "steps": _steps(htb.get("steps"))}
        if htb else None,
        "image": text(wil.get("imageUrl")),
        "video": text(wil.get("videoUrl")),
        "classifications": [_classification(g(c, "classificationCode"), g(c, "classification"),
                                            g(c, "subclassificationCode"))
                            for c in as_list(role.get("classifications")) if g(c, "classificationCode") is not None],
        "salary": {
            "currency": cur,
            "typical": _salary_pair(role.get("typicalSalary")),
            "national": dict(_suggestion(role.get("salarySuggestion")) or {},
                             location=text(g(role, "salarySuggestion", "locationName"))),
            "by_location": locations,
            "by_classification": class_salaries,
        },
        "skills": skills,
        "growth": {
            "percent": S.rounded(growth.get("value")),
            "start_year": S.to_int(growth.get("startYear")),
            "end_year": S.to_int(growth.get("endYear")),
            "source": {"organisation": text(source.get("organisation")), "category": text(source.get("category")),
                       "link": text(source.get("link"))} if source else None,
        } if growth else None,
        "review_statistics": {
            "review_count": S.to_int(stats.get("total")),
            "job_satisfaction": S.rating(stats.get("jobSatisfaction")),
            "remuneration": S.rating(stats.get("remuneration")),
            "employability": S.rating(stats.get("employability")),
            "work_life_balance": S.rating(stats.get("workLifeBalance")),
            "diversity_in_tasks": S.rating(stats.get("diversityInTasks")),
            "career_progression": S.rating(stats.get("careerProgressionOpportunities")),
            "working_hours": {
                "responses": S.to_int(stats.get("workingHoursCount")),
                "overtime_percent": _frequency(stats.get("overtime")),
                "weekends_percent": _frequency(stats.get("weekends")),
                "shift_work_percent": _frequency(stats.get("shiftWork")),
                "late_nights_percent": _frequency(stats.get("lateNights")),
            } if stats.get("workingHoursCount") else None,
        } if stats else None,
        "similar_roles": [role_card(r, country) for r in as_list(role.get("similarRoles")) if isinstance(r, dict)],
        "pathway_roles": [role_card(g(r, "role"), country) for r in as_list(g(role, "pathwayRoles", "cgRoles"))
                          if isinstance(g(r, "role"), dict)],
        "is_released": _bool(role.get("isReleased")),
        "available_locales": [l for l in (text(x) for x in as_list(role.get("additionalLocales"))) if l],
    }


def role_review(item):
    item = as_dict(item)
    return {
        "id": text(item.get("id")),
        "title": text(item.get("title")),
        "rating": S.rating(item.get("overallRating")),
        "good_things": S.multiline(item.get("goodThings")),
        "challenges": S.multiline(item.get("challenges")),
        "ratings": {
            "remuneration": S.rating(item.get("remuneration")),
            "employability": S.rating(item.get("employability")),
            "job_satisfaction": S.rating(item.get("jobSatisfaction")),
            "work_life_balance": S.rating(item.get("workLifeBalance")),
            "diversity_in_tasks": S.rating(item.get("diversityInTasks")),
            "career_progression": S.rating(item.get("careerProgressionOpportunities")),
        },
        "reviewer": {
            "qualification": text(item.get("relevantQualificationFullName")),
            "years_in_role": text(item.get("yearsInCurrentRole")),
            "organisation_size": text(item.get("sizeOfOrganisation")),
            "department": text(item.get("currentDepartment")),
        },
        "submitted_at": S.iso_datetime(item.get("submitted")),
    }


def role_reviews(raw, country, alias, page, page_size):
    raw = as_dict(raw)
    total = S.to_int(raw.get("roleReviewsCount")) or 0
    return {
        "role": {"alias": alias, "link": S.role_link(country, alias)},
        "reviews": [role_review(r) for r in as_list(raw.get("roleReviews")) if isinstance(r, dict)],
        "pagination": {"page": page, "items_per_page": page_size,
                       "total_pages": ceil(total / page_size) if total and page_size else 0,
                       "total_count": total},
    }


def normalised_role_alias(raw):
    """GetNormalisedRoles -> the career guide alias of the first title, or None."""
    for item in as_list(as_dict(raw).get("getNormalisedRoles")):
        alias = text(g(item, "caRole", "alias"))
        if alias:
            return alias
    return None
