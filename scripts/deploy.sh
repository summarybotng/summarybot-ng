#!/bin/bash
# Deploy script that sets build info

set -e

# Get git info
GIT_SHA=$(git rev-parse --short HEAD)
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Deploying build: $GIT_SHA ($BUILD_DATE)"

# Deploy with build args
flyctl deploy --ha=false \
  --build-arg "BUILD_NUMBER=$GIT_SHA" \
  --build-arg "BUILD_DATE=$BUILD_DATE" \
  "$@"
