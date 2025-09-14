# agents_config.py

GLOSSARY = """
Focus on topics related to labor contracts, iqama and visa, leaves, end of service, 
labor courts, social insurance (GOSI), health insurance, labor disciplinary and violations, remote work, 
part-time, working hours, Saudization or Nitaqat, Wage Protection, labor law, income tax, 
paytoll, currency, data protection, data residency, service duration, calendar
""".strip()

RSS_FEED_URLS = [
    "https://saudigazette.com.sa/rssFeed/74",
    "https://www.arabnews.com/taxonomy/term/25/feed",  # Example HR feed
    # Add more here...
]

# configurations/agents_config.py

TWEET_ACCOUNTS = [
    {"name": "SaudiGOSI", "id": "1234567890"},
    {"name": "HRSD_SA",   "id": "9876543210"}
]

MONITOR_URLS = [
    {
        "name": "أم القرى - مجلس الوزراء",
        "url": "https://uqn.gov.sa/category?cat=4",
        "domain": "https://uqn.gov.sa",
        "selector": "h5.entry-title a"
    },
    {
        "name": "أم القرى - قرارات وأنظمة",
        "url": "https://uqn.gov.sa/category?cat=6",
        "domain": "https://uqn.gov.sa",
        "selector": "h5.entry-title a"
    },
    {
        "name": "أم القرى - أوامر ملكية",
        "url": "https://uqn.gov.sa/category?cat=7",
        "domain": "https://uqn.gov.sa",
        "selector": "h5.entry-title a"
    },
    {
        "name": "أم القرى - مراسيم ملكية",
        "url": "https://uqn.gov.sa/category?cat=8",
        "domain": "https://uqn.gov.sa",
        "selector": "h5.entry-title a"
    },
    {
        "name": "أم القرى - قرارات مجلس الوزراء",
        "url": "https://uqn.gov.sa/category?cat=9",
        "domain": "https://uqn.gov.sa",
        "selector": "h5.entry-title a"
    },
    {
        "name": "أم القرى - قرارات وزارية",
        "url": "https://uqn.gov.sa/category?cat=10",
        "domain": "https://uqn.gov.sa",
        "selector": "h5.entry-title a"
    },
    {
        "name": "أم القرى - لوائح وأنظمة",
        "url": "https://uqn.gov.sa/category?cat=11",
        "domain": "https://uqn.gov.sa",
        "selector": "h5.entry-title a"
    },
    {
        "name": "أم القرى - هيئات",
        "url": "https://uqn.gov.sa/category?cat=12",
        "domain": "https://uqn.gov.sa",
        "selector": "h5.entry-title a"
    },
    # ... add more as needed
]
