#!/usr/bin/env bash
# Run from project root: bash start_frontend.sh
set -e
cd "$(dirname "$0")/frontend"
echo "Starting Next.js on http://localhost:3000"
npm run dev
