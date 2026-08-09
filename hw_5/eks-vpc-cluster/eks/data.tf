data "terraform_remote_state" "vpc" {
  backend = "s3"

  config = {
    bucket  = "tfstate-goit"
    key     = "vpc/terraform.tfstate"
    region  = "us-east-1"
    profile = "goit-terraform"
  }
}