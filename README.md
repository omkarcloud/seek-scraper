# 💼 Seek Scraper

Seek Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Seek job data for free.

## ✨ What Can I Get?

- 💼 **Every live job ad on Seek Australia & New Zealand** — full description, salary, applicant counts, screening questions & apply link
- 🔍 **Search with every Seek filter** — location, salary band, work type, remote / hybrid, classification & date listed
- 🏢 **Company profiles, reviews & salaries** — ratings breakdown, AI review summary, employee reviews & pay per role
- 📈 **2,200+ career guides** — salary by state and city, skills, growth & job satisfaction for every role

## 🎥 Example: A Full Seek Job Ad

```json
{
  "id": "95216242",
  "title": "Staff AI Engineer, Strategic Partners, Google Cloud",
  "link": "https://www.seek.com.au/job/95216242",
  "status": "active",
  "teaser": "Lead AI production deployments. Build scalable agentic systems. Shape Google Cloud's future product roadmap.",
  "bullet_points": [
    "Room and opportunities to grow – on your own and with team mates",
    "Flexibility to get your best work"
  ],
  "description_text": "At Google, we have a vision of empowerment and equitable opportunity for all ...",
  "work_type": { "value": "full_time", "label": "Full time" },
  "work_arrangement": { "value": "on_site", "label": "On-site" },
  "classification": {
    "id": "6281",
    "name": "Information & Communication Technology",
    "subclassification": { "id": "6287", "name": "Developers/Programmers" }
  },
  "location": { "label": "Sydney NSW", "suburb": "Sydney", "state": "New South Wales", "postcode": "2000", "country_code": "AU" },
  "apply": { "link": "https://www.seek.com.au/job/95216242/apply", "is_external": true },
  "advertiser": { "id": "400021817", "name": "Google", "is_verified": true },
  "company": {
    "id": "433216",
    "name": "Google",
    "link": "https://www.seek.com.au/companies/google-433216",
    "industry": "Online Media & eCommerce",
    "size": "More than 10,000 employees",
    "rating": 4.2,
    "review_count": 18,
    "perks_and_benefits": ["Health & Wellness", "Flexibility & Time Off", "Googley Extras"]
  },
  "listed_at": "2026-10-12T14:29:46Z",
  "expires_at": "2026-11-11T14:29:46Z"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Seek Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/seek-scraper
cd seek-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=95216242"
```

```json
{
  "id": "95216242",
  "title": "Staff AI Engineer, Strategic Partners, Google Cloud",
  "link": "https://www.seek.com.au/job/95216242",
  "teaser": "Lead AI production deployments. Build scalable agentic systems. Shape Google Cloud's future product roadmap.",
  "work_type": { "value": "full_time", "label": "Full time" },
  "work_arrangement": { "value": "on_site", "label": "On-site" },
  "classification": {
    "id": "6281",
    "name": "Information & Communication Technology",
    "subclassification": { "id": "6287", "name": "Developers/Programmers" }
  },
  "location": { "label": "Sydney NSW", "state": "New South Wales", "postcode": "2000", "country_code": "AU" },
  "company": {
    "name": "Google",
    "industry": "Online Media & eCommerce",
    "size": "More than 10,000 employees",
    "rating": 4.2,
    "review_count": 18
  },
  "listed_at": "2026-10-12T14:29:46Z",
  "expires_at": "2026-11-11T14:29:46Z"
}
```

All 16 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

16 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | The full job ad: description, salary, applicants, questions, employer |
| Search Jobs | `/jobs/search` | Up to 100 jobs per page with every Seek filter and facets |
| Batch Job Details | `/jobs/batch` | Full details for up to 10 jobs in one call |
| Company Details | `/companies/details` | Overview, ratings breakdown, AI review summary, perks and awards |
| Company Reviews | `/companies/reviews` | Employee reviews with pros, cons and ratings, newest first |
| Company Salaries | `/companies/salaries` | Pay range per role, compared with the industry |
| Company Jobs | `/companies/jobs` | Every live job ad a company has on Seek |
| Search Companies | `/companies/search` | Company profiles by name with rating and logo |
| Role Details | `/roles/details` | Salary by state and city, skills, tasks and growth |
| Search Roles | `/roles/search` | Career guide roles with typical salary and satisfaction |
| Role Reviews | `/roles/reviews` | Reviews written by people working in the role |
| Autocomplete | `/autocomplete` | Location IDs and job-title suggestions |
| Company Industries | `/companies/industries` | Every industry in Seek's company directory |
| Company Directory | `/companies/directory` | Every company Seek files under an industry |
| Classifications | `/classifications` | Seek's 30 classifications with their sub-classifications |
| Countries | `/countries` | Markets served and every search filter value |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-seek-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-seek-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-seek-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"query": "software engineer", "location": "Sydney NSW"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Seek Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Seek%20Scraper%20API.)

[![Ask Us by Email about Seek Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Seek%20Scraper%20API&body=I%20need%20help%20using%20the%20Seek%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/seek-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/seek-scraper)
