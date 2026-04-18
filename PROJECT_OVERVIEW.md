# Project Overview: Ethnic Threads Showcase

An automated, high-performance web-scraping and discovery platform for Indian Ethnic Wear, featuring real-time data aggregation from Amazon, Flipkart, and Myntra.

---

## 🚀 1. The Technology Stack
*   **Frontend:** React (Vite) with Tailwind CSS for a modern, responsive UI.
*   **Scraping Engine:** Python 3.12 with **Playwright** (for dynamic JavaScript rendering) and **BeautifulSoup4** (for fast HTML parsing).
*   **Cloud Infrastructure:** Amazon Web Services (AWS)
    *   **AWS S3:** Host of the static frontend and the live `products.json` database.
    *   **AWS EC2 (t3.micro):** Dedicated scraper worker running as a continuous background service (`systemd`).
    *   **AWS SSM:** Secure remote management and command execution for the scraper worker.
*   **DevOps:** Git/GitHub for version control and automated code synchronization between local and EC2.

---

## 🛠️ 2. Core Features & Engineering
*   **Cross-Source Product Merging:** Sophisticated logic that identifies identical products across Amazon, Flipkart, and Myntra using alphanumeric title snippets and brand normalization. It displays the cheapest primary source with "Also Available At" price comparisons.
*   **AI Trust Score (Bayesian Inspired):** A heuristic algorithm that calculates a 1-99% score based on raw ratings and volume. It uses a **Logarithmic Confidence Penalty** to ensure that a product with 500 reviews (4.5★) ranks higher than a single 5-star review.
*   **"Nuclear" Noise Filter:** An aggressive, case-insensitive blocklist that automatically purges jewelry, footwear, accessories, and "unstitched" materials, ensuring a 100% garment-only collection.
*   **High-Res Image Upscaling:** Custom Regex-based upscalers that strip compression parameters from Amazon/Myntra/Flipkart URLs to serve studio-quality photography instead of blurry thumbnails.
*   **Admin Scraper Controls:** A high-visibility dashboard with a live terminal, real-time pulse animations, and the ability to trigger manual scrapes or prioritize specific genders (Men/Women) with one click.
*   **Seamless Auto-Updates:** Background data polling every 3 minutes that silently updates the product count without page reloads or disrupting the user's scroll position.

---

## 🌐 3. AWS Deployment Workflow
1.  **Static Hosting:** The React frontend is built and synced to an S3 bucket configured for website hosting.
2.  **Scraper Worker:** A Python script runs on an EC2 instance, managed by a `systemd` service for 24/7 uptime and auto-recovery from crashes.
3.  **Autonomous Synchronization:** The worker performs its scrape, normalizes the data, and uses the `boto3` library to force-upload the latest `products.json` to S3 with aggressive Cache-Control headers.
4.  **Remote Management:** SSM (Systems Manager) allows for nuclear database purges, timezone synchronization (IST), and Playwright browser updates without needing SSH keys.

---

## 🛡️ 4. Data Quality Standards
*   **Strict Normalization:** All brand names are forced to Title Case (e.g., "Manyavar") to prevent duplicate filters.
*   **IST Synchronization:** The entire system is synced to **Asia/Kolkata** time for accurate logging and scrape scheduling.
*   **User Resilience:** Includes a "Manual Retry" system on every product card to fix network-related image loading failures instantly.
