# Auto Match Pull System

## 功能实现原理

```mermaid
graph TD
    A[deploy.sh] --> B[生成scan_folders.json]
    A --> C[创建LaunchAgent]
    A --> D[设置PROJECT_DATA_DIR]
    
    E[main.py] --> F[CLI加载]
    F --> G[读取scan_folders.json]
    F --> H[设置数据目录]
    
    I[文件夹匹配] --> J[扫描本地目录]
    J --> K[扫描Git仓库]
    K --> L[相似度计算]
    L --> M[建立映射关系]
    
    N[自动同步] --> O[定时检查]
    O --> P[执行Git Pull]
    P --> Q[状态更新]
    
    R[调度服务] --> S[并发控制]
    S --> T[错误重试]
    T --> U[日志记录]
    
    subgraph "数据目录结构"
        V[~/Developer/Code/Data/srv/auto_match_pull/]
        V --> W[config.json]
        V --> X[scan_folders.json]
        V --> Y[logs/]
        V --> Z[mappings.db]
    end
```

## 文件引用关系

```mermaid
graph LR
    A[deploy.sh] --> B[src/auto_match_pull/cli.py]
    B --> C[src/auto_match_pull/core/matcher.py]
    C --> D[src/auto_match_pull/core/database.py]
    D --> E[src/auto_match_pull/services/git_service.py]
    E --> F[src/auto_match_pull/services/scheduler.py]
    
    G[scan_folders.json] --> B
    H[config.json] --> B
    I[LaunchAgent plist] --> J[main.py]
    J --> K[autostart]
    K --> F
    
    L[PROJECT_DATA_DIR] --> B
    L --> D
    L --> M[logs/]
    L --> N[mappings.db]
```

## 部署说明

1. **运行部署脚本**：
   ```bash
   ./deploy.sh
   ```

2. **配置文件**：
   - `scan_folders.json`: 定义搜索路径和排除规则
   - `config.json`: 项目配置和调度设置

3. **数据目录**：
   - 位置：`~/Developer/Code/Data/srv/auto_match_pull/`
   - 包含：配置文件、映射数据库、日志

4. **服务管理**：
   - LaunchAgent 自动启动
   - 定时执行 Git Pull
   - 智能映射和冲突处理

## 新架构特性

- ✅ 使用 PROJECT_DATA_DIR 环境变量
- ✅ 符合新的文件结构规范
- ✅ 支持用户自定义扫描目录
- ✅ 规范化数据目录命名
- ✅ 统一的部署脚本模板