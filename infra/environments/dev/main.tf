locals {
  project_name = "flightdelay"

  tags = {
    project     = local.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.project_name}-${var.environment}"
  location = var.location

  tags = local.tags
}