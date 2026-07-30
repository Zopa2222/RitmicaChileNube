locals {
  enabled_services = [
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "compute.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
  ]
  secret_ids = [
    var.database_url_secret_id, var.jwt_secret_id,
    var.super_admin_username_secret_id, var.super_admin_password_secret_id,
    var.global_admin_username_secret_id, var.global_admin_password_secret_id,
  ]
}

resource "google_project_service" "api" {
  for_each           = toset(local.enabled_services)
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "backend" {
  location      = var.region
  repository_id = "ritmica"
  format        = "DOCKER"
  depends_on    = [google_project_service.api]
}

resource "google_storage_bucket" "static" {
  name                        = "${var.project_id}-${var.app_name}-web"
  location                    = "US"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }
}

resource "google_storage_bucket" "private_files" {
  name                        = "${var.project_id}-${var.app_name}-private"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }
}

resource "google_sql_database_instance" "postgres" {
  name             = "${var.app_name}-postgres"
  database_version = "POSTGRES_16"
  region           = var.region
  settings {
    tier              = "db-custom-1-3840"
    availability_type = "ZONAL"
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
    ip_configuration { ipv4_enabled = true }
  }
  deletion_protection = true
  depends_on          = [google_project_service.api]
}

resource "google_sql_database" "application" {
  name     = "ritmica_chile"
  instance = google_sql_database_instance.postgres.name
}

resource "google_service_account" "runtime" {
  account_id   = "ritmica-runtime"
  display_name = "Rítmica Chile runtime"
}

resource "google_project_iam_member" "cloud_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_storage_bucket_iam_member" "runtime_private_files" {
  bucket = google_storage_bucket.private_files.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

data "google_secret_manager_secret" "runtime" {
  for_each   = toset(local.secret_ids)
  secret_id  = each.value
  depends_on = [google_project_service.api]
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each  = data.google_secret_manager_secret.runtime
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "backend" {
  name     = "${var.app_name}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  template {
    service_account = google_service_account.runtime.email
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = [google_sql_database_instance.postgres.connection_name] }
    }
    containers {
      image = var.backend_image
      ports { container_port = 8080 }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name  = "APP_ENV"
        value = "production"
      }
      env {
        name  = "CORS_ORIGINS"
        value = "https://${var.domain_name}"
      }
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.private_files.name
      }
      env {
        name  = "ENABLE_LEGACY_ROUTES"
        value = "false"
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime[var.database_url_secret_id].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "JWT_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime[var.jwt_secret_id].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SUPER_ADMIN_USERNAME"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime[var.super_admin_username_secret_id].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SUPER_ADMIN_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime[var.super_admin_password_secret_id].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GLOBAL_ADMIN_USERNAME"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime[var.global_admin_username_secret_id].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GLOBAL_ADMIN_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime[var.global_admin_password_secret_id].secret_id
            version = "latest"
          }
        }
      }
    }
  }
  depends_on = [google_project_iam_member.cloud_sql, google_secret_manager_secret_iam_member.runtime]
}

resource "google_compute_region_network_endpoint_group" "backend" {
  name                  = "${var.app_name}-api-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run { service = google_cloud_run_v2_service.backend.name }
}

resource "google_compute_backend_service" "backend" {
  name                  = "${var.app_name}-api-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTP"
  backend { group = google_compute_region_network_endpoint_group.backend.id }
}

resource "google_compute_backend_bucket" "frontend" {
  name        = "${var.app_name}-web-backend"
  bucket_name = google_storage_bucket.static.name
  enable_cdn  = true
}

resource "google_compute_url_map" "web" {
  name            = "${var.app_name}-url-map"
  default_service = google_compute_backend_bucket.frontend.id
  host_rule {
    hosts        = [var.domain_name]
    path_matcher = "application"
  }
  path_matcher {
    name            = "application"
    default_service = google_compute_backend_bucket.frontend.id
    path_rule {
      paths   = ["/api", "/api/*"]
      service = google_compute_backend_service.backend.id
    }
  }
}

resource "google_compute_managed_ssl_certificate" "web" {
  name = "${var.app_name}-certificate"
  managed { domains = [var.domain_name] }
}

resource "google_compute_target_https_proxy" "web" {
  name             = "${var.app_name}-https"
  url_map          = google_compute_url_map.web.id
  ssl_certificates = [google_compute_managed_ssl_certificate.web.id]
}

resource "google_compute_global_address" "web" {
  name = "${var.app_name}-ip"
}
resource "google_compute_global_forwarding_rule" "web" {
  name                  = "${var.app_name}-https-rule"
  target                = google_compute_target_https_proxy.web.id
  port_range            = "443"
  ip_address            = google_compute_global_address.web.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

resource "google_cloud_run_v2_job" "purge" {
  name     = "${var.app_name}-purge"
  location = var.region
  template {
    template {
      service_account = google_service_account.runtime.email
      volumes {
        name = "cloudsql"
        cloud_sql_instance { instances = [google_sql_database_instance.postgres.connection_name] }
      }
      containers {
        image   = var.backend_image
        command = ["flask"]
        args    = ["--app", "run.py", "purge-expired-championships"]
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
        env {
          name  = "APP_ENV"
          value = "production"
        }
        env {
          name  = "GCS_BUCKET"
          value = google_storage_bucket.private_files.name
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.runtime[var.database_url_secret_id].secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "JWT_SECRET_KEY"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.runtime[var.jwt_secret_id].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
}

resource "google_service_account" "scheduler" {
  account_id   = "ritmica-scheduler"
  display_name = "Rítmica Chile scheduler"
}
resource "google_cloud_run_v2_job_iam_member" "scheduler" {
  name     = google_cloud_run_v2_job.purge.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}
resource "google_cloud_scheduler_job" "purge" {
  name      = "${var.app_name}-purge-expired"
  region    = var.region
  schedule  = "15 3 * * *"
  time_zone = "America/Santiago"
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.purge.name}:run"
    oauth_token { service_account_email = google_service_account.scheduler.email }
  }
}
