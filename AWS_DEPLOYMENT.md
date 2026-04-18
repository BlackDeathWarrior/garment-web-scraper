# AWS Infrastructure Setup (Free Tier)

Run these commands using the **AWS CLI** or manually in the **AWS Console**.

## 1. Database (DynamoDB)
Create a table for products.

```bash
aws dynamodb create-table \
    --table-name products \
    --attribute-definitions AttributeName=id,AttributeType=S \
    --key-schema AttributeName=id,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --region us-east-1
```

## 2. Frontend (S3 + CloudFront)
1. **Create S3 Bucket**:
```bash
aws s3 mb s3://ethnic-threads-frontend --region us-east-1
```
2. **Build & Upload**:
```bash
cd frontend
npm run build
aws s3 sync dist/ s3://ethnic-threads-frontend --acl public-read
```
3. **CloudFront**: Manually create a distribution pointing to the S3 bucket's website endpoint for HTTPS.

## 3. Scraper (EC2)
1. **Launch Instance**: `t2.micro` (Ubuntu 22.04 LTS).
2. **Setup**:
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv chromium-browser
git clone <your-repo-url>
cd <repo-dir>/scraper
pip install -r requirements.txt
playwright install chromium --with-deps
```
3. **Environment Variables**:
   Create a `.env` file on the EC2 instance:
   ```env
   AWS_DYNAMODB_TABLE=products
   AWS_ACCESS_KEY_ID=xxx
   AWS_SECRET_ACCESS_KEY=xxx
   AWS_DEFAULT_REGION=us-east-1
   ```
4. **Schedule (Crontab)**:
   Add to `crontab -e` to run every 6 hours:
   `0 */6 * * * /usr/bin/python3 <path-to-repo>/scraper/collect.py --max-products 100 --append-existing`

## 4. Admin Access
- **Username**: `scraper_admin`
- **Password**: `&Jd%)(%AxbiXw#t0SzLv`
