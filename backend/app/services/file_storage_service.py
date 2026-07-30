from pathlib import Path

from flask import current_app


class FileStorageError(RuntimeError):
    pass


def store_bytes(object_name, contents, content_type):
    backend = current_app.config['FILE_STORAGE_BACKEND']
    if backend == 'local':
        configured_root = current_app.config.get('LOCAL_STORAGE_PATH')
        root = (
            Path(configured_root)
            if configured_root
            else Path(current_app.instance_path) / 'uploads'
        )
        destination = root / Path(object_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
        return object_name

    if backend == 'gcs':
        from google.cloud import storage

        bucket_name = current_app.config.get('GCS_BUCKET')
        if not bucket_name:
            raise FileStorageError('GCS_BUCKET no está configurado')
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(object_name)
        blob.upload_from_string(contents, content_type=content_type)
        return object_name

    raise FileStorageError(
        f'Backend de almacenamiento no soportado: {backend}'
    )


def delete_object(object_name):
    backend = current_app.config['FILE_STORAGE_BACKEND']
    if backend == 'local':
        configured_root = current_app.config.get('LOCAL_STORAGE_PATH')
        root = (
            Path(configured_root)
            if configured_root
            else Path(current_app.instance_path) / 'uploads'
        ).resolve()
        target = (root / Path(object_name)).resolve()
        if root not in target.parents:
            raise FileStorageError('Ruta de almacenamiento inválida')
        if target.exists():
            target.unlink()
        return

    if backend == 'gcs':
        from google.cloud import storage

        bucket_name = current_app.config.get('GCS_BUCKET')
        if not bucket_name:
            raise FileStorageError('GCS_BUCKET no está configurado')
        storage.Client().bucket(bucket_name).blob(object_name).delete()
        return

    raise FileStorageError(
        f'Backend de almacenamiento no soportado: {backend}'
    )
