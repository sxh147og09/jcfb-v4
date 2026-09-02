# JCFB V4 本地存储约定

## 目的

JCFB V4 的本地运行时目录统一放在仓库所在的项目盘：

`F:\Projects\jcfb-v4\.runtime\`

该目录用于临时文件、缓存、构建辅助文件、日志、依赖缓存、Playwright 浏览器文件、Python 字节码缓存，以及一次性的本地 PostgreSQL 数据。它不包含正式源码、Frozen Prediction、历史预测或生产数据库。

`.runtime/` 已加入 `.gitignore`，不会进入 Git。

## 启用项目环境

在 PowerShell 中进入仓库后，使用点号调用脚本，使环境变量保留在当前窗口，并传递给从该窗口启动的子进程：

```powershell
Set-Location F:\Projects\jcfb-v4
. .\scripts\activate_jcfb_v4_runtime.ps1
```

如果本机执行策略阻止加载仓库脚本，只对当前 PowerShell 窗口临时放行，不要修改全局执行策略：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
. .\scripts\activate_jcfb_v4_runtime.ps1
```

验证关键路径：

```powershell
$env:TEMP
$env:TMP
$env:PIP_CACHE_DIR
$env:NPM_CONFIG_CACHE
$env:PNPM_STORE_DIR
$env:YARN_CACHE_FOLDER
$env:PLAYWRIGHT_BROWSERS_PATH
$env:PYTHONPYCACHEPREFIX
```

这些值应全部指向 `F:\Projects\jcfb-v4\.runtime\`。脚本只修改当前 PowerShell 进程及其子进程，不修改 Windows 全局 `TEMP/TMP`，也不影响其他项目。

## 依赖与构建

- Node 的 `node_modules`、`.next`、`.turbo`、Vite 缓存和常规构建输出应留在仓库所在的 F 盘；相关目录已加入忽略规则。
- npm、pnpm、yarn、Corepack、pip、Playwright 的缓存路径由激活脚本指向 `.runtime`。
- Python 的 `PYTHONPYCACHEPREFIX` 指向 `.runtime\pycache`，避免新生成的 `__pycache__` 回到源码目录或 C 盘。
- 如需创建 Python 虚拟环境，应在激活项目环境后执行：

  ```powershell
  python -m venv $env:JCFB_V4_PYTHON_VENV
  ```

  本次迁移没有自动安装依赖，也没有创建虚拟环境，因为仓库当前没有 `package.json` 或依赖清单，盲目安装会改变项目状态。

## 一次性 PostgreSQL 运行时

`docker-compose.runtime-validation.yml` 已从 Docker 命名卷改为仓库相对路径绑定：

`F:\Projects\jcfb-v4\.runtime\postgres\`

因此以后从该 compose 文件启动的临时 PostgreSQL 数据落在 F 盘。现有 Docker 命名卷 `jcfb-v4-disposable-pg-data` 不会被自动删除；它可能仍占用 Docker Desktop 的默认存储位置，只有确认不再需要后才应单独处理。

运行入口仍是：

```powershell
.\scripts\v4_disposable_runtime.ps1 -Action start
.\scripts\v4_disposable_runtime.ps1 -Action readiness
```

该运行时仍是本地、一次性验证数据库，不会自动应用正式迁移，也不会连接生产数据库。

## 边界

此配置保证从已激活的 JCFB PowerShell 会话启动的进程使用 F 盘项目缓存和临时目录。它不会迁移 Docker Desktop 的全局镜像层，也不会改变其他应用的全局缓存；这两类内容属于系统级配置，需单独审计和确认。
