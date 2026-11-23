# Docker 开发环境

本配置用于 `E:\oshino` 的 XM 分支，运行第一至第六部分。前端使用 Vite，后端使用 Uvicorn 开发重载；案例和知识检索使用 Windows Ollama 本地向量模型，第六部分等待用户验收。

## 本地模型

第五部分使用 Windows 上的 Ollama 和 `qwen3-embedding:0.6b`。先打开 Ollama；Docker 内通过 `host.docker.internal:11434` 访问它。模型配置保存在 `backend/.env.retrieval`，只读挂载到后端，Milvus 文件持久化到 `data/milvus`。

首次加载超时、预热命令及重建步骤见[第五部分实施与验收](../03-检查记录/2026-10-31-第五部分实施与验收.md)。重建完成后不需要每次启动都重新生成向量；新增或修改有效案例时再重建。

## 日常启动

打开 Windows 的 Docker Desktop，启用 Settings → Resources → WSL Integration → Ubuntu。在 WSL 执行：

```bash
cd /mnt/e/oshino
docker compose --env-file .env.docker up -d --build --wait
```

- 登录页：http://127.0.0.1:18734/login
- 基础管理：http://127.0.0.1:18734/admin
- 接口文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

Docker Desktop 的 Containers 页面中，项目名为 `oshino-dev`，包含 frontend、backend、db 三个服务。数据库不发布宿主机端口；前端和后端端口只绑定本机回环地址。

## 密码与账号

数据库密码和 JWT 密钥保存在项目根目录 `.env.docker`；本机本次自动初始化的网页登录账号保存在 `.local/docker-admin.json`。这些文件已由 Git 忽略，不要复制到公开文档或提交。

容器数据库使用独立的命名数据卷 `oshino-dev_postgres_data`，不会自动读取原 WSL 数据库的账号和数据。容器数据库管理员首次初始化后持续保留。

在新电脑首次准备配置时，先在项目根目录生成密码文件：

```bash
python3 - <<'PY'
from pathlib import Path
from secrets import token_urlsafe

with Path('.env.docker').open('x', encoding='utf-8') as file:
    file.write(f'POSTGRES_PASSWORD={token_urlsafe(32)}\n')
    file.write(f'JWT_SECRET={token_urlsafe(48)}\n')
PY
```

文件存在时不重复生成。启动服务后，在新数据库创建管理员：

```bash
docker compose --env-file .env.docker exec backend \
  python -m app.seed --username admin --display-name 管理员
```

按提示设置网页登录密码并自行保管。已有管理员不重复初始化，不用旧 WSL 数据库的密码代替网页登录密码。

## 修改代码

`backend/app` 和前端的 src、public、index.html、vite.config.ts 挂载到容器。修改已启用的源码会触发开发服务器刷新。

修改 Python/Node 依赖或 Dockerfile 后，重新运行 `up -d --build --wait`。容器使用自己的依赖，不需要激活宿主机虚拟环境，也不复用宿主机 node_modules。

前端代理在容器中使用 `http://backend:8000`，直接在 WSL 启动时沿用 `http://127.0.0.1:8000`。

## 迁移与预建空文件

当前 backend/Dockerfile 复制基础配置、工单、CSV 来源编号、知识文档四条迁移，最新版本为 `06_knowledge`。启动时先迁移，成功后才启动 API；迁移失败会准确退出。后续空迁移保留为 `.py.pending`，不会被 Alembic 误读；完成后再改回 `.py` 并加入 Dockerfile。

预建的其他空迁移文件保留在宿主机，不参与当前镜像。后续阶段按已完成的迁移逐项添加。不要把空文件或缺少 revision 的文件加入可执行迁移。

第三部分已经加入以下配置，无需重复添加：

```dockerfile
COPY migrations/versions/1368452a803a_工单与处理记录.py ./migrations/versions/
```

然后运行 `up -d --build --wait`，后端会先升级数据库，再启动 API。

本配置运行 Vite 开发服务器，不执行生产构建。未完成的空 Vue 文件明确列入 tsconfig.json 的 exclude，完成对应阶段时移除排除项。当前已启用页面参与类型检查与生产构建，不能把开发页面可打开当成全部构建通过。

## 常用命令

```bash
# 检查配置，不打印密码和密钥
docker compose --env-file .env.docker config --quiet

# 查看状态
docker compose --env-file .env.docker ps

# 查看日志
docker compose --env-file .env.docker logs -f

# 停止并移除容器，保留命名数据卷
docker compose --env-file .env.docker down
```

数据库密码在数据卷首次初始化时生效。以后更换密码需要同步修改数据库用户密码，不能仅改 `.env.docker` 就认为旧数据库密码已更换。

## 本机验证记录

2026-10-25 在 Windows Docker Desktop 与 WSL Ubuntu 验证：

| 项目 | 实际结果 |
|---|---|
| Compose 配置 | `config --quiet` 通过 |
| 开发镜像 | Python 后端与 Node 前端镜像构建成功 |
| WSL 一键启动 | `up -d --build --wait` 通过，三个服务均为 healthy |
| HTTP 链路 | 后端健康接口、前端代理健康接口、登录页入口与 Vite 入口正常 |
| 账号与权限 | 通过前端代理登录管理员，读取当前账号、用户、产品、模块、分类；未登录访问配置返回 401 |
| 数据库迁移 | 版本为 `321917cab056 (head)` |
| 数据持久化 | 执行 down 后重新 up，原管理员仍可登录，保护接口仍可读取 |
| 浏览器 | 已确认登录页面的表单正常渲染；未把 API 检查描述成全部页面交互验收 |

首次构建遇到 Docker Hub 认证直连超时，先通过 Docker 引擎直接拉取基础镜像后完成构建，之后已复验 WSL 启动命令。本机没有改用第三方镜像源或修改系统代理配置。

如果以后清理基础镜像或更换版本时出现同类认证超时，可先确认 Docker Desktop 的网络代理可用，再拉取对应镜像：

```bash
docker pull postgres:17
docker pull python:3.12-slim
docker pull node:24-bookworm-slim
```

上述 2026-10-25 记录当时没有运行生产前端构建，预建的 108 个文件当时仍为空。第三部分的最新实施与验证见[2026-10-31 记录](../03-检查记录/2026-10-31-第三部分实施与验收.md)。

参考：[Docker WSL 集成](https://docs.docker.com/desktop/features/wsl/)、[Compose 启动顺序](https://docs.docker.com/compose/how-tos/startup-order/)。

## 第七至九部分更新（2026-10-31）

当前迁移头为 `09_resolution_time`。执行根目录的一键启动命令会创建建议历史表并增加真实解决时间，保留已有业务数据。

聊天配置独立保存在 `backend/.env.chat`，Compose 以只读文件挂载到后端。参考 `.env.chat.example` 填入 CHAT_BASE_URL、CHAT_API_KEY、CHAT_MODEL；没有配置时只有生成建议功能报配置错误，普通工单、知识检索和看板仍可使用。填写后执行 `docker compose --env-file .env.docker restart backend`。

原 `.env.retrieval` 继续连接本地向量模型，无需为了聊天 API 更改 Embedding 模型或重建索引。详情见[第七部分教程](../01-教程/06-08-知识库与AI建议/07-AI处理建议.md)。
