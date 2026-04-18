# 🚀 Ethnic Threads: Deployment & Cost Guide

This guide covers everything you need to know about taking your project live on AWS and keeping it free.

---

## 🛠️ Infrastructure Setup

### 1. Database (DynamoDB)
- Create a table named `products`.
- **Partition key**: `id` (String).

### 2. Scraper Brain (EC2)
- Launch an Ubuntu `t3.micro` instance.
- **SSH Command for Setup**:
```bash
sudo apt update && sudo apt install -y python3-full git
git clone https://github.com/BlackDeathWarrior/garment-web-scraper
cd garment-web-scraper
python3 -m venv venv
./venv/bin/pip install -r scraper/requirements.txt
./venv/bin/python3 -m playwright install --with-deps chromium
```

### 3. Website Hosting (S3 + CloudFront)
- **S3**: Create bucket and upload `frontend/dist` files. Make public.
- **CloudFront**: Attach to S3 for secure HTTPS and mobile access.

---

## 💰 Start, Stop & Cost Savings

AWS gives you **750 hours per month** for free (enough for 1 machine 24/7).

### Safe Shutdown (Broke Mode)
- **Stop EC2**: Go to Console -> Instance State -> **Stop**.
- **S3 & DynamoDB**: Keep them running. They are serverless and free for small usage.

### Safe Startup
- **Start EC2**: Go to Console -> Instance State -> **Start**.
- **Resume Scraper**:
```bash
export AWS_DYNAMODB_TABLE="products"
export AWS_S3_BUCKET="ethnic-threads-showcase-ap-south-1"
export AWS_ACCESS_KEY_ID="YOUR_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR_SECRET"
export PYTHONPATH=$HOME/garment-web-scraper
nohup ./venv/bin/python3 -m scraper.collect --watch --interval-minutes 10 --append-existing > ~/scraper.log 2>&1 &
```

---

## 🔑 Admin Credentials
- **Username**: `scraper_admin`
- **Password**: Found in your local `.env` file (VITE_ADMIN_PASSWORD).
