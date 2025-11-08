"""
Cloud storage manager for uploading files.
"""
import os
import boto3

class StorageError(FluxInferenceError):
    """Base exception for storage-related errors."""
    pass

class CloudflareR2Storage:
    """Manages file uploads to Cloudflare R2 storage."""

    def __init__(self, account_id=None, access_key_id=None, secret_access_key=None, bucket_name=None):
        """
        Initialize R2 storage client.

        Args:
            account_id: Cloudflare account ID (defaults to env var CLOUDFLARE_ACCOUNT_ID)
            access_key_id: Cloudflare access key ID (defaults to env var CLOUDFLARE_ACCESS_KEY_ID)
            secret_access_key: Cloudflare secret access key (defaults to env var CLOUDFLARE_SECRET_ACCESS_KEY)
            bucket_name: R2 bucket name (defaults to env var or "headshotpro-temporary-files")
        """
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.access_key_id = access_key_id or os.environ.get("CLOUDFLARE_ACCESS_KEY_ID")
        self.secret_access_key = secret_access_key or os.environ.get("CLOUDFLARE_SECRET_ACCESS_KEY")
        self.bucket_name = bucket_name or os.environ.get("CLOUDFLARE_R2_BUCKET", "headshotpro-temporary-files")

        if not all([self.account_id, self.access_key_id, self.secret_access_key]):
            raise ValueError("Cloudflare R2 credentials not provided")

        self.endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"

    def _get_client(self):
        """Get or create boto3 S3 client for R2."""
        return boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name='auto'
        )

    def upload_bytes(self, file_bytes, object_key, content_type='image/jpeg'):
        """
        Upload bytes to R2 storage.

        Args:
            file_bytes: File data as bytes
            object_key: Storage path/key for the object
            content_type: MIME type of the file (default: 'image/jpeg')

        Returns:
            dict: File metadata including url, content_type, file_name, and file_size

        Raises:
            StorageUploadError: If upload fails
        """
        try:
            print(f"📤 Uploading to Cloudflare R2: {object_key}")

            s3_client = self._get_client()

            s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=file_bytes,
                ContentType=content_type
            )

            # Extract filename from object_key
            file_name = object_key.split('/')[-1]

            print(f"✅ Uploaded successfully: {object_key}")

            return {
                "url": object_key,
                "content_type": content_type,
                "file_name": file_name,
                "file_size": len(file_bytes)
            }

        except Exception as e:
            error_msg = f"Failed to upload to Cloudflare R2: {str(e)}"
            print(f"❌ {error_msg}")
            raise StorageUploadError(error_msg) from e

    def upload_image(self, image_bytes, prefix="modal/flux-images", extension="jpg"):
        """
        Upload image bytes with auto-generated filename.

        Args:
            image_bytes: Image data as bytes
            prefix: Storage path prefix (default: "modal/flux-images")
            extension: File extension (default: "jpg")

        Returns:
            dict: File metadata including url, content_type, file_name, and file_size
        """
        object_key = generate_object_key(prefix=prefix, extension=extension)
        return self.upload_bytes(image_bytes, object_key, content_type='image/jpeg')


def generate_object_key(prefix="modal/flux-images", extension="jpg"):
    """
    Generate a unique object key for storage.

    Args:
        prefix: Storage path prefix (default: "modal/flux-images")
        extension: File extension without dot (default: "jpg")

    Returns:
        str: Object key path
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}/{timestamp}_{unique_id}.{extension}"