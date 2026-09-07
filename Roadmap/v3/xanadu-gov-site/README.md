# Xanadu Government Website (local demo fixture)

A small **static** website that plays the role of a foreign government portal —
the *Ministry of Human Resources, Republic of Xanadu* — for the Legal Eagle v3 team demo (Run 1).
Xanadu is fictional; all notices are invented.

It is served **locally** and ingested by Legal Eagle through its **direct URL-source** path (which
opens each article and extracts the full body). No Firebase, no public hosting, no RSS feed.

```
Local Xanadu gov site  →  Legal Eagle URL source  →  Run → Review → Announcements → RCM → L2S
```

## Structure

```
xanadu-gov-site/
└── public/
    ├── index.html       # Newsroom listing (the URL added to Legal Eagle points here)
    ├── styles.css       # Government-portal styling
    └── news/            # One page per press release (full article body)
        ├── social-insurance-rate-countdown.html   # ← FLAGSHIP (the LC candidate)
        ├── public-holiday-schedule.html            # low-rank noise
        ├── regional-bureau-relocation.html         # low-rank noise
        ├── staff-sports-day.html                   # low-rank noise
        └── annual-leave-reminder.html              # low-rank noise
```

Each listing item links to its article and carries a **"Read more →"** anchor, so Legal Eagle's
URL-source scraper reliably discovers and follows each link to the full article body.

## Content design (why these articles)

- **Flagship — "One week remaining before the new social insurance contribution rate takes
  effect"** is a *reworded re-announcement* of a change Legal Eagle has already seen (that prior
  version is pre-seeded into the DB by `scripts/prep_xanadu_demo.py`). It matches the glossary
  (*social insurance*, *contribution rate*) and is designed to land at **rank 4, tag REPEATED**.
- The other four items are routine notices that match little/no glossary and rank low (1–2).

## Serve it locally

```bash
cd Roadmap/v3/xanadu-gov-site
python3 -m http.server 8000 -d public
```

The newsroom is then at `http://127.0.0.1:8000/`. (Any static server works; `.html` links are used
so no clean-URL rewriting is required.)

## Add it to Legal Eagle as a URL source

In the Xanadu profile → Sources → add a **URL source** with just the newsroom URL
(`http://127.0.0.1:8000/`).

> **Do not run the Source Simulator on it.** Leaving the source un-simulated routes it to the
> full-article scraper (follows each link, extracts the full body). Running the Simulator would
> store list-page selectors that capture title/link/date **snippets only** — thin content.

That's it — run the profile and the articles flow through the normal pipeline.
