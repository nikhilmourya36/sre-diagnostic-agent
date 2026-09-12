# Minimal EKS cluster — deliberately small.
#
# This is a TARGET for the diagnostic agent project, not production
# infrastructure. Don't add node groups, autoscaling policies, or
# multi-AZ HA here until the agent side actually needs something more
# complex to diagnose. Start small, prove the loop works, then grow.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# Networking — minimal VPC, public subnets only (fine for a demo/portfolio
# cluster; do not reuse this networking setup for anything handling real
# user data without adding private subnets + NAT).
# ---------------------------------------------------------------------------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.cluster_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  public_subnets  = ["10.0.1.0/24", "10.0.2.0/24"]
  private_subnets = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = true # one NAT, not one per AZ — keeps cost down
  enable_dns_hostnames = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }
}

# ---------------------------------------------------------------------------
# EKS cluster — small, single managed node group.
# ---------------------------------------------------------------------------

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.35" # one version behind latest (1.36) for stability —
  # AWS EKS periodically retires old versions from new-cluster creation, so
  # if this fails with "unsupported Kubernetes version" again in the
  # future, check current supported versions and bump this

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = true

  eks_managed_node_groups = {
    default = {
      min_size     = 1
      max_size     = 2
      desired_size = 2

      instance_types = ["t3.medium"]
      capacity_type  = "ON_DEMAND"
    }
  }

  # Lets you (and later the agent, via IRSA) read pod/deployment status.
  enable_cluster_creator_admin_permissions = true
}

# ---------------------------------------------------------------------------
# ECR repository — for the demo-backend image.
#
# Deliberately NOT scan-on-push: basic scanning is free either way, but
# scan-on-push adds a delay to every push and isn't needed for a demo
# project. Enhanced (paid) scanning is never enabled here.
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "demo_backend" {
  name                 = "demo-backend"
  image_tag_mutability = "MUTABLE" # lets `:latest` be overwritten on each push — fine for a demo, not for prod

  image_scanning_configuration {
    scan_on_push = false
  }

  force_delete = true # lets `terraform destroy` remove the repo even if it still has images in it —
  # convenient for a demo project you rebuild often; would NOT want this on a real prod repo
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "configure_kubectl" {
  value = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.demo_backend.repository_url
}
