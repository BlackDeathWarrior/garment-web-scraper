"""Ethnic Threads, the shop: accounts, orders and a simulated warehouse.

A small e-commerce backend on the standard library and SQLite. Nothing here
takes real money or ships anything: a payment is a method the shopper picks
plus an outcome the shop decides, and an order moves through its steps on a
timer (see simulation.py).

- db.py          the SQLite database (outputs/shop/shop.db)
- auth.py        shopper accounts, the admin sign-in, session tokens
- catalog.py     the products on sale (frontend/public/products.json)
- orders.py      placing, reading, cancelling, returning and refunding orders
- simulation.py  the warehouse and carrier clock, and the admin's switches
- support.py     /api/support/*: the support desk integration
- server.py      the HTTP API (python -m shop.server)
"""
