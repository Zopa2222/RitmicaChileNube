# Despliegue en Google Cloud

Este directorio deja la plataforma preparada para Cloud Run, Cloud SQL para PostgreSQL, Cloud Storage privado, CDN mediante balanceador HTTPS, Secret Manager y una tarea diaria de purga.

## Orden seguro de despliegue

1. Cree un proyecto de staging y autentique `gcloud` y Terraform.
2. Cree los seis secretos indicados en `terraform/variables.tf`. `ritmica-database-url` debe usar el socket de Cloud SQL, por ejemplo `postgresql+psycopg://USUARIO:CLAVE@/ritmica_chile?host=/cloudsql/PROYECTO:REGION:INSTANCIA`.
3. Ejecute `terraform init`, copie `terraform.tfvars.example` como `terraform.tfvars`, complete sus valores y aplique Terraform. Terraform muestra la IP a asignar al DNS del dominio; el certificado se habilita cuando el DNS propaga.
4. Ejecute Cloud Build con `infra/cloudbuild.yaml`, indicando `_REGION` y `_STATIC_BUCKET`. Actualice `backend_image` con la imagen generada y aplique Terraform otra vez.
5. Ejecute una sola vez la migración y las cuentas fijas desde un Cloud Run Job con la misma imagen: `flask --app run.py db upgrade` y `flask --app run.py bootstrap-fixed-users`.

El balanceador entrega el frontend y dirige `/api/*` al backend; por ello las cookies HttpOnly conservan el mismo origen. No habilite `ENABLE_LEGACY_ROUTES` en producción.
