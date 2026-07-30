variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "southamerica-west1"
}
variable "app_name" {
  type    = string
  default = "ritmica-chile"
}
variable "domain_name" {
  type        = string
  description = "FQDN served by the HTTPS load balancer, for example puntajes.ritmicachile.cl."
}
variable "backend_image" {
  type        = string
  description = "Artifact Registry image produced by infra/cloudbuild.yaml."
}
variable "database_url_secret_id" {
  type    = string
  default = "ritmica-database-url"
}
variable "jwt_secret_id" {
  type    = string
  default = "ritmica-jwt-secret"
}
variable "super_admin_username_secret_id" {
  type    = string
  default = "ritmica-super-admin-username"
}
variable "super_admin_password_secret_id" {
  type    = string
  default = "ritmica-super-admin-password"
}
variable "global_admin_username_secret_id" {
  type    = string
  default = "ritmica-global-admin-username"
}
variable "global_admin_password_secret_id" {
  type    = string
  default = "ritmica-global-admin-password"
}
