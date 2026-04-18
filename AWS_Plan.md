# 🚀 AWS Beginner Deployment Guide: Ethnic Threads

Follow these steps to take your project from your local computer to the live web on AWS. This guide is designed for absolute beginners and stays within the **AWS Free Tier**.

## 📋 Prerequisites
1.  **AWS Account**: Create one at [aws.amazon.com](https://aws.amazon.com/). You will need a credit card for verification, but we will use Free Tier services only.
2.  **GitHub Account**: Upload your code to a GitHub repository (private or public).

---

## 🛠️ Step 1: Database Setup (DynamoDB)
*AWS DynamoDB is a fast, free-tier-eligible database that stores your product data.*

1.  Log in to the **AWS Management Console**.
2.  Search for **DynamoDB** in the top search bar.
3.  Click **Create table**.
4.  **Table name**: `products`
5.  **Partition key**: `id` (Type: `String`).
6.  Leave everything else as **Default settings**.
7.  Click **Create table**.

---

## 💻 Step 2: The Scraper "Brain" (EC2)
*AWS EC2 is a virtual computer in the cloud that will run your Python scraper.*

1.  Search for **EC2** in the AWS Console.
2.  Click **Launch instance**.
3.  **Name**: `Scraper-Worker`
4.  **Application Image**: Select **Ubuntu** (22.04 LTS, Free Tier eligible).
5.  **Instance type**: `t2.micro` (Free Tier eligible).
6.  **Key pair**: Create a new one, download the `.pem` file. **Don't lose this!**
7.  **Network settings**: Ensure "Allow SSH traffic from Anywhere" is checked.
8.  Click **Launch instance**.

### Setting up the Scraper on EC2:
1.  Connect to your instance via SSH (using the `.pem` file) or use the **EC2 Instance Connect** button in the browser.
2.  Run these commands one by one:
    ```bash
    sudo apt update && sudo apt install -y python3-pip git chromium-browser
    git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
    cd YOUR_REPO/scraper
    pip3 install -r requirements.txt
    playwright install chromium --with-deps
    ```
3.  **Link to Database**:
    Create a file named `.env` in the `scraper` folder:
    ```bash
    nano .env
    ```
    Paste this inside (replace with your AWS keys found in IAM):
    ```env
    AWS_DYNAMODB_TABLE=products
    AWS_DEFAULT_REGION=us-east-1
    AWS_ACCESS_KEY_ID=YOUR_KEY
    AWS_SECRET_ACCESS_KEY=YOUR_SECRET
    ```
    *Press `Ctrl+O`, `Enter`, `Ctrl+X` to save.*

---

## 🌐 Step 3: The Website (S3 + CloudFront)
*AWS S3 stores your website files, and CloudFront makes it fast and secure (HTTPS).*

### Part A: S3 (Storage)
1.  Search for **S3** in the AWS Console.
2.  Click **Create bucket**.
3.  **Bucket name**: `ethnic-threads-frontend-[your-name]` (must be unique).
4.  **Object Ownership**: ACLs enabled.
5.  **Block Public Access**: Uncheck "Block all public access" (we need the web to see it!).
6.  Click **Create bucket**.

### Part B: Uploading Files
1.  On your **local computer**, open the `frontend` folder.
2.  Run: `npm run build`
3.  Open the newly created `dist` folder.
4.  Go to your S3 bucket in the AWS Console and click **Upload**.
5.  Drag and drop all files **inside** the `dist` folder into the upload area.
6.  After uploading, select all files, click **Actions** -> **Make public using ACL**.

---

## 🔑 Step 4: Admin Access
Use the credentials you configured in your environment variables to log in once your site is live.
- **URL**: Your S3 Website Endpoint (found in S3 -> Properties -> Static website hosting).
- **Username**: `scraper_admin`
- **Password**: [Your Secure Password]

---

## 💡 Pro Tips for Beginners
-   **IAM Users**: Don't use your "Root" account for the EC2 `.env` file. Create an **IAM User** with `AmazonDynamoDBFullAccess` for better security.
-   **Cost Alert**: Set up a **Billing Alarm** in AWS (search for "Billing") to notify you if you ever spend more than $1.
