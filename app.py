import os
import uuid
from pathlib import Path

import boto3
import psycopg2
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename

load_dotenv()

S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.environ.get("S3_REGION", "us-east-1")

DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ["DB_NAME"],
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
}

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 10))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
PRESIGN_EXPIRES = 3600

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# boto3 picks up credentials from the IAM role automatically (instance metadata,
# ECS task role, or EKS IRSA) — no keys passed here on purpose.
s3 = boto3.client("s3", region_name=S3_REGION)


def get_db():
    return psycopg2.connect(**DB_CONFIG)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def init_db():
    schema = Path(__file__).parent.joinpath("schema.sql").read_text()
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(schema)


@app.route("/", methods=["GET"])
def index():
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, s3_key, filename, content_type, size_bytes, uploaded_at "
            "FROM images ORDER BY uploaded_at DESC LIMIT 100"
        )
        rows = cur.fetchall()

    images = []
    for row in rows:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": row["s3_key"]},
            ExpiresIn=PRESIGN_EXPIRES,
        )
        images.append({**row, "url": url})

    return render_template("index.html", images=images, max_mb=MAX_UPLOAD_MB)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("image")
    if not file or file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash(f"File type not allowed. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}.", "error")
        return redirect(url_for("index"))

    safe_name = secure_filename(file.filename)
    ext = safe_name.rsplit(".", 1)[1].lower()
    s3_key = f"uploads/{uuid.uuid4().hex}.{ext}"
    content_type = file.mimetype or "application/octet-stream"

    file.stream.seek(0, os.SEEK_END)
    size_bytes = file.stream.tell()
    file.stream.seek(0)

    try:
        s3.upload_fileobj(
            file.stream,
            S3_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": content_type},
        )
    except ClientError as e:
        flash(f"S3 upload failed: {e}", "error")
        return redirect(url_for("index"))

    try:
        with get_db() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO images (s3_key, filename, content_type, size_bytes) "
                "VALUES (%s, %s, %s, %s)",
                (s3_key, safe_name, content_type, size_bytes),
            )
    except Exception as e:
        # Roll back the S3 object so we don't leave orphans.
        s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
        flash(f"DB insert failed: {e}", "error")
        return redirect(url_for("index"))

    flash(f"Uploaded {safe_name}.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
