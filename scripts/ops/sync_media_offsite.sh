#!/usr/bin/env bash
# Copy locally stored shop photos (JDS_MEDIA_STORAGE=local) to an off-site S3-compatible bucket.
# Not needed when JDS_MEDIA_STORAGE=supabase (photos already live off the app server).
# Required env: JDS_LOCAL_MEDIA_ROOT, MEDIA_RCLONE_REMOTE (e.g. "offsite:jds-media")
# rclone remote credentials come from rclone's own config/env (RCLONE_CONFIG_OFFSITE_*), never this script.
set -euo pipefail
: "${JDS_LOCAL_MEDIA_ROOT:?JDS_LOCAL_MEDIA_ROOT is required}"
: "${MEDIA_RCLONE_REMOTE:?MEDIA_RCLONE_REMOTE is required}"
# copy (not sync) so a local deletion or disk loss never deletes the off-site copy
rclone copy "$JDS_LOCAL_MEDIA_ROOT" "$MEDIA_RCLONE_REMOTE" --quiet --checksum
echo "media copied off-site"
