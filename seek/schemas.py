"""Marshmallow request schemas for every /seek/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Seek resolvers (refs.py). Every schema's load() output is the
kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `job` takes a job id OR any Seek job link;
`company` a company id, a /companies/<name>-<id> slug or link, or a company
name; `role` a career-guide alias, a title or a /career-advice/role/ link;
`industry` a directory slug, name or link; `location` free text or a Seek
location id; `country` AU / NZ, a name or a Seek link.
"""
from marshmallow import ValidationError, fields, validate, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CommaListField, PageField, PageSizeField, PositiveInt,
                           QueryField, RefField, StrippedString)
from seek import refdata, refs
from seek.jobs import MAX_BATCH


class CountryField(RefField):
    """The Seek market: AU (default) or NZ, a name, or a Seek link."""
    resolver = staticmethod(refs.resolve_country)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", refdata.DEFAULT_COUNTRY)
        super().__init__(**kwargs)


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class RoleField(RefField):
    resolver = staticmethod(refs.resolve_role)


class IndustryField(RefField):
    resolver = staticmethod(refs.resolve_industry)


class LocationField(RefField):
    resolver = staticmethod(refs.resolve_location)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class JobListField(fields.Field):
    """'94722577, https://www.seek.com.au/job/95263358' -> ['94722577', '95263358']
    (resolved, deduped, 1..MAX_BATCH)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        out = []
        for item in str(value or "").split(","):
            item = item.strip()
            if not item:
                continue
            try:
                job_id = refs.resolve_job(item)
            except ValueError as e:
                raise ValidationError(f"'{item}': {e}")
            if job_id not in out:
                out.append(job_id)
        if not out:
            raise ValidationError("Must list at least one job id or link (comma-separated).")
        if len(out) > MAX_BATCH:
            raise ValidationError(f"At most {MAX_BATCH} jobs.")
        return out


class _TaxonomyListField(CommaListField):
    """Classification / sub-classification ids OR names -> ids."""
    table = {}
    kind = "classification"

    def __init__(self, **kwargs):
        kwargs.setdefault("max_items", 10)
        super().__init__(upper=False, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        by_name = {name.lower(): cid for cid, name in self.table.items()}
        out = []
        for item in items or []:
            cid = item if item in self.table else by_name.get(item.lower())
            if not cid:
                raise ValidationError(f"'{item}' is not a Seek {self.kind} id or name (see /seek/classifications).")
            if cid not in out:
                out.append(cid)
        return out or None


class ClassificationListField(_TaxonomyListField):
    table = refdata.CLASSIFICATIONS
    kind = "classification"


class SubclassificationListField(_TaxonomyListField):
    table = {sid: name for sid, (_, name) in refdata.SUBCLASSIFICATIONS.items()}
    kind = "sub-classification"


class AdvertiserField(StrippedString):
    """A Seek advertiser (account) id, as the search facets list them."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        if not value.isdigit():
            raise ValidationError("Must be a Seek advertiser id (digits, from the search facets).")
        return value


# ---- jobs ----------------------------------------------------------------------------------------------------

class _JobListing(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=validate.Length(max=200))
    country = CountryField()
    page = PageField(max_page=refdata.MAX_RESULTS)
    page_size = PageSizeField(default=20, max_size=refdata.MAX_PAGE_SIZE)
    sort = ChoiceField(refdata.SORT_MODES, load_default=None)

    @validates_schema
    def validate_reach(self, data, **kwargs):
        page, size = data.get("page") or 1, data.get("page_size") or 20
        if (page - 1) * size >= refdata.MAX_RESULTS:
            raise ValidationError({"page": [f"Seek serves at most {refdata.MAX_RESULTS} results per search; "
                                            f"page {page} with page_size {size} is beyond that."]})


class JobSearchSchema(_JobListing):
    location = LocationField()
    date_range = ChoiceField(refdata.DATE_RANGES)
    work_type = CommaListField(value_map=refdata.WORK_TYPES, max_items=4)
    work_arrangement = CommaListField(value_map=refdata.WORK_ARRANGEMENTS, max_items=3)
    classification = ClassificationListField()
    subclassification = SubclassificationListField()
    salary_min = PositiveInt(max_value=10_000_000)
    salary_max = PositiveInt(max_value=10_000_000)
    salary_type = ChoiceField(refdata.SALARY_TYPES, load_default="annual")
    distance = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=0, max=500))
    advertiser = AdvertiserField()

    @validates_schema
    def validate_salary(self, data, **kwargs):
        low, high = data.get("salary_min"), data.get("salary_max")
        if low is not None and high is not None and high < low:
            raise ValidationError({"salary_max": ["Must be >= salary_min."]})


class JobSchema(BaseSchema):
    job = JobField()
    country = CountryField()


class JobBatchSchema(BaseSchema):
    jobs = JobListField()
    country = CountryField()


# ---- companies ----------------------------------------------------------------------------------------------------

class CompanySearchSchema(BaseSchema):
    query = QueryField(max_length=100)
    country = CountryField()
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=20))


class CompanySchema(BaseSchema):
    company = CompanyField()
    country = CountryField()


class CompanyReviewsSchema(CompanySchema):
    page = PageField(max_page=1000)
    page_size = PageSizeField(default=20, max_size=30)
    location = LocationField()


class CompanyJobsSchema(_JobListing):
    company = CompanyField()


class CountrySchema(BaseSchema):
    country = CountryField()


class DirectorySchema(BaseSchema):
    industry = IndustryField()
    country = CountryField()
    page = PageField(max_page=100)
    page_size = PageSizeField(default=50, max_size=200)


# ---- careers ----------------------------------------------------------------------------------------------------------

class RoleSchema(BaseSchema):
    role = RoleField()
    country = CountryField()


class RoleReviewsSchema(RoleSchema):
    page = PageField(max_page=500)
    page_size = PageSizeField(default=10, max_size=50)


class RoleSearchSchema(BaseSchema):
    query = QueryField(max_length=100)
    country = CountryField()
    page = PageField(max_page=100)
    page_size = PageSizeField(default=10, max_size=50)
    sort = ChoiceField(refdata.ROLE_SORTS, load_default=None)


# ---- lookups ------------------------------------------------------------------------------------------------------------

class AutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100)
    type = ChoiceField(["locations", "keywords"], load_default="locations")
    country = CountryField()
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=20))


class EmptySchema(BaseSchema):
    pass
