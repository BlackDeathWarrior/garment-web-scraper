import json
import boto3
import os
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# Helper to handle Decimal types (DynamoDB specific)
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('PRODUCTS_TABLE', 'products'))

def lambda_handler(event, context):
    # Support both API Gateway (V1) and Function URL (V2) payload formats
    path = event.get('rawPath') or event.get('path') or '/'
    
    if 'requestContext' in event and 'http' in event['requestContext']:
        method = event['requestContext']['http']['method']
    else:
        method = event.get('httpMethod', 'GET')
    
    # CORS Headers (Required for S3 to talk to Lambda)
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST"
    }

    if method == 'OPTIONS':
        return {"statusCode": 200, "headers": headers}

    # 1. GET /products - Fetch data from DynamoDB
    if path == '/products' and method == 'GET':
        try:
            # Simple scan (limit 100 for performance)
            response = table.scan(Limit=100)
            items = response.get('Items', [])
            
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps(items, cls=DecimalEncoder)
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": headers,
                "body": json.dumps({"error": str(e)})
            }

    # 2. POST /scrape-cycle - Trigger EC2 Scraper
    if path == '/scrape-cycle' and method == 'POST':
        try:
            ssm = boto3.client('ssm')
            instance_id = os.environ.get('EC2_INSTANCE_ID')
            
            if not instance_id:
                return {
                    "statusCode": 400,
                    "headers": headers,
                    "body": json.dumps({"error": "EC2 Instance ID not configured"})
                }

            ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={'commands': ['cd /home/ubuntu/scraper/scraper && python3 collect.py --max-products 100']}
            )

            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({"message": "Scrape command sent to EC2", "ok": True})
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": headers,
                "body": json.dumps({"error": str(e)})
            }

    return {
        "statusCode": 404,
        "headers": headers,
        "body": json.dumps({"error": "Path not found: " + path})
    }
