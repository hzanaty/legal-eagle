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

TWITTER_ACCOUNTS = [
    {"name": "SaudiGOSI", "id": "1234567890"},
    {"name": "HRSD_SA",   "id": "9876543210"}
]

MONITOR_URLS = [
    {
        "url": "https://uqn.gov.sa/category?cat=4",   # أم القرى - مجلس الوزراء
        "selector": "h5.entry-title a"
    },
    {
        "url": "https://uqn.gov.sa/category?cat=6",   # أم القرى - قرارات وأنظمة
        "selector": "h5.entry-title a"
    },
    {
        "url": "https://uqn.gov.sa/category?cat=7",   # أم القرى - أوامر ملكية
                "selector": "h5.entry-title a"
    },
    {
        "url": "https://uqn.gov.sa/category?cat=8",   # أم القرى - مراسيم ملكية
        "selector": "h5.entry-title a"
    },
    {
        "url": "https://uqn.gov.sa/category?cat=9",   # أم القرى - قرارات مجلس الوزراء
        "selector": "h5.entry-title a"
    },
    {
        "url": "https://uqn.gov.sa/category?cat=10",   # أم القرى - قرارات وزارية
        "selector": "h5.entry-title a"
    },
    {
        "url": "https://uqn.gov.sa/category?cat=11",   # أم القرى - لوائح وأنظمة
        "selector": "h5.entry-title a"
    },
    {
        "url": "https://uqn.gov.sa/category?cat=12",   # أم القرى - هيئات
        "selector": "h5.entry-title a"
    },
    # ... add more as needed
]
