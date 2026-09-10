output "resource_group_name" {
  description = "FlightDelay resource group"
  value       = azurerm_resource_group.main.name
}

output "vnet_name" {
  description = "FlightDelay virtual network"
  value       = azurerm_virtual_network.main.name
}

output "vnet_address_space" {
  description = "VNet CIDR"
  value       = azurerm_virtual_network.main.address_space
}

output "app_subnet_id" {
  description = "Application subnet ID"
  value       = azurerm_subnet.app.id
}