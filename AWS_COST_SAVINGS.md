# 💰 AWS Cost Savings: How to Start & Stop Safely

Because you are on the AWS Free Tier, you want to be careful with your "Compute Hours." Here is how to manage your project without spending a dime.

---

## 🖥️ 1. The Scraper (EC2) - THE BIGGEST COST
AWS gives you **750 hours per month** for free. This is exactly enough to run **ONE** machine 24/7. If you accidentally run two, you will be charged.

### How to SHUT DOWN (To save hours):
1.  Go to the **EC2 Dashboard**.
2.  Click **Instances (running)**.
3.  Select `Scraper-Worker`.
4.  Click **Instance State** -> **Stop Instance**.
    *   *Note: "Stop" is like turning off a computer. "Terminate" is like throwing it in the trash. Only use Terminate if you never want the machine again.*

### How to START UP:
1.  Go to **EC2 Dashboard**.
2.  Select `Scraper-Worker`.
3.  Click **Instance State** -> **Start Instance**.
4.  **Crucial**: You must run the scraper command again (see below) because the computer "forgets" what it was doing when it turned off.

**Run this on start:**
```bash
export AWS_DYNAMODB_TABLE="products"
export AWS_S3_BUCKET="ethnic-threads-showcase-ap-south-1"
export AWS_DEFAULT_REGION="ap-south-1"
export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_KEY"
export PYTHONPATH=$HOME/garment-web-scraper
nohup $HOME/garment-web-scraper/venv/bin/python3 -m scraper.collect --watch --interval-minutes 10 --append-existing > ~/scraper.log 2>&1 &
```

---

## 🗄️ 2. The Database (DynamoDB) - SAFE
DynamoDB is "Serverless." If nobody is using it, it costs **$0**. 
-   **Do not delete the table.** Just leave it. It stores up to 25GB for free.

---

## 🌐 3. The Website (S3) - SAFE
S3 hosting is also "Serverless." 
-   It costs pennies per month to store your files. You can leave this **ON** 24/7 so people can always see your site. 

---

## 🚨 4. The "Broke Student" Safety Rules
1.  **Set a Billing Alarm**: 
    - Search for "Billing" in AWS. 
    - Go to **Billing Preferences**.
    - Check the box: **"Receive Free Tier Usage Alerts"**. This will email you if you are about to reach your limit.
2.  **Check for "Zombies"**: Once a week, go to the EC2 Dashboard and make sure "Running Instances" says **1** (or 0 if you turned it off).
3.  **Use One Region**: Always stay in `ap-south-1` (Mumbai) to keep everything organized.

---

## 🧹 5. The "I'm Done" Option (Delete Everything)
If you finish the project and never want to use it again:
1.  **Terminate** the EC2 Instance.
2.  **Delete** the S3 Bucket.
3.  **Delete** the DynamoDB Table.
4.  **Delete** the Lambda Function.
