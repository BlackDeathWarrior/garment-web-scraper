$ErrorActionPreference = "Continue"

# Use environment variables or run 'aws configure' instead of hardcoding keys
$AWS = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"

Write-Host "Zipping Lambda function..."
Compress-Archive -Path "D:\Web Scraping\backend\lambda_function.py" -DestinationPath "D:\Web Scraping\backend\lambda.zip" -Force

Write-Host "Creating IAM Role..."
try {
    $RoleResponse = & $AWS iam create-role --role-name EthnicThreadsLambdaRole --assume-role-policy-document "file://D:\Web Scraping\trust_policy.json" --no-cli-pager | ConvertFrom-Json
    $RoleArn = $RoleResponse.Role.Arn
    Write-Host "Role created: $RoleArn"
} catch {
    Write-Host "Role might already exist. Retrieving ARN..."
    $RoleResponse = & $AWS iam get-role --role-name EthnicThreadsLambdaRole --no-cli-pager | ConvertFrom-Json
    $RoleArn = $RoleResponse.Role.Arn
}

if (-not $RoleArn) {
    $RoleArn = (& $AWS iam get-role --role-name EthnicThreadsLambdaRole --no-cli-pager | ConvertFrom-Json).Role.Arn
}

Write-Host "Attaching policies..."
& $AWS iam attach-role-policy --role-name EthnicThreadsLambdaRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole --no-cli-pager
& $AWS iam attach-role-policy --role-name EthnicThreadsLambdaRole --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess --no-cli-pager
& $AWS iam attach-role-policy --role-name EthnicThreadsLambdaRole --policy-arn arn:aws:iam::aws:policy/AmazonSSMFullAccess --no-cli-pager

Write-Host "Waiting for IAM Role propagation (15 seconds)..."
Start-Sleep -Seconds 15

Write-Host "Creating Lambda Function..."
try {
    $LambdaResponse = & $AWS lambda create-function --function-name EthnicThreadsBackend --runtime python3.10 --role $RoleArn --handler lambda_function.lambda_handler --zip-file "fileb://D:\Web Scraping\backend\lambda.zip" --environment "Variables={PRODUCTS_TABLE=products,EC2_INSTANCE_ID=placeholder}" --no-cli-pager | ConvertFrom-Json
    Write-Host "Lambda created."
} catch {
    Write-Host "Function might exist, updating code..."
    & $AWS lambda update-function-code --function-name EthnicThreadsBackend --zip-file "fileb://D:\Web Scraping\backend\lambda.zip" --no-cli-pager
}

Write-Host "Creating Function URL..."
try {
    $UrlResponse = & $AWS lambda create-function-url-config --function-name EthnicThreadsBackend --auth-type NONE --cors "file://D:\Web Scraping\cors_config.json" --no-cli-pager | ConvertFrom-Json
    $FunctionUrl = $UrlResponse.FunctionUrl
    Write-Host "Function URL created: $FunctionUrl"
} catch {
    Write-Host "Function URL config might already exist. Retrieving..."
    $UrlResponse = & $AWS lambda get-function-url-config --function-name EthnicThreadsBackend --no-cli-pager | ConvertFrom-Json
    $FunctionUrl = $UrlResponse.FunctionUrl
}

if (-not $FunctionUrl) {
    $FunctionUrl = (& $AWS lambda get-function-url-config --function-name EthnicThreadsBackend --no-cli-pager | ConvertFrom-Json).FunctionUrl
}

Write-Host "Adding resource-based policy for public access..."
try {
    & $AWS lambda add-permission --function-name EthnicThreadsBackend --statement-id FunctionURLAllowPublicAccess --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE --no-cli-pager
} catch {
    Write-Host "Permission might already exist (ignoring)."
}

Write-Host "------------------------------------------------"
Write-Host "DEPLOYMENT SUCCESSFUL!"
Write-Host "YOUR API URL IS: $FunctionUrl"
Write-Host "------------------------------------------------"
