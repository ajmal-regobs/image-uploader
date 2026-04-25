# image-uploader

Flask app that uploads images to S3 and stores metadata in Postgres. A single HTML page handles upload + gallery view.

## Architecture

- **S3** — image storage. Credentials come from the **IAM role** on the host (EC2 instance profile, ECS task role, or EKS IRSA). No keys in the app.
- **Postgres** — metadata (`s3_key`, `filename`, `content_type`, `size_bytes`, `uploaded_at`).
- **Flask** — `/` lists images via presigned GET URLs; `/upload` accepts multipart form posts.

## Setup

1. Install deps:
   ```
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in `S3_BUCKET`, `S3_REGION`, and the Postgres connection fields.
3. Make sure the host's IAM role has `s3:PutObject`, `s3:GetObject`, and `s3:DeleteObject` on `arn:aws:s3:::<bucket>/*`.
4. Run:
   ```
   python app.py
   ```
   The app creates the `images` table on first start (`schema.sql`) and serves on `http://0.0.0.0:5000`.

## Notes

- Gallery uses presigned URLs (1h expiry) so the bucket can stay private.
- If the DB insert fails after the S3 upload succeeds, the orphan S3 object is deleted to keep state consistent.
- Max upload size is `MAX_UPLOAD_MB` (default 10 MB).
