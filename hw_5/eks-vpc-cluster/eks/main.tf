module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  vpc_id     = data.terraform_remote_state.vpc.outputs.vpc_id
  subnet_ids = data.terraform_remote_state.vpc.outputs.private_subnets

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  enable_cluster_creator_admin_permissions = true

  eks_managed_node_group_defaults = {
    ami_type = "AL2_x86_64"
  }

  eks_managed_node_groups = {
    cpu-nodes = {
      instance_types = var.cpu_node_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = var.cpu_node_min_size
      max_size     = var.cpu_node_max_size
      desired_size = var.cpu_node_desired_size

      labels = {
        workload-type = "cpu"
      }

      tags = {
        NodeGroup = "cpu-nodes"
      }
    }

    gpu-nodes = {
      instance_types = var.gpu_node_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = var.gpu_node_min_size
      max_size     = var.gpu_node_max_size
      desired_size = var.gpu_node_desired_size

      labels = {
        workload-type = "gpu"
      }

      tags = {
        NodeGroup = "gpu-nodes"
      }
    }
  }

  tags = {
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}