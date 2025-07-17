#!/bin/bash

# 保险模板
source ~/.env_common
slug=$(slugify "$(basename "$PWD")")
PROJECT_DIR=$(get_project_data "$slug")

# 项目配置
PROJECT_NAME="auto_match_pull"
SCRIPT_DIR="$HOME/Developer/Code/Scripts/desktop/auto-match-pull"
PYTHON_BIN="$HOME/Developer/Python/miniconda/envs/System/bin/python"

# 确保项目数据目录存在
mkdir -p "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/logs"

# 创建用户配置文件
cat > "$PROJECT_DIR/scan_folders.json" << 'EOF'
{
  "search_paths": [
    "/Users/niceday/Developer",
    "/Users/niceday/Documents/Projects",
    "/Users/niceday/Developer/Code/Scripts"
  ],
  "exclude_patterns": [
    "*.git*",
    "node_modules",
    "__pycache__",
    "*.pyc",
    ".venv",
    "venv",
    ".DS_Store"
  ],
  "repo_manager_config": {
    "data_dir": "/Users/niceday/Developer/Code/Data/srv/repo_management"
  }
}
EOF

# 停止现有服务
launchctl unload "$HOME/Library/LaunchAgents/com.auto-match-pull.plist" 2>/dev/null || true

# 创建 LaunchAgent plist
cat > "$HOME/Library/LaunchAgents/com.auto-match-pull.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.auto-match-pull</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$SCRIPT_DIR/src/auto_match_pull/main.py</string>
        <string>autostart</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/launchd.out</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/launchd.err</string>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
        <key>PROJECT_DATA_DIR</key>
        <string>$PROJECT_DIR</string>
    </dict>
</dict>
</plist>
EOF

# 加载服务
launchctl load "$HOME/Library/LaunchAgents/com.auto-match-pull.plist"

echo "✅ auto_match_pull 部署完成"
echo "📁 数据目录: $PROJECT_DIR"
echo "⚙️ 配置文件: $PROJECT_DIR/scan_folders.json"
echo "📋 日志目录: $PROJECT_DIR/logs"