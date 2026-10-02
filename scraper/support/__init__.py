"""Support desk integration for Ethnic Threads.

Everything here is optional: with SUPPORT_API_URL unset, every hook is a
no-op and the storefront behaves as it did before.

- config.py      settings from the environment
- tms_support.py the support desk's Python client (vendored, standard library only)
- incidents.py   report scraper failures and recoveries
- catalog.py     facts about the scraped catalogue (how old, how big)
- routes.py      the worker's /api/support/* endpoints
"""
