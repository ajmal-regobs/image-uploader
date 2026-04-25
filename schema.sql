CREATE TABLE IF NOT EXISTS images (
    id           BIGSERIAL PRIMARY KEY,
    s3_key       TEXT NOT NULL UNIQUE,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes   BIGINT NOT NULL,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS images_uploaded_at_idx ON images (uploaded_at DESC);
