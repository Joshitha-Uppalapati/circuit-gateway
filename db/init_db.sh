#!/bin/bash
set -e

psql $DATABASE_URL -f db/schema.sql