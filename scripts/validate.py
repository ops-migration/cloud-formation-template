#!/usr/bin/env python3
"""
ECS Migration Configuration Validator
Validates YAML configs, JSON policies, and CloudFormation templates
"""

import os
import sys
import json
import yaml
import boto3
from pathlib import Path
from typing import Dict, List, Tuple
import re

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

class ConfigValidator:
    """Validates all project configurations"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.absolute()
        self.errors = []
        self.warnings = []
        self.success_count = 0
        
    def print_header(self, title: str):
        """Print section header"""
        print(f"\n{Colors.BLUE}{'=' * 60}")
        print(f"{title}")
        print(f"{'=' * 60}{Colors.NC}\n")
        
    def print_success(self, message: str):
        """Print success message"""
        print(f"{Colors.GREEN}✓{Colors.NC} {message}")
        self.success_count += 1
        
    def print_warning(self, message: str):
        """Print warning message"""
        print(f"{Colors.YELLOW}⚠{Colors.NC} {message}")
        self.warnings.append(message)
        
    def print_error(self, message: str):
        """Print error message"""
        print(f"{Colors.RED}✗{Colors.NC} {message}")
        self.errors.append(message)
        
    def validate_yaml_syntax(self, file_path: Path, is_cloudformation: bool = False) -> bool:
        """Validate YAML file syntax"""
        try:
            with open(file_path, 'r') as f:
                if is_cloudformation:
                    # For CloudFormation templates, use a loader that ignores unsupported tags
                    class CloudFormationLoader(yaml.SafeLoader):
                        pass
                    
                    # Add constructors for CloudFormation intrinsic functions
                    def constructor(loader, tag_suffix, node):
                        if isinstance(node, yaml.MappingNode):
                            return loader.construct_mapping(node)
                        elif isinstance(node, yaml.SequenceNode):
                            return loader.construct_sequence(node)
                        else:
                            return loader.construct_scalar(node)
                    
                    CloudFormationLoader.add_multi_constructor('!', constructor)
                    yaml.load(f, Loader=CloudFormationLoader)
                else:
                    yaml.safe_load(f)
            return True
        except yaml.YAMLError as e:
            self.print_error(f"Invalid YAML in {file_path.relative_to(self.project_root)}: {str(e)[:100]}")
            return False
        except Exception as e:
            self.print_error(f"Error reading {file_path.relative_to(self.project_root)}: {str(e)}")
            return False
            
    def validate_json_syntax(self, file_path: Path) -> bool:
        """Validate JSON file syntax"""
        try:
            with open(file_path, 'r') as f:
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            self.print_error(f"Invalid JSON in {file_path.relative_to(self.project_root)}: {str(e)[:100]}")
            return False
        except Exception as e:
            self.print_error(f"Error reading {file_path.relative_to(self.project_root)}: {str(e)}")
            return False
            
    def validate_config_keys(self, config: Dict, app_name: str, env: str) -> bool:
        """Validate required configuration keys"""
        required_keys = {
            'Environment', 'ApplicationName', 'ClusterName', 'DesiredCount',
            'MinCapacity', 'MaxCapacity', 'ContainerPort', 'CPU', 'Memory',
            'VpcId', 'SubnetIds', 'HealthCheckPath', 'TargetGroupPort'
        }
        
        missing_keys = required_keys - set(config.keys())
        if missing_keys:
            self.print_error(f"Missing required keys in {app_name}/{env}: {', '.join(missing_keys)}")
            return False
        return True
        
    def validate_aws_resource_ids(self, config: Dict, app_name: str) -> bool:
        """Validate AWS resource IDs format"""
        vpc_id = config.get('VpcId', '')
        subnet_ids = config.get('SubnetIds', [])
        
        vpc_pattern = r'^vpc-[a-f0-9]{17}$'
        subnet_pattern = r'^subnet-[a-f0-9]{17}$'
        
        is_valid = True
        
        # Check if using placeholder values
        if '<' in vpc_id or 'x' in vpc_id.lower() or vpc_id.endswith('x'):
            self.print_warning(f"{app_name}: VPC ID contains placeholder value - needs to be replaced before deployment")
        elif vpc_id and not re.match(vpc_pattern, vpc_id):
            self.print_error(f"{app_name}: Invalid VPC ID format: {vpc_id}")
            is_valid = False
            
        for subnet_id in subnet_ids:
            if '<' in subnet_id or 'x' in subnet_id.lower() or 'y' in subnet_id.lower() or 'z' in subnet_id.lower():
                self.print_warning(f"{app_name}: Subnet ID contains placeholder value - needs to be replaced before deployment")
            elif subnet_id and not re.match(subnet_pattern, subnet_id):
                self.print_error(f"{app_name}: Invalid Subnet ID format: {subnet_id}")
                is_valid = False
                
        return is_valid
        
    def validate_container_config(self, config: Dict, app_name: str) -> bool:
        """Validate container configuration"""
        has_single = 'ContainerImage' in config and config['ContainerImage']
        has_dual = 'APIContainerImage' in config and 'UIContainerImage' in config
        
        if not (has_single or has_dual):
            self.print_error(f"{app_name}: No container images defined (needs ContainerImage or APIContainerImage+UIContainerImage)")
            return False
            
        if has_single and '<' not in config.get('ContainerImage', ''):
            self.print_success(f"{app_name}: Single-container configuration is valid")
        elif has_dual and '<' not in config.get('APIContainerImage', '') and '<' not in config.get('UIContainerImage', ''):
            self.print_success(f"{app_name}: Dual-container configuration is valid")
        else:
            self.print_warning(f"{app_name}: Container image URIs contain placeholders - needs to be replaced before deployment")
            
        return True
        
    def validate_scaling_config(self, config: Dict, app_name: str) -> bool:
        """Validate auto-scaling configuration"""
        try:
            min_cap = int(config.get('MinCapacity', 1))
            max_cap = int(config.get('MaxCapacity', 1))
            desired = int(config.get('DesiredCount', 1))
            
            if min_cap > max_cap:
                self.print_error(f"{app_name}: MinCapacity ({min_cap}) > MaxCapacity ({max_cap})")
                return False
            if desired < min_cap or desired > max_cap:
                self.print_error(f"{app_name}: DesiredCount ({desired}) outside range [{min_cap}, {max_cap}]")
                return False
                
            self.print_success(f"{app_name}: Scaling configuration is valid")
            return True
        except ValueError as e:
            self.print_error(f"{app_name}: Invalid scaling values: {e}")
            return False
            
    def validate_environment_variables(self, config: Dict, app_name: str) -> bool:
        """Validate environment variables JSON"""
        env_vars = config.get('EnvironmentVariables', '[]')
        
        if isinstance(env_vars, str):
            try:
                parsed = json.loads(env_vars)
                if isinstance(parsed, list):
                    self.print_success(f"{app_name}: Environment variables JSON is valid")
                    return True
                else:
                    self.print_error(f"{app_name}: EnvironmentVariables must be a JSON array, got {type(parsed).__name__}")
                    return False
            except json.JSONDecodeError as e:
                self.print_error(f"{app_name}: Invalid JSON in EnvironmentVariables: {str(e)[:100]}")
                return False
        return True
        
    def validate_secrets(self, config: Dict, app_name: str) -> bool:
        """Validate secrets JSON"""
        secrets = config.get('Secrets', '[]')
        
        if isinstance(secrets, str):
            try:
                parsed = json.loads(secrets)
                if isinstance(parsed, list):
                    self.print_success(f"{app_name}: Secrets JSON is valid")
                    return True
                else:
                    self.print_error(f"{app_name}: Secrets must be a JSON array, got {type(parsed).__name__}")
                    return False
            except json.JSONDecodeError as e:
                self.print_error(f"{app_name}: Invalid JSON in Secrets: {str(e)[:100]}")
                return False
        return True
        
    def validate_iam_policy(self, policy_path: Path, app_name: str) -> bool:
        """Validate IAM policy JSON"""
        if not policy_path.exists():
            self.print_warning(f"{app_name}: No iam.json found - using default empty policy")
            return True
            
        if not self.validate_json_syntax(policy_path):
            return False
            
        try:
            with open(policy_path, 'r') as f:
                policy = json.load(f)
                
            if not isinstance(policy, dict):
                self.print_error(f"{app_name}: iam.json must be a JSON object")
                return False
                
            self.print_success(f"{app_name}: IAM policy is valid JSON")
            return True
        except Exception as e:
            self.print_error(f"{app_name}: Error validating IAM policy: {e}")
            return False
            
    def validate_template(self, template_path: Path) -> bool:
        """Validate CloudFormation template"""
        if not self.validate_yaml_syntax(template_path, is_cloudformation=True):
            return False
            
        try:
            with open(template_path, 'r') as f:
                # Use CloudFormation-aware YAML loader
                class CloudFormationLoader(yaml.SafeLoader):
                    pass
                
                def constructor(loader, tag_suffix, node):
                    if isinstance(node, yaml.MappingNode):
                        return loader.construct_mapping(node)
                    elif isinstance(node, yaml.SequenceNode):
                        return loader.construct_sequence(node)
                    else:
                        return loader.construct_scalar(node)
                
                CloudFormationLoader.add_multi_constructor('!', constructor)
                template = yaml.load(f, Loader=CloudFormationLoader)
                
            # Check required CF template sections
            if 'AWSTemplateFormatVersion' not in template:
                self.print_warning(f"{template_path.name}: Missing AWSTemplateFormatVersion")
                
            if 'Resources' not in template or not template['Resources']:
                self.print_error(f"{template_path.name}: No resources defined in template")
                return False
                
            self.print_success(f"{template_path.name}: Template is valid")
            return True
        except Exception as e:
            self.print_error(f"{template_path.name}: Error validating template: {e}")
            return False
            
    def run_full_validation(self) -> Tuple[bool, str]:
        """Run complete validation suite"""
        self.print_header("ECS MIGRATION PROJECT VALIDATION")
        
        # 1. Validate CloudFormation Templates
        self.print_header("1. CloudFormation Templates")
        templates_dir = self.project_root / 'template'
        template_results = []
        
        for template_file in sorted(templates_dir.glob('*.yaml')):
            result = self.validate_template(template_file)
            template_results.append(result)
            
        # 2. Validate ECS Cluster Config
        self.print_header("2. ECS Cluster Configuration")
        ecs_configs = self.project_root / 'infra'
        
        for env_dir in sorted(ecs_configs.glob('*/ecs')):
            env_name = env_dir.parent.name
            config_file = env_dir / 'config.yaml'
            
            if config_file.exists():
                if self.validate_yaml_syntax(config_file):
                    config = yaml.safe_load(config_file.read_text())
                    self.print_success(f"{env_name}/ecs: Config syntax is valid")
                    
                    # Validate AWS resource IDs
                    self.validate_aws_resource_ids(config, f"ECS-{env_name}")
                    
        # 3. Validate Application Configs
        self.print_header("3. Application Configurations")
        app_dir = self.project_root / 'application'
        app_results = []
        
        for app_folder in sorted(app_dir.iterdir()):
            if app_folder.is_dir():
                app_name = app_folder.name
                
                for env_folder in sorted(app_folder.iterdir()):
                    if env_folder.is_dir():
                        env_name = env_folder.name
                        config_file = env_folder / 'config.yaml'
                        iam_file = env_folder / 'iam.json'
                        
                        print(f"\n{Colors.BLUE}Validating {app_name}/{env_name}:{Colors.NC}")
                        
                        # Validate config YAML
                        if not config_file.exists():
                            self.print_error(f"{app_name}/{env_name}: config.yaml not found")
                            app_results.append(False)
                            continue
                            
                        if not self.validate_yaml_syntax(config_file):
                            app_results.append(False)
                            continue
                            
                        config = yaml.safe_load(config_file.read_text())
                        
                        # Run all config validations
                        checks = [
                            self.validate_config_keys(config, app_name, env_name),
                            self.validate_aws_resource_ids(config, app_name),
                            self.validate_container_config(config, app_name),
                            self.validate_scaling_config(config, app_name),
                            self.validate_environment_variables(config, app_name),
                            self.validate_secrets(config, app_name),
                            self.validate_iam_policy(iam_file, app_name)
                        ]
                        
                        app_results.append(all(checks))
        
        # Summary
        self.print_header("VALIDATION SUMMARY")
        
        total_checks = self.success_count + len(self.errors) + len(self.warnings)
        print(f"{Colors.GREEN}✓ Passed: {self.success_count}{Colors.NC}")
        print(f"{Colors.YELLOW}⚠ Warnings: {len(self.warnings)}{Colors.NC}")
        print(f"{Colors.RED}✗ Errors: {len(self.errors)}{Colors.NC}")
        print(f"\nTotal Checks: {total_checks}")
        
        if self.errors:
            print(f"\n{Colors.RED}ERRORS FOUND:{Colors.NC}")
            for error in self.errors:
                print(f"  • {error}")
                
        if self.warnings:
            print(f"\n{Colors.YELLOW}WARNINGS:{Colors.NC}")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        all_passed = len(self.errors) == 0
        status = f"{Colors.GREEN}VALIDATION PASSED{Colors.NC}" if all_passed else f"{Colors.RED}VALIDATION FAILED{Colors.NC}"
        
        print(f"\n{status}")
        
        return all_passed, "VALIDATION PASSED" if all_passed else "VALIDATION FAILED"

def main():
    validator = ConfigValidator()
    passed, message = validator.run_full_validation()
    sys.exit(0 if passed else 1)

if __name__ == '__main__':
    main()
