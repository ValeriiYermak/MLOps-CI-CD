terraform {
  backend "s3" {
    bucket  = "tfstate-goit"
    key     = "eks/terraform.tfstate"
    region  = "us-east-1"
    profile = "goit-terraform"
    encrypt = true
  }
}