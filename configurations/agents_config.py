# agents_config.py

GLOSSARY = """
Focus on topics related to labor contracts, iqama and visa, leaves, end of service, 
labor courts, social insurance (GOSI), health insurance, labor disciplinary and violations, remote work, 
part-time, working hours, Saudization or Nitaqat, Wage Protection, labor law, income tax, 
paytoll, currency, data protection, data residency, service duration, calendar
""".strip()

RSS_FEED_URLS = [
    "https://saudigazette.com.sa/rssFeed/74",
]

TWEET_ACCOUNTS = [
    "SaudiGOSI",
    "HRSD_SA",
]

MONITOR_URLS = [
    {
        "name": "أم القرى - مجلس الوزراء",
        "url": "https://uqn.gov.sa/category?cat=4",
        "domain": "https://uqn.gov.sa",
        "title_tag": "h5.entry-title a",
        "content_tag": "m-3 mt-4"
    },
    {
        "name": "أم القرى - قرارات وأنظمة",
        "url": "https://uqn.gov.sa/category?cat=6",
        "domain": "https://uqn.gov.sa",
        "title_tag": "h5.entry-title a",
        "content_tag": "m-3 mt-4"
    },
    {
        "name": "أم القرى - أوامر ملكية",
        "url": "https://uqn.gov.sa/category?cat=7",
        "domain": "https://uqn.gov.sa",
        "title_tag": "h5.entry-title a",
        "content_tag": "m-3 mt-4"
    },
    {
        "name": "أم القرى - مراسيم ملكية",
        "url": "https://uqn.gov.sa/category?cat=8",
        "domain": "https://uqn.gov.sa",
        "title_tag": "h5.entry-title a",
        "content_tag": "m-3 mt-4"
    },
    {
        "name": "أم القرى - قرارات مجلس الوزراء",
        "url": "https://uqn.gov.sa/category?cat=9",
        "domain": "https://uqn.gov.sa",
        "title_tag": "h5.entry-title a",
        "content_tag": "m-3 mt-4"
    },
    {
        "name": "أم القرى - قرارات وزارية",
        "url": "https://uqn.gov.sa/category?cat=10",
        "domain": "https://uqn.gov.sa",
        "title_tag": "h5.entry-title a",
        "content_tag": "m-3 mt-4"
    },
    {
        "name": "أم القرى - لوائح وأنظمة",
        "url": "https://uqn.gov.sa/category?cat=11",
        "domain": "https://uqn.gov.sa",
        "title_tag": "h5.entry-title a",
        "content_tag": "m-3 mt-4"
    },
    {
        "name": "أم القرى - هيئات",
        "url": "https://uqn.gov.sa/category?cat=12",
        "domain": "https://uqn.gov.sa",
        "title_tag": "h5.entry-title a",
        "content_tag": "m-3 mt-4"
    },
    # ... add more as needed
]
