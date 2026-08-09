terraform {
  backend "s3" {
    bucket  = "tfstate-goit"
    key     = "vpc/terraform.tfstate"
    region  = "us-east-1"
    profile = "goit-terraform"
    encrypt = true
  }
}