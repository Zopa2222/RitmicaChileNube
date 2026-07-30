output "dns_ip" {
  value = google_compute_global_address.web.address
}
output "private_bucket" {
  value = google_storage_bucket.private_files.name
}
output "static_bucket" {
  value = google_storage_bucket.static.name
}
output "cloud_sql_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}
