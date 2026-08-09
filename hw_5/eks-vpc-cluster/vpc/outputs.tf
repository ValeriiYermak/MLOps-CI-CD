output "vpc_id" {
  description = "ID створеної VPC"
  value       = module.vpc.vpc_id
}

output "public_subnets" {
  description = "Список ID public subnet-ів"
  value       = module.vpc.public_subnets
}

output "private_subnets" {
  description = "Список ID private subnet-ів"
  value       = module.vpc.private_subnets
}