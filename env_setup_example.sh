#!/bin/bash

# Auto Match Pull - Environment Setup Example
# This script demonstrates how to use the env_common framework

# Source the common environment variables
source ~/.env_common

# Get project data directory using the helper function
slug=$(slugify "$(basename "$PWD")")
PROJECT_DIR=$(get_project_data "$slug")

# Export PROJECT_DATA_DIR for auto-match-pull to use
export PROJECT_DATA_DIR="$PROJECT_DIR"

echo "Project: $slug"
echo "Data directory: $PROJECT_DIR"
echo "PROJECT_DATA_DIR set to: $PROJECT_DATA_DIR"

# Optional: Set other auto-match-pull environment variables
export AUTO_MATCH_PULL_SEARCH_PATHS="$HOME/Developer,$HOME/Documents,$HOME/Projects"
export AUTO_MATCH_PULL_INTERVAL="30"

echo "Environment setup complete!"
echo ""
echo "You can now run auto-match-pull commands:"
echo "  auto-match-pull scan --save"
echo "  auto-match-pull list"
echo "  auto-match-pull daemon"