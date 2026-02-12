#!/usr/bin/env python3
"""
ECS Migration Deployment Script
Automates CloudFormation stack deployment for ECS migration
"""

import os
import sys
import json
import yaml
import boto3
import argparse
from pathlib import Path
from typing import Dict, List, Optional

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'  # No Color

class ECSDeployer:
    """Handles ECS infrastructure deployment"""
    
    def __init__(self, environment: str, region: str = 'us-east-1', endpoint_url: Optional[str] = None):
        self.environment = environment
        self.region = region
        self.endpoint_url = endpoint_url or os.getenv('AWS_ENDPOINT_URL')
        
        # Initialize CloudFormation client with optional endpoint URL (for LocalStack)
        client_kwargs = {'region_name': region}
        if self.endpoint_url:
            client_kwargs['endpoint_url'] = self.endpoint_url
            
        self.cfn_client = boto3.client('cloudformation', **client_kwargs)
        self.project_root = Path(__file__).parent.parent.absolute()
        
    def print_info(self, message: str):
        """Print info message"""
        print(f"{Colors.GREEN}[INFO]{Colors.NC} {message}")
        
    def print_warning(self, message: str):
        """Print warning message"""
        print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {message}")
        
    def print_error(self, message: str):
        """Print error message"""
        print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")
        
    def load_yaml_config(self, config_path: Path) -> Dict:
        """Load YAML configuration file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.print_error(f"Failed to load config file {config_path}: {e}")
            sys.exit(1)
            
    def load_json_policy(self, policy_path: Path) -> str:
        """Load JSON IAM policy file"""
        try:
            if not policy_path.exists():
                return '{}'
            with open(policy_path, 'r') as f:
                policy = json.load(f)
                return json.dumps(policy)
        except Exception as e:
            self.print_warning(f"Failed to load IAM policy {policy_path}: {e}")
            return '{}'
            
    def deploy_stack(self, stack_name: str, template_file: str, 
                    parameters: List[Dict], tags: List[Dict],
                    capabilities: Optional[List[str]] = None):
        """Deploy CloudFormation stack"""
        template_path = self.project_root / 'template' / template_file
        
        if not template_path.exists():
            self.print_error(f"Template file not found: {template_path}")
            return False
            
        self.print_info(f"Deploying stack: {stack_name}")
        
        try:
            with open(template_path, 'r') as f:
                template_body = f.read()
                
            kwargs = {
                'StackName': stack_name,
                'TemplateBody': template_body,
                'Parameters': parameters,
                'Tags': tags,
            }
            
            if capabilities:
                kwargs['Capabilities'] = capabilities
                
            # Check if stack exists
            try:
                self.cfn_client.describe_stacks(StackName=stack_name)
                operation = 'update'
            except self.cfn_client.exceptions.ClientError:
                operation = 'create'
                
            if operation == 'create':
                response = self.cfn_client.create_stack(**kwargs)
                self.print_info(f"Creating stack: {stack_name}")
            else:
                response = self.cfn_client.update_stack(**kwargs)
                self.print_info(f"Updating stack: {stack_name}")
                
            # Wait for stack operation to complete
            waiter_name = f'stack_{operation}_complete'
            waiter = self.cfn_client.get_waiter(waiter_name)
            waiter.wait(StackName=stack_name)
            
            self.print_info(f"Stack {operation}d successfully: {stack_name}")
            return True
            
        except self.cfn_client.exceptions.ClientError as e:
            error_message = e.response['Error']['Message']
            if 'No updates are to be performed' in error_message:
                self.print_info(f"No changes needed for stack: {stack_name}")
                return True
            else:
                self.print_error(f"Failed to deploy stack {stack_name}: {error_message}")
                return False
        except Exception as e:
            self.print_error(f"Unexpected error deploying {stack_name}: {e}")
            return False
            
    def get_stack_output(self, stack_name: str, output_key: str) -> Optional[str]:
        """Get stack output value"""
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            outputs = response['Stacks'][0].get('Outputs', [])
            
            for output in outputs:
                if output['OutputKey'] == output_key:
                    return output['OutputValue']
            return None
        except Exception as e:
            self.print_warning(f"Failed to get output {output_key} from {stack_name}: {e}")
            return None
            
    def create_parameters(self, config: Dict) -> List[Dict]:
        """Convert config dict to CloudFormation parameters format"""
        parameters = []
        
        for key, value in config.items():
            # Skip stack name keys
            if key.endswith('StackName'):
                continue
                
            # Handle different value types
            if isinstance(value, list):
                # Convert list to comma-separated string
                param_value = ','.join(str(v) for v in value)
            elif isinstance(value, bool):
                param_value = str(value).lower()
            elif value is None:
                continue
            else:
                param_value = str(value)
                
            parameters.append({
                'ParameterKey': key,
                'ParameterValue': param_value
            })
            
        return parameters
        
    def create_tags(self, environment: str, application: str) -> List[Dict]:
        """Create standard tags"""
        return [
            {'Key': 'Environment', 'Value': environment},
            {'Key': 'Application', 'Value': application},
            {'Key': 'ManagedBy', 'Value': 'CloudFormation'}
        ]
        
    def deploy_ecs_cluster(self) -> bool:
        """Deploy ECS cluster"""
        self.print_info("=" * 50)
        self.print_info("Deploying ECS Cluster")
        self.print_info("=" * 50)
        
        config_path = self.project_root / 'infra' / self.environment / 'ecs' / 'config.yaml'
        config = self.load_yaml_config(config_path)
        
        stack_name = f"ecs-cluster-{self.environment}"
        parameters = self.create_parameters(config)
        tags = self.create_tags(self.environment, 'ecs-cluster')
        
        return self.deploy_stack(
            stack_name=stack_name,
            template_file='ecs.yaml',
            parameters=parameters,
            tags=tags
        )
        
    def deploy_application(self, app_name: str) -> bool:
        """Deploy complete application infrastructure"""
        self.print_info("=" * 50)
        self.print_info(f"Deploying Application: {app_name}")
        self.print_info("=" * 50)
        
        config_path = self.project_root / 'application' / app_name / self.environment / 'config.yaml'
        iam_path = self.project_root / 'application' / app_name / self.environment / 'iam.json'
        
        if not config_path.exists():
            self.print_error(f"Config file not found: {config_path}")
            return False
            
        config = self.load_yaml_config(config_path)
        iam_policy = self.load_json_policy(iam_path)
        
        tags = self.create_tags(self.environment, app_name)
        
        # 1. Security Groups
        self.print_info("Step 1/8: Deploying Security Groups")
        sg_stack = config.get('SecurityGroupStackName', f"{app_name}-sg-{self.environment}")
        sg_params = self.create_parameters({
            'Environment': self.environment,
            'ApplicationName': app_name,
            'VpcId': config['VpcId'],
            'AllowedCIDR': config.get('AllowedCIDR', '0.0.0.0/0')
        })
        
        if not self.deploy_stack(sg_stack, 'sg.yaml', sg_params, tags):
            return False
            
        # 2. IAM Roles
        self.print_info("Step 2/8: Deploying IAM Roles")
        iam_stack = config.get('IAMStackName', f"{app_name}-iam-{self.environment}")
        iam_params = self.create_parameters({
            'Environment': self.environment,
            'ApplicationName': app_name,
            'TaskRolePolicyDocument': iam_policy
        })
        
        if not self.deploy_stack(iam_stack, 'iam.yaml', iam_params, tags, 
                                capabilities=['CAPABILITY_NAMED_IAM']):
            return False
            
        # 3. CloudWatch Logs
        self.print_info("Step 3/8: Deploying CloudWatch Log Group")
        cw_stack = config.get('CloudWatchStackName', f"{app_name}-logs-{self.environment}")
        cw_params = self.create_parameters({
            'Environment': self.environment,
            'ApplicationName': app_name,
            'RetentionInDays': config.get('RetentionInDays', 7)
        })
        
        if not self.deploy_stack(cw_stack, 'cloudwatch.yaml', cw_params, tags):
            return False
        
        # 4a. AWS CodeBuild (for CI/CD runner)
        self.print_info("Step 4a/8: Deploying CodeBuild Project")
        codebuild_stack = config.get('CodeBuildStackName', f"{app_name}-codebuild-{self.environment}")
        codebuild_params = self.create_parameters({
            'Environment': self.environment,
            'ApplicationName': app_name,
            'ProjectName': config.get('CodeBuildProjectName', f"{self.environment}-codebuild-runner"),
            'GitHubOrgName': config.get('GitHubOrgName', 'rpx'),
            'WorkflowNamePattern': config.get('WorkflowNamePattern', '.*CI-CodeBuild.*'),
            'ComputeType': config.get('ComputeType', 'BUILD_ARM1_MEDIUM'),
            'Team': config.get('Team', 'DevOps')
        })

        if not self.deploy_stack(codebuild_stack, 'codebuild_runner.yaml', codebuild_params, tags,
                                capabilities=['CAPABILITY_NAMED_IAM']):
            return False
            
        # 4b. ECR Repository
        self.print_info("Step 4b/8: Deploying ECR Repository")
        ecr_stack = config.get('ECRStackName', f"{app_name}-ecr-{self.environment}")
        ecr_params = self.create_parameters({
            'Environment': self.environment,
            'ApplicationName': app_name,
            'ImageTagMutability': config.get('ImageTagMutability', 'MUTABLE'),
            'ScanOnPush': config.get('ScanOnPush', 'true')
        })
        
        if not self.deploy_stack(ecr_stack, 'ecr.yaml', ecr_params, tags):
            return False
            
        # Get outputs from previous stacks
        alb_sg_id = self.get_stack_output(sg_stack, 'ALBSecurityGroupId')
        ecs_sg_id = self.get_stack_output(sg_stack, 'ECSSecurityGroupId')
        # exec_role_arn = self.get_stack_output(iam_stack, 'TaskExecutionRoleArn')
        # task_role_arn = self.get_stack_output(iam_stack, 'TaskRoleArn')
        log_group_name = self.get_stack_output(cw_stack, 'LogGroupName')
        
        # Validate required outputs
        # if not exec_role_arn or not task_role_arn:
        #     self.print_error("Failed to get IAM role ARNs from stack outputs")
        #     self.print_error(f"TaskExecutionRoleArn: {exec_role_arn}")
        #     self.print_error(f"TaskRoleArn: {task_role_arn}")
        #     return False
            
        if not log_group_name:
            self.print_error("Failed to get log group name from stack outputs")
            return False
        
        # 5. Application Load Balancer
        self.print_info("Step 5/8: Deploying Application Load Balancer")
        alb_stack = config.get('ALBStackName', f"{self.environment}-alb")
        alb_params = self.create_parameters({
            'Environment': self.environment,
            'VpcId': config['VpcId'],
            'SubnetIds': config['SubnetIds'],
            'SecurityGroupId': alb_sg_id,
            'CertificateArn': config.get('CertificateArn', '')
        })
        
        if not self.deploy_stack(alb_stack, 'alb.yaml', alb_params, tags):
            return False
        
        # 5.5 Target Group (with host-based routing)
        self.print_info("Step 5.5/8: Deploying Target Group with Host-Based Routing")
        tg_stack = config.get('TargetGroupStackName', f"{app_name}-tg-{self.environment}")
        tg_params = self.create_parameters({
            'Environment': self.environment,
            'ServiceName': app_name,
            'VpcId': config['VpcId'],
            'LoadBalancerName': alb_stack,
            'HostHeaders': config.get('HostHeaders', app_name),
            'ListenerType': config.get('ListenerType', 'HTTPS'),
            'Priority': config.get('Priority', 100),
            'HealthCheckPath': config.get('HealthCheckPath', '/health'),
            'TargetGroupPort': config.get('TargetGroupPort', 80),
            'HealthCheckIntervalSeconds': config.get('HealthCheckIntervalSeconds', 30),
            'HealthCheckTimeoutSeconds': config.get('HealthCheckTimeoutSeconds', 5),
            'HealthyThresholdCount': config.get('HealthyThresholdCount', 2),
            'UnhealthyThresholdCount': config.get('UnhealthyThresholdCount', 3),
            'DeregistrationDelay': config.get('DeregistrationDelay', 30),
            'HealthCheckMatcherHttpCode': config.get('HealthCheckMatcherHttpCode', '200')
        })
        
        if not self.deploy_stack(tg_stack, 'target_group.yaml', tg_params, tags):
            return False
            
        target_group_arn = self.get_stack_output(tg_stack, 'TargetGroupArn')
        
        # 6. Task Definition
        self.print_info("Step 6/9: Deploying ECS Task Definition")
        taskdef_stack = config.get('TaskDefinitionStackName', f"{app_name}-taskdef-{self.environment}")
        taskdef_params = self.create_parameters({
            'Environment': self.environment,
            'ApplicationName': app_name,
            'ExecutionRole': config.get('ExecutionRole', ''),
            'TaskRole': config.get('ExecutionRole', ''),
            'LogGroupName': log_group_name,
            'CPU': config.get('CPU', '256'),
            'Memory': config.get('Memory', '512'),
            'ContainerImage': config.get('ContainerImage', ''),
            'ContainerPort': config.get('ContainerPort', 80),
            'APIContainerImage': config.get('APIContainerImage', ''),
            'APIContainerPort': config.get('APIContainerPort', 8080),
            'UIContainerImage': config.get('UIContainerImage', ''),
            'UIContainerPort': config.get('UIContainerPort', 3000),
            'EnvironmentVariables': config.get('EnvironmentVariables', '[]'),
            'Secrets': config.get('Secrets', '[]')
        })
        
        if not self.deploy_stack(taskdef_stack, 'task_definition.yaml', taskdef_params, tags):
            return False
            
        task_def_arn = self.get_stack_output(taskdef_stack, 'TaskDefinitionArn')
        
        # 7. ECS Service
        self.print_info("Step 7/9: Deploying ECS Service")
        service_stack = config.get('ECSServiceStackName', f"{app_name}-service-{self.environment}")
        service_params = self.create_parameters({
            'Environment': self.environment,
            'ApplicationName': app_name,
            'ClusterName': config['ClusterName'],
            'TaskDefinitionArn': task_def_arn,
            'DesiredCount': config.get('DesiredCount', 1),
            'SubnetIds': config['SubnetIds'],
            'SecurityGroupId': ecs_sg_id,
            'TargetGroupArn': target_group_arn,
            'ContainerName': config.get('ContainerName', app_name),
            'ContainerPort': config.get('ContainerPort', 80),
            'HealthCheckGracePeriodSeconds': config.get('HealthCheckGracePeriodSeconds', 60)
        })
        
        if not self.deploy_stack(service_stack, 'ecs_service.yaml', service_params, tags):
            return False
            
        service_name = self.get_stack_output(service_stack, 'ServiceName')
        
        # 8. Auto Scaling
        self.print_info("Step 8/9: Deploying Auto Scaling")
        autoscaling_stack = config.get('AutoScalingStackName', f"{app_name}-autoscaling-{self.environment}")
        
        alb_full_name = self.get_stack_output(alb_stack, 'LoadBalancerFullName')
        tg_full_name = self.get_stack_output(alb_stack, 'TargetGroupFullName')
        
        autoscaling_params = self.create_parameters({
            'Environment': self.environment,
            'ApplicationName': app_name,
            'ClusterName': config['ClusterName'],
            'ServiceName': service_name,
            'MinCapacity': config.get('MinCapacity', 1),
            'MaxCapacity': config.get('MaxCapacity', 4),
            'EnableCPUScaling': config.get('EnableCPUScaling', 'true'),
            'TargetCPUUtilization': config.get('TargetCPUUtilization', 70),
            'EnableMemoryScaling': config.get('EnableMemoryScaling', 'true'),
            'TargetMemoryUtilization': config.get('TargetMemoryUtilization', 80),
            'EnableRequestCountScaling': config.get('EnableRequestCountScaling', 'false'),
            'ALBFullName': alb_full_name or '',
            'TargetGroupFullName': tg_full_name or ''
        })
        
        if not self.deploy_stack(autoscaling_stack, 'service_autoscaling.yaml', autoscaling_params, tags):
            return False
            
        self.print_info(f"Application deployed successfully: {app_name}")
        return True
        
    def delete_stack(self, stack_name: str, force: bool = False) -> bool:
        """Delete CloudFormation stack"""
        self.print_warning(f"Deleting stack: {stack_name}")
        
        if not force:
            response = input(f"Are you sure you want to delete {stack_name}? (yes/no): ")
            if response.lower() != 'yes':
                self.print_info("Deletion cancelled")
                return True
        
        try:
            self.cfn_client.delete_stack(StackName=stack_name)
            waiter = self.cfn_client.get_waiter('stack_delete_complete')
            waiter.wait(StackName=stack_name)
            
            self.print_info(f"Stack deleted successfully: {stack_name}")
            return True
            
        except self.cfn_client.exceptions.ClientError as e:
            error_message = e.response['Error']['Message']
            if 'does not exist' in error_message:
                self.print_warning(f"Stack does not exist: {stack_name}")
                return True
            else:
                self.print_error(f"Failed to delete stack {stack_name}: {error_message}")
                return False
        except Exception as e:
            self.print_error(f"Unexpected error deleting {stack_name}: {e}")
            return False
            
    def delete_infrastructure(self, environment: str, app_name: str, specific_stack: Optional[str] = None):
        """Delete infrastructure stacks"""
        self.print_info("=" * 50)
        self.print_info(f"Deleting Infrastructure for {environment}")
        self.print_info("=" * 50)
        
        if specific_stack:
            # Delete specific stack
            self.delete_stack(specific_stack, force=False)
            return
        
        # Delete applications
        if app_name == 'all':
            app_dir = self.project_root / 'application'
            applications = [d.name for d in app_dir.iterdir() if d.is_dir()]
        else:
            applications = [app_name]
        
        for app in applications:
            app_env_dir = self.project_root / 'application' / app / environment
            if not app_env_dir.exists():
                self.print_warning(f"Application {app} not configured for {environment}")
                continue
                
            config_file = app_env_dir / 'config.yaml'
            config = self.load_yaml_config(config_file)
            
            self.print_info(f"\nDeleting application: {app}")
            
            # Delete in reverse order: autoscaling, service, taskdef, alb, ecr, logs, iam, sg
            stacks_to_delete = [
                config.get('AutoScalingStackName', f"{environment}-{app}-autoscaling"),
                config.get('ECSServiceStackName', f"{environment}-{app}-service"),
                config.get('TaskDefinitionStackName', f"{environment}-{app}-taskdef"),
                config.get('ALBStackName', f"{environment}-{app}-alb"),
                config.get('ECRStackName', f"{environment}-{app}-ecr"),
                config.get('CloudWatchStackName', f"{environment}-{app}-logs"),
                config.get('IAMStackName', f"{environment}-{app}-iam"),
                config.get('SecurityGroupStackName', f"{environment}-{app}-sg"),
            ]
            
            for stack in stacks_to_delete:
                if not self.delete_stack(stack, force=False):
                    self.print_error(f"Failed to delete stack {stack}, stopping deletion...")
                    return
        
        self.print_info("\n" + "=" * 50)
        self.print_info("Deletion completed successfully!")
        self.print_info("=" * 50)
        
    def print_status(self, environment: str, app_name: str):
        """Print status of stacks"""
        self.print_info("=" * 50)
        self.print_info(f"Stack Status for {environment}")
        self.print_info("=" * 50)
        
        if app_name == 'all':
            # Show ECS cluster
            cluster_stack = f"ecs-cluster-{environment}"
            self._print_stack_status(cluster_stack)
            
            # Show all applications
            app_dir = self.project_root / 'application'
            applications = [d.name for d in app_dir.iterdir() if d.is_dir()]
            
            for app in applications:
                app_env_dir = app_dir / app / environment
                if app_env_dir.exists():
                    self.print_info(f"\nApplication: {app}")
                    config_file = app_env_dir / 'config.yaml'
                    config = self.load_yaml_config(config_file)
                    
                    service_stack = config.get('ECSServiceStackName', f"{environment}-{app}-service")
                    self._print_stack_status(service_stack)
        else:
            app_env_dir = self.project_root / 'application' / app_name / environment
            if app_env_dir.exists():
                config_file = app_env_dir / 'config.yaml'
                config = self.load_yaml_config(config_file)
                
                service_stack = config.get('ECSServiceStackName', f"{environment}-{app_name}-service")
                self._print_stack_status(service_stack)
            else:
                self.print_error(f"Application {app_name} not configured for {environment}")
                
    def _print_stack_status(self, stack_name: str):
        """Print status of a single stack"""
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            stack = response['Stacks'][0]
            
            status = stack['StackStatus']
            status_color = Colors.GREEN if 'COMPLETE' in status else Colors.YELLOW if 'IN_PROGRESS' in status else Colors.RED
            
            print(f"  {Colors.BLUE}Stack:{Colors.NC} {stack_name}")
            print(f"  {Colors.BLUE}Status:{Colors.NC} {status_color}{status}{Colors.NC}")
            
            if 'Outputs' in stack and stack['Outputs']:
                print(f"  {Colors.BLUE}Outputs:{Colors.NC}")
                for output in stack['Outputs']:
                    print(f"    • {output['OutputKey']}: {output['OutputValue']}")
        except self.cfn_client.exceptions.ClientError as e:
            if 'does not exist' in str(e):
                self.print_warning(f"Stack does not exist: {stack_name}")
            else:
                self.print_error(f"Error retrieving stack status: {e}")

def main():
    parser = argparse.ArgumentParser(description='Deploy/Manage ECS infrastructure')
    parser.add_argument('action', choices=['validate', 'deploy', 'update', 'delete', 'status'],
                       help='Action to perform')
    parser.add_argument('environment', nargs='?', help='Environment (dev/qa/stage/prod)')
    parser.add_argument('application', nargs='?', default='all', 
                       help='Application name or "all"')
    parser.add_argument('--region', default='us-east-1', 
                       help='AWS region (default: us-east-1)')
    parser.add_argument('--stack', help='Specific stack name to delete')
    
    args = parser.parse_args()
    
    # Validate action
    if args.action in ['deploy', 'update', 'delete', 'status'] and not args.environment:
        print(f"{Colors.RED}[ERROR]{Colors.NC} environment is required for {args.action} action")
        sys.exit(1)
    
    # Run validation action
    if args.action == 'validate':
        import subprocess
        result = subprocess.run([sys.executable, str(Path(__file__).parent / 'validate.py')], 
                              cwd=Path(__file__).parent.parent)
        sys.exit(result.returncode)
    
    # Get endpoint URL from environment (for LocalStack support)
    endpoint_url = os.getenv('AWS_ENDPOINT_URL')
    deployer = ECSDeployer(args.environment, args.region, endpoint_url)
    
    # Deploy action
    if args.action == 'deploy':
        # Deploy ECS cluster
        if not deployer.deploy_ecs_cluster():
            sys.exit(1)
            
        # Deploy applications
        if args.application == 'all':
            app_dir = deployer.project_root / 'application'
            applications = [d.name for d in app_dir.iterdir() if d.is_dir()]
            
            for app in applications:
                app_env_dir = app_dir / app / args.environment
                if app_env_dir.exists():
                    if not deployer.deploy_application(app):
                        sys.exit(1)
        else:
            if not deployer.deploy_application(args.application):
                sys.exit(1)
                
        deployer.print_info("=" * 50)
        deployer.print_info("Deployment completed successfully!")
        deployer.print_info("=" * 50)
    
    # Update action
    elif args.action == 'update':
        deployer.print_info("=" * 50)
        deployer.print_info("Updating Infrastructure")
        deployer.print_info("=" * 50)
        
        # Update ECS cluster
        deployer.print_info("Updating ECS Cluster...")
        if not deployer.deploy_ecs_cluster():
            deployer.print_warning("ECS cluster update skipped (no changes)")
            
        # Update applications
        if args.application == 'all':
            app_dir = deployer.project_root / 'application'
            applications = [d.name for d in app_dir.iterdir() if d.is_dir()]
            
            for app in applications:
                app_env_dir = app_dir / app / args.environment
                if app_env_dir.exists():
                    deployer.print_info(f"Updating application: {app}")
                    if not deployer.deploy_application(app):
                        deployer.print_warning(f"Application {app} update skipped (no changes)")
        else:
            deployer.print_info(f"Updating application: {args.application}")
            if not deployer.deploy_application(args.application):
                deployer.print_warning(f"Application update skipped (no changes)")
                
        deployer.print_info("=" * 50)
        deployer.print_info("Update completed!")
        deployer.print_info("=" * 50)
    
    # Delete action
    elif args.action == 'delete':
        deployer.delete_infrastructure(args.environment, args.application, args.stack)
    
    # Status action
    elif args.action == 'status':
        deployer.print_status(args.environment, args.application)

if __name__ == '__main__':
    main()