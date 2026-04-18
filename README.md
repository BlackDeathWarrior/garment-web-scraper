# 👗 Ethnic Threads: Smart Clothing Scraper & Showcase

An automated e-commerce intelligence tool that scrapes, normalizes, and showcases Indian ethnic wear from major retailers (Amazon, Myntra, Flipkart). Features a high-performance React frontend and a cloud-ready Python backend.

---

## ✨ Key Features

### 🛒 Multi-Source Scraper (Python + Playwright)
- **Automated Extraction**: Deep-scrapes product titles, brands, prices, images, and user ratings.
- **Intelligent Normalization**: Automatically detects gender (Men/Women) and categories (Kurta, Saree, Sherwani) from titles.
- **Anti-Bot Resilience**: Uses rotating user agents and randomized delays to bypass scraping protections.
- **Cloud Ready**: Integrated with **AWS DynamoDB** for high-scale data storage.

### ⚡ High-Performance Frontend (React + Tailwind)
- **Zero-Lag UI**: Optimized for massive datasets (10,000+ items) using memoization and local storage caching.
- **Beautiful Showcase**: Elegant masonry-style product cards with hover Spec-Rows (Color, Fabric, Source).
- **Smart Filtering**: Instant client-side filtering by price range, ratings, source, and discount percentage.
- **Admin Dashboard**: Secure login for `scraper_admin` to trigger real-time scrape cycles.

### ☁️ Cloud Architecture
- **Serverless Backend**: Designed to run via AWS Lambda and API Gateway.
- **Free Tier Deployment**: Full guides included for hosting on S3, CloudFront, and EC2.

---

## 🛠️ Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS, React Router, Lucide Icons.
- **Backend**: Python 3.10+, BeautifulSoup4, Playwright (Headless Chromium).
- **Database**: AWS DynamoDB / JSON.
- **Deployment**: AWS (S3, CloudFront, EC2, Lambda).

---

## 🚀 Getting Started

### 1. Local Scraper Setup
```bash
cd scraper
pip install -r requirements.txt
playwright install chromium
python collect.py --max-products 100
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## 📖 Documentation
- [AWS Deployment Guide](AWS_Plan.md): Step-by-step for absolute beginners.
- [Architecture Migration](Implementation.md): Technical roadmap and scaling strategy.

---

## 📄 License
MIT License - Created by BlackDeathWarrior
