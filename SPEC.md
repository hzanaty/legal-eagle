# SPEC.md

## Introduction
This document outlines the specifications and architecture of the "Legal Eagle" project, aimed at monitoring legal changes impacting SAP's localized products.

## Purpose
The "Legal Eagle" project creates an AI-driven agent to monitor government sources for legal updates in chosen countries and industries like HR & Payroll (HCM) or Finance (FIN). It evaluates impacts on SAP local products, flags significant legal changes, and delivers daily actionable intelligence to Localization Product Managers (LPMs).

## Requirements
- **Programming Language**: Python 3.x
- **Libraries and Services**:
  - `feedparser`: For fetching and parsing RSS feed data.
  - `openai`: Utilized for AI-driven natural language processing and insights.
  - `requests`: For HTTP requests and web data interactions.
  - `google-auth`, `google-auth-oauthlib`, `google-auth-httplib2`: For Google services API authentication.
  - `beautifulsoup4`: Employed for web scraping tasks.
  - `playwright`: Used for web automation and interactions.
  - `numpy`: Applied for numerical data processing and analysis.

## Configurations
Configuration settings are centralized in `agents_config.py`:
- **GLOSSARY**: Defines terms for HCM, FIN, and unrelated content.
- **LANGUAGE_PREFERENCE**: Currently set to Arabic ("ar").
- **RSS_FEED_URLS**, **TWEET_ACCOUNTS**, **CRAWL_URLS**, **SNAP_URLS**: Define the data sources for updates.
- **EMAIL_RECEIVERS**: Target LPMs for notification.

## Architecture
### Agents (Execution Order):
- **rss_parser.py**:
  - *Requirements*: Feedparser library
  - *Configurations*: Uses `RSS_FEED_URLS` for input.
  - *Purpose*: Parse and retrieve updates from RSS feeds.
  - *Techniques*: Fetch data via `feedparser`.

- **tweet_feed.py**:
  - *Requirements*: Twitter API integration
  - *Configurations*: Uses credentials from `twitter` section in `credentials.json`.
  - *Purpose*: Collect and analyze tweets from specified accounts.
  - *Techniques*: Employs Twitter's API via bearer token.

- **url_crawl.py**:
  - *Requirements*: Static HTML web scraping
  - *Configurations*: Crawls URLs defined in `CRAWL_URLS`.
  - *Purpose*: Extracts data from static HTML web pages.
  - *Techniques*: Uses BeautifulSoup for extraction.

- **url_snap.py**:
  - *Requirements*: Dynamic page handling with Playwright
  - *Configurations*: Snapshots URLs defined in `SNAP_URLS`.
  - *Purpose*: Collects data from dynamic JavaScript pages.
  - *Techniques*: Automates browsing with Playwright.

- **compare_news.py**:
  - *Requirements*: String comparison support
  - *Configurations*: Cross-references with glossary terms to check relevance.
  - *Purpose*: Identify duplicate or similar news items.
  - *Techniques*: Uses string comparison algorithms, integrates with OpenAI via `openai_api_key` for content analysis.

- **news_filter.py**:
  - *Requirements*: OpenAI API
  - *Configurations*: Uses glossary and language preference.
  - *Purpose*: Filters news for relevance.
  - *Techniques*: Employs OpenAI via `openai_api_key`.

- **news_grouper.py**:
  - *Requirements*: OpenAI API
  - *Configurations*: Utilizes glossary terms and language settings.
  - *Purpose*: Groups and summarizes filtered news.
  - *Techniques*: Uses OpenAI for semantic grouping.

- **email_sender.py**:
  - *Requirements*: SMTP access via Gmail
  - *Configurations*: Uses `EMAIL_RECEIVERS` for routing emails.
  - *Purpose*: Dispatches notifications to LPMs.
  - *Techniques*: Utilizes Gmail SMTP servers and OAuth credentials from `credentials.json`.

## Data Flow
- **Collect**: Retrieve updates from RSS feeds, Twitter, and web crawls.
- **Process**: Filter for relevance and group similar items.
- **Analyze**: Determine impacts on SAP product features.
- **Notify**: Summarize findings and notify via email.

## Version
- **1.0.0**: Framework and agent development for data collection and notification.

## Change Log
- **v1.0.0** - Initial project setup and agent implementation.
