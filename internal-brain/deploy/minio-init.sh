#!/bin/sh
# Creates the checkpoint bucket with Object Lock in COMPLIANCE mode, a put-only writer for
# the app and a read-only verifier. Safe to re-run. Runs once before the app starts.
set -eu
for i in $(seq 1 30); do
  mc alias set store "${MINIO_URL:-http://minio:9000}" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1 && break
  sleep 1
done
mc mb --ignore-existing --with-lock "store/$BUCKET"
mc retention set --default COMPLIANCE "${RETENTION_DAYS}d" "store/$BUCKET"

cat > /tmp/writer.json <<JSON
{"Version": "2012-10-17", "Statement": [
  {"Effect": "Allow", "Action": ["s3:PutObject"], "Resource": ["arn:aws:s3:::$BUCKET/*"]}]}
JSON
cat > /tmp/reader.json <<JSON
{"Version": "2012-10-17", "Statement": [
  {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:ListBucketVersions", "s3:GetBucketObjectLockConfiguration"],
   "Resource": ["arn:aws:s3:::$BUCKET"]},
  {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion"], "Resource": ["arn:aws:s3:::$BUCKET/*"]}]}
JSON
mc admin policy create store checkpoint-writer /tmp/writer.json
mc admin policy create store checkpoint-reader /tmp/reader.json
mc admin user add store "$WRITER_KEY" "$WRITER_SECRET"
mc admin user add store "$READER_KEY" "$READER_SECRET"
mc admin policy attach store checkpoint-writer --user "$WRITER_KEY" || true
mc admin policy attach store checkpoint-reader --user "$READER_KEY" || true
mc retention info --default "store/$BUCKET"
echo "checkpoint store ready"
