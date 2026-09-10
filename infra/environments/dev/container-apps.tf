resource "azurerm_log_analytics_workspace" "container_apps" {
  name                = "log-${local.project_name}-${var.environment}"
  location            = var.app_location
  resource_group_name = azurerm_resource_group.main.name

  sku               = "PerGB2018"
  retention_in_days = 30

  tags = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.project_name}-${var.environment}"
  location                   = var.app_location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.container_apps.id

  tags = local.tags
}