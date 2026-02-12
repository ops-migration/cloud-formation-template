# CloudFormation Deployment Scripts

This directory contains Python scripts for automating ECS infrastructure deployment using CloudFormation templates.

## Overview

- **`deploy.py`** - Main deployment orchestrator for CloudFormation stacks
- **`validate.py`** - Configuration and template validation tool
- **`requirements.txt`** - Python dependencies

## Prerequisites

- Python 3.8+
- AWS CLI v2 configured with credentials
- boto3, pyyaml (see requirements.txt)
- Internet connectivity for AWS API calls

### Quick Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Verify Python version
python3 --version
```

## Scripts

### 1. validate.py

**Purpose**: Validates all CloudFormation templates, configuration files, and IAM policies before deployment.

**Usage**:
```bash
python validate.py
```

**What It Checks**:
- ✓ CloudFormation template YAML syntax (10 templates)
- ✓ Application configuration YAML syntax
- ✓ JSON policy files validity
- ✓ Environment variables and secrets JSON format
- ✓ Required configuration keys
- ✓ Placeholder values that need replacement
- ✓ VPC/Subnet ID format
- ✓ Container image URI format

**Output**:
```
============================================================
ECS MIGRATION PROJECT VALIDATION
============================================================

1. CloudFormation Templates
   ✓ alb.yaml: Template is valid
   ✓ cloudwatch.yaml: Template is valid
   [...]

2. Application Configurations
   ✓ aqcuiflow/dev: Configuration is valid
   [...]

VALIDATION SUMMARY
✓ Passed: 20
⚠ Warnings: 14
✗ Errors: 0
```

**Exit Codes**:
- `0` - Validation passed (with or without warnings)
- `1` - Validation failed (errors found)

**Common Issues**:
- Placeholder values (VPC IDs, Subnet IDs, image URIs) - Replace with real values
- Missing iam.json files - Create empty `{}` if not needed
- Invalid YAML syntax - Check file formatting and indentation

---

### 2. deploy.py

**Purpose**: Orchestrates CloudFormation stack deployment and management across environments and applications.

**Usage**:

#### Deployment
```bash
# Deploy all applications to dev environment
python deploy.py deploy dev all

# Deploy single application
python deploy.py deploy dev aqcuiflow

# Deploy to different environment
python deploy.py deploy qa all
```

#### Update (Modify Existing Infrastructure)
```bash
# Update all stacks after config changes
python deploy.py update dev all

# Update single application
python deploy.py update dev aqcuiflow
```

#### Delete (Cleanup Infrastructure)
```bash
# Delete all infrastructure for environment
python deploy.py delete dev all

# Delete specific application
python delete.py delete dev aqcuiflow

# Delete specific stack
python deploy.py delete dev aqcuiflow --stack dev-acquiflow-sg
```

#### Status (Check Deployment Status)
```bash
# Check status of dev environment
python deploy.py status dev all

# Check specific application
python deploy.py status dev aqcuiflow
```

#### Validate (Run Validation)
```bash
# Validate configuration before deployment
python deploy.py validate
```

### Command Format

```
python deploy.py <action> [environment] [application] [options]

Arguments:
  action              {validate, deploy, update, delete, status}
                      - validate: Check configuration and templates
                      - deploy: Create new or update existing stacks
                      - update: Update stacks after changes
                      - delete: Remove infrastructure
                      - status: Check deployment status

  environment         Environment name (dev, qa, staging, prod)
                      - Required for: deploy, update, delete, status
                      - Optional for: validate

  application         Application name (all, aqcuiflow, function-manager)
                      - 'all' deploys all applications in environment
                      - Can be specific app name

Options:
  --region REGION     AWS region (default: us-east-1)
  --stack STACK       Specific stack name (for delete operations)
```

### Deployment Sequence (9 Steps per Application)

When deploying an application, deploy.py executes this sequence:

1. **Security Groups** - ALB and ECS security groups
2. **IAM Roles** - Task execution role + task role
3. **CloudWatch Logs** - Log group with configurable retention
4. **ECR Repository** - Container image registry
5. **Application Load Balancer** - Shared ALB (once per environment)
6. **Target Group** - Per-app target group with host-based routing
7. **Task Definition** - ECS task with API + Nginx containers
8. **ECS Service** - Service configuration with scaling
9. **Auto Scaling** - CPU/Memory-based scaling policies

### Configuration Mapping

The script reads configuration from YAML files and converts them to CloudFormation parameters:

**Location**: `application/{app-name}/{environment}/config.yaml`

**Examples**:
```yaml
# Basic parameters
Environment: dev
ApplicationName: aqcuiflow
CPU: '256'
Memory: '512'

# Lists (converted to comma-separated strings)
SubnetIds:
  - subnet-xxxxx
  - subnet-yyyyy
# → SubnetIds: "subnet-xxxxx,subnet-yyyyy"

# Booleans
EnableCPUScaling: 'true'
# → EnableCPUScaling: "true" (CloudFormation format)

# JSON strings (passed as-is)
EnvironmentVariables: |
  [{"name": "NODE_ENV", "value": "production"}]
```

### Stack Naming Convention

CloudFormation stacks follow this naming pattern:

```
{environment}-{app-name}-{component}

Examples:
- dev-acquiflow-sg              (Security Groups)
- dev-acquiflow-iam             (IAM Roles)
- dev-acquiflow-logs            (CloudWatch Logs)
- dev-acquiflow-ecr             (ECR Repository)
- dev-alb                       (Shared ALB)
- dev-acquiflow-tg              (Target Group)
- dev-acquiflow-taskdef         (Task Definition)
- dev-acquiflow-service         (ECS Service)
- dev-acquiflow-autoscaling     (Auto Scaling)
```

### IAM Policy Injection

Custom IAM policies can be injected into the task role:

**File**: `application/{app-name}/{environment}/iam.json`

**Format** (JSON object, not stringified):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::bucket-name/*"
    }
  ]
}
```

**If not provided**: Defaults to `{}` (no custom permissions)

---

## Environment Variables & Secrets

### Environment Variables

**In config.yaml**:
```yaml
EnvironmentVariables: |
  [
    {"name": "NODE_ENV", "value": "production"},
    {"name": "LOG_LEVEL", "value": "info"},
    {"name": "API_PORT", "value": "8080"}
  ]
```

**In containers**: Available as environment variables directly.

### Secrets

**In config.yaml**:
```yaml
Secrets: |
  [
    {
      "name": "DATABASE_URL",
      "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789012:secret:app/db"
    },
    {
      "name": "API_KEY",
      "valueFrom": "arn:aws:ssm:us-east-1:123456789012:parameter/app/api-key"
    }
  ]
```

**Sources**:
- AWS Secrets Manager: `arn:aws:secretsmanager:region:account:secret:name`
- SSM Parameter Store: `arn:aws:ssm:region:account:parameter/path`

**In containers**: Injected at runtime from AWS Secrets Manager/SSM.

---

## Usage Examples

### Example 1: First-Time Deployment

```bash
# 1. Validate everything
python validate.py

# 2. Deploy to dev environment
python deploy.py deploy dev all

# 3. Check status
python deploy.py status dev all
```

### Example 2: Update After Config Changes

```bash
# 1. Edit application config
vim ../application/aqcuiflow/dev/config.yaml

# 2. Validate changes
python validate.py

# 3. Update infrastructure
python deploy.py update dev aqcuiflow

# 4. Verify
python deploy.py status dev aqcuiflow
```

### Example 3: Deploy Single Application

```bash
# Deploy only function-manager to qa
python deploy.py deploy qa function-manager
```

### Example 4: Deploy to Multiple Environments

```bash
# Deploy all apps to dev
python deploy.py deploy dev all

# Deploy all apps to qa
python deploy.py deploy qa all

# Deploy all apps to staging
python deploy.py deploy staging all
```

### Example 5: Cleanup

```bash
# Delete all infrastructure for dev environment
python deploy.py delete dev all

# Delete specific application infrastructure
python deploy.py delete dev aqcuiflow

# Delete specific stack only
python deploy.py delete dev aqcuiflow --stack dev-acquiflow-sg
```

---

## Troubleshooting

### Issue: "Parameters must have values"

**Cause**: Missing required stack outputs from previous stacks.

**Solution**:
```bash
# Check if previous stack exists
aws cloudformation describe-stacks --stack-name <stack-name>

# If missing, deploy again from the beginning
python deploy.py deploy <env> <app>
```

### Issue: "VPC/Subnet not found"

**Cause**: VPC ID or Subnet IDs are placeholders or incorrect.

**Solution**:
```bash
# Find your VPC
aws ec2 describe-vpcs --query 'Vpcs[].VpcId'

# Find subnets
aws ec2 describe-subnets --query 'Subnets[].SubnetId'

# Update config.yaml with real values
vi ../application/<app>/dev/config.yaml
```

### Issue: "Stack already exists"

**Cause**: Stack already deployed. Use `update` instead of `deploy`.

**Solution**:
```bash
# To update existing infrastructure
python deploy.py update dev aqcuiflow
```

### Issue: "Template format error"

**Cause**: YAML syntax error in CloudFormation template.

**Solution**:
```bash
# Validate YAML syntax
python validate.py

# Check specific template
aws cloudformation validate-template --template-body file://../template/<template>.yaml
```

### Issue: "Access Denied"

**Cause**: AWS credentials don't have required permissions.

**Solution**:
```bash
# Check configured credentials
aws sts get-caller-identity

# Ensure IAM user/role has CloudFormation, ECS, EC2, IAM, CloudWatch permissions
```

### Issue: "Endpoint URL can't be connected to" (LocalStack)

**Cause**: LocalStack not running.

**Solution**:
```bash
# Start LocalStack
docker-compose up -d

# Wait for health check
sleep 5

# Verify
curl http://localhost:4566/_localstack/health
```

### Issue: "No changes needed"

**Cause**: Configuration hasn't changed since last deployment.

**Solution**: This is normal! Stacks are idempotent. Only update if you made config changes.

---

## Integration with deploy.sh

A shell wrapper script (`deploy.sh`) provides convenience commands:

```bash
# Deploy with wrapper script
./deploy.sh deploy dev all

# Check status
./deploy.sh status dev aqcuiflow

# Validate
./deploy.sh validate
```

---

## LocalStack Testing

Test deployments locally without AWS:

```bash
# 1. Set LocalStack endpoint
export AWS_ENDPOINT_URL=http://localhost:4566

# 2. Use dummy credentials
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

# 3. Deploy
python deploy.py deploy dev aqcuiflow

# 4. Check LocalStack
curl http://localhost:4566/_localstack/health
```

See [LOCALSTACK.md](../LOCALSTACK.md) for detailed LocalStack setup.

---

## Best Practices

### 1. Always Validate Before Deploying

```bash
python validate.py
python deploy.py validate
```

### 2. Deploy to Lower Environments First

```bash
# Test in dev first
python deploy.py deploy dev all

# Then staging
python deploy.py deploy staging all

# Finally production
python deploy.py deploy prod all
```

### 3. Keep Configuration in Version Control

```bash
# Commit config changes
git add application/*/dev/config.yaml
git commit -m "Update app configuration"
```

### 4. Review Stack Outputs

```bash
# Check what was created
aws cloudformation describe-stacks --stack-name dev-acquiflow-sg --query 'Stacks[0].Outputs'
```

### 5. Monitor Deployments

```bash
# Watch deployment events
aws cloudformation describe-stack-events --stack-name dev-acquiflow-service

# Monitor ECS service
aws ecs describe-services --cluster dev-ecs-cluster --services dev-acquiflow-service
```

---

## Architecture Overview

```
Environment (dev, qa, staging, prod)
├── ECS Cluster (1 per environment)
├── Application Load Balancer (1 per environment)
│   ├── HTTP Listener
│   ├── HTTPS Listener
│   └── Target Groups (1 per application)
│       ├── Health Checks
│       └── Host-Based Routing Rules
└── Applications (multiple per environment)
    ├── aqcuiflow
    │   ├── Security Groups
    │   ├── IAM Roles
    │   ├── CloudWatch Logs
    │   ├── ECR Repository
    │   ├── ECS Task Definition (API + Nginx containers)
    │   ├── ECS Service
    │   └── Auto Scaling Policies
    └── function-manager
        └── [Same structure as aqcuiflow]
```

---

## Related Documentation

- [Main README](../README.md) - Project overview
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Detailed deployment procedures
- [LOCALSTACK.md](../LOCALSTACK.md) - Local testing with LocalStack
- [.github/copilot-instructions.md](../.github/copilot-instructions.md) - AI agent guidance

---

## Support

For issues or questions:

1. Check troubleshooting section above
2. Review validation errors: `python validate.py`
3. Check CloudFormation events: `aws cloudformation describe-stack-events --stack-name <stack-name>`
4. Review script logs and error messages
5. Check AWS CloudFormation console for detailed error information

---

**Version**: 1.0  
**Last Updated**: February 2026  
**Maintainer**: DevOps Team
