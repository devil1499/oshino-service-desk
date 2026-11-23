# GitHub Actions 与 Ubuntu 上线

推送 GitHub `main` 后，Actions 运行前端测试、构建以及后端测试（含临时 PostgreSQL）。测试通过后构建生产镜像、使用独立数据库启动服务，并检查首页和 API。验证通过的镜像以提交 SHA 标记推送至 GHCR。服务器部署使用镜像摘要。

## 首次准备 Ubuntu

适用环境为 x86-64 Ubuntu，安装 Docker Engine 和 Compose 插件，使用有 Docker 权限的专用部署账号。Docker 权限等同于主机高权限，请只给受信任账号。把部署专用 SSH 公钥放进该账号的 `authorized_keys`，并在服务器控制台核对 SSH 主机公钥。SSH 使用默认 22 端口和 DNS 名称或 IPv4 地址。

在部署账号的家目录创建 `~/oshino-service-desk/.env.server`，权限设为 600。在服务器上用 `openssl rand -hex 32` 分别生成两个值：

```dotenv
POSTGRES_PASSWORD=在服务器替换为十六进制密码
JWT_SECRET=在服务器替换为另一段随机值
WEB_PORT=18734
```

对外访问需要宿主反向代理为域名配置 HTTPS，再转发到 `127.0.0.1:18734`。数据库和后端只在 Compose 网络中通信。PostgreSQL、向量索引、AI 配置和 OCR 模型使用持久卷。模型与 SMTP 可通过 `.env.server` 配置，聊天模型也可在应用管理页面配置。Ubuntu 上的向量模型地址需要能从容器访问。新数据库的管理员使用 `python -m app.seed --username admin --display-name 管理员` 在 backend 容器内交互创建。

## GitHub 仓库配置

在 Settings → Environments 创建 `production`，限制到 `main`。添加以下环境 Secrets：

| 名称 | 内容 |
| --- | --- |
| DEPLOY_HOST | SSH 主机 DNS 名或 IPv4 |
| DEPLOY_USER | Ubuntu 部署用户名 |
| DEPLOY_SSH_KEY | 部署专用 SSH 私钥 |
| DEPLOY_KNOWN_HOSTS | 从服务器控制台核验过的 known_hosts 完整记录 |

在 Settings → Secrets and variables → Actions → Variables 设置仓库变量 `DEPLOY_ENABLED=true`。如已对外开放，可同时设置仓库变量 `DEPLOY_SITE_URL=https://你的域名`，用于检查公网首页和 API。配置完成后，在 Actions 选择 `Test, publish and deploy`，手动运行 `main` 或推送新提交。

GHCR 使用 GitHub Actions 的临时令牌发布和拉取镜像。每次部署保存在 `~/oshino-service-desk/releases/<commit>`，成功后 `current` 指向对应目录。首次启动执行数据库迁移。更新前保留数据库备份，涉及数据库结构变化时需确认迁移兼容性，再决定是否回退镜像。

在 Ubuntu 查看已通过检查的发布：

```bash
cd ~/oshino-service-desk
export SERVER_ENV_FILE="$PWD/.env.server"
docker compose --env-file "$SERVER_ENV_FILE" --env-file current/.images.env -f current/compose.yaml ps
```
