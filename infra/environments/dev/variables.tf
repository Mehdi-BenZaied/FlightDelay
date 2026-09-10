variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "swedencentral"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}
variable "app_location" {
  description = "Azure region for Container Apps"
  type        = string
  default     = "austriaeast"
}