# 👗 Ethnic Threads: a demonstration shop for Indian ethnic wear

A small online shop with the features you expect from one: accounts, a cart, checkout, orders you can track step by step, cancellations, returns and refunds, and customer support. It sells a catalogue of Indian ethnic wear that this repository's scraper collected from Amazon, Myntra and Flipkart.

**It is a demonstration.** No card number or UPI id is asked for, no money moves and nothing is shipped: paying is simulated, and an order moves through the warehouse and the carrier on a clock.

---

## ✨ What is in it

### 🛍️ The shop (`shop/`, `frontend/`)
- **Browse and buy**: search, filters, product pages with sizes, a cart, "buy now".
- **Checkout**: a delivery address, standard or express delivery, and cash on delivery, UPI or card (all simulated).
- **Orders**: "Your orders", and an order page with the five steps (placed, packed, shipped, out for delivery, delivered), the carrier, a tracking number and the expected date.
- **After the order**: cancel before it ships (refunded at once), ask for a return after delivery, buy it again.
- **Operations page for the admin**: every order, move or hold one, approve a return, and switches that make payments fail or the carrier run late, to show what happens when things go wrong.
- **Customer support**: help with an order, a contact form, a list of your requests and a chat, all run by a support desk through its integration API. See [The shop and its support desk](SUPPORT_DESK.md).

### 🛒 The scraper (`scraper/`)
- Collects product titles, brands, prices, images and ratings with Playwright, and normalises them (gender, category).
- It is how the catalogue in `frontend/public/products.json` was made. The site no longer starts or shows it.

---

## 🛠️ Tech stack

- **Storefront**: React 18, Vite, Tailwind CSS, React Router.
- **Shop server**: Python 3.10+, standard library only (`http.server`, SQLite).
- **Scraper**: Python, BeautifulSoup4, Playwright.

---

## 🚀 Getting started

### 1. The shop's server
```bash
pip install python-dotenv
python -m shop.server --step-seconds 20
```

### 2. The storefront
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, create an account and place an order. To sign in as the admin, set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` (see `frontend/.env.example`).

### 3. Tests
```bash
python -m pytest tests/shop tests/support
cd frontend && npx vitest run
```

### The scraper, if you want a fresh catalogue
```bash
cd scraper
pip install -r requirements.txt
playwright install firefox
python collect.py --max-products 100
```

---

## 📖 Documentation
- [The shop and its support desk](SUPPORT_DESK.md): pages, routes, settings, the simulation, and how support is connected.
- [AWS Deployment Guide](DEPLOYMENT.md) and [Architecture Migration](Implementation.md): written for the scraper showcase this project began as.

---

## 📄 License
MIT License - Created by BlackDeathWarrior
