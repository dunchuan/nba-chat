# 使用 GitHub Actions 部署 NBA Chat 到 Vultr

本文说明如何通过 GitHub Actions 将 `main` 分支按需部署到 Vultr 服务器。

当前部署方式：

- 手动触发部署，不会在每次 `push` 后自动执行。
- GitHub Actions Runner 通过 SSH 登录 Vultr。
- 服务器拉取 `main` 分支并重新构建 Docker 容器。
- 服务器上的 `.env` 和 SQLite 数据不会提交到 Git，也不会被正常部署覆盖。

## 1. 部署流程

```text
GitHub Actions 手动触发
        ↓
读取 production Environment 中的配置
        ↓
使用 SSH 私钥连接 Vultr
        ↓
进入 /opt/nba-chat
        ↓
拉取 main 分支
        ↓
重新构建并启动 Docker Compose
        ↓
请求 /api/health 验证部署结果
```

## 2. 准备 Vultr 服务器

服务器需要提前安装 Git、Docker、Docker Compose 和 curl：

```bash
apt update
apt install -y git curl ca-certificates docker.io docker-compose
systemctl enable --now docker
```

检查安装结果：

```bash
git --version
docker --version
docker compose version
systemctl is-active docker
```

首次部署代码：

```bash
git clone https://github.com/dunchuan/nba-chat.git /opt/nba-chat
cd /opt/nba-chat
```

在服务器创建生产环境配置：

```bash
cd /opt/nba-chat
nano .env
chmod 600 .env
```

`.env` 只保存在服务器，不要提交到 GitHub。

账号和注册功能需要以下配置（不填写时也使用这些默认值）：

```env
AUTH_REQUIRED=true
REGISTRATION_ENABLED=true
SESSION_MAX_AGE=604800
SESSION_COOKIE_SECURE=auto
SQLITE_PATH=./data/nba_chat.sqlite3
```

如果需要临时关闭公开注册，将 `REGISTRATION_ENABLED` 改为 `false` 并重新启动容器。

首次启动服务：

```bash
cd /opt/nba-chat
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/api/health
```

## 3. 准备 SSH 密钥

可以使用已有的部署密钥，也可以在 Windows PowerShell 中创建专用密钥：

```powershell
ssh-keygen -t ed25519 -C "github-actions-nba-chat" -f "$env:USERPROFILE\.ssh\vultr_nba_chat"
```

生成两个文件：

- `vultr_nba_chat`：私钥，只交给 GitHub Actions。
- `vultr_nba_chat.pub`：公钥，写入 Vultr 服务器。

查看公钥：

```powershell
Get-Content "$env:USERPROFILE\.ssh\vultr_nba_chat.pub"
```

将公钥整行添加到服务器登录用户的 `authorized_keys`。如果使用 `root`：

```bash
mkdir -p /root/.ssh
nano /root/.ssh/authorized_keys
chmod 700 /root/.ssh
chmod 600 /root/.ssh/authorized_keys
```

在本地验证免密登录：

```powershell
ssh -i "$env:USERPROFILE\.ssh\vultr_nba_chat" root@45.76.199.150
```

## 4. 获取 Vultr 服务器主机公钥

GitHub Actions 使用严格主机校验，必须保存 Vultr 服务器的 ED25519 主机公钥。

在 Vultr Web Console 或已经登录的服务器中执行：

```bash
printf '45.76.199.150 '; cut -d' ' -f1-2 /etc/ssh/ssh_host_ed25519_key.pub
```

输出类似：

```text
45.76.199.150 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
```

复制完整的一行。不要复制 SHA256 指纹、私钥、注释或报错信息。

## 5. 创建 GitHub Environment

进入当前 GitHub 仓库：

```text
Settings → Environments → New environment
```

Environment 名称填写：

```text
production
```

Environment 属于当前仓库，因此其他仓库也可以各自拥有名为 `production` 的 Environment，彼此不会混用。

## 6. 配置 Environment secrets

进入：

```text
Settings → Environments → production → Environment secrets
```

添加以下 Secrets：

### `VULTR_SSH_PRIVATE_KEY`

填写本地私钥文件的完整内容：

```powershell
Get-Content "$env:USERPROFILE\.ssh\vultr_nba_chat" -Raw
```

内容应包含：

```text
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

不要填写 `.pub` 公钥。

### `VULTR_KNOWN_HOSTS`

填写第 4 步获得的完整主机公钥，例如：

```text
45.76.199.150 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA...
```

## 7. 配置 Environment variables

进入：

```text
Settings → Environments → production → Environment variables
```

添加：

| 变量名 | 示例值 | 含义 |
|---|---|---|
| `VULTR_HOST` | `45.76.199.150` | Vultr 服务器公网 IP |
| `VULTR_USER` | `root` | SSH 登录用户名 |

Secrets 用于保存敏感内容；Variables 用于保存服务器地址、用户名等普通配置。

## 8. 添加 Workflow

文件位置：

```text
.github/workflows/deploy-production.yml
```

当前项目使用以下配置：

```yaml
name: Deploy Production

on:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: nba-chat-production
  cancel-in-progress: false

jobs:
  deploy:
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Configure SSH
        env:
          SSH_PRIVATE_KEY: ${{ secrets.VULTR_SSH_PRIVATE_KEY }}
          SSH_KNOWN_HOSTS: ${{ secrets.VULTR_KNOWN_HOSTS }}
        run: |
          test -n "$SSH_PRIVATE_KEY" || {
            echo "VULTR_SSH_PRIVATE_KEY is not configured"
            exit 1
          }

          test -n "$SSH_KNOWN_HOSTS" || {
            echo "VULTR_KNOWN_HOSTS is not configured"
            exit 1
          }

          install -m 700 -d ~/.ssh
          printf '%s\n' "$SSH_PRIVATE_KEY" | tr -d '\r' > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          printf '%s\n' "$SSH_KNOWN_HOSTS" | tr -d '\r' > ~/.ssh/known_hosts
          chmod 600 ~/.ssh/known_hosts

      - name: Deploy to Vultr
        env:
          DEPLOY_HOST: ${{ vars.VULTR_HOST }}
          DEPLOY_USER: ${{ vars.VULTR_USER }}
        run: |
          : "${DEPLOY_HOST:?VULTR_HOST is not configured}"
          : "${DEPLOY_USER:?VULTR_USER is not configured}"

          ssh \
            -o BatchMode=yes \
            -o IdentitiesOnly=yes \
            -o StrictHostKeyChecking=yes \
            -i ~/.ssh/id_ed25519 \
            "$DEPLOY_USER@$DEPLOY_HOST" \
            'bash -se' <<'REMOTE'
          set -Eeuo pipefail

          cd /opt/nba-chat
          git checkout main
          git pull --ff-only origin main
          docker compose up -d --build --remove-orphans

          for attempt in {1..30}; do
            if curl -fsS http://127.0.0.1:8000/api/health; then
              echo
              echo "Deployment succeeded."
              exit 0
            fi
            sleep 2
          done

          docker compose ps
          docker compose logs --tail=100 nba-chat
          exit 1
          REMOTE
```

说明：

- `runs-on: ubuntu-latest` 是 GitHub 临时 Runner 的系统，不是 Vultr 的系统。
- Vultr 使用 Debian 不受影响，因为真正的部署命令通过 SSH 在 Vultr 上执行。
- `workflow_dispatch` 表示只允许手动触发。
- `environment: production` 让 Job 可以读取 `production` 下的 Secrets 和 Variables。
- `concurrency` 防止两个生产部署同时执行。
- 健康检查最多等待约 60 秒。

## 9. 提交 Workflow

在本地执行：

```powershell
git add .github/workflows/deploy-production.yml
git commit -m "Add production deployment workflow"
git push origin main
```

如果 Workflow 是直接在 GitHub 网页创建的，应先确保本地没有同名未提交文件，再执行 `git pull`，避免覆盖或冲突。

## 10. 手动触发部署

进入 GitHub 仓库：

```text
Actions → Deploy Production → Run workflow
```

选择 `main` 分支，然后点击绿色的 `Run workflow`。

部署成功时，日志会显示：

```text
Deployment succeeded.
```

## 11. 部署后验证

检查健康接口：

```text
https://nbachat.top/api/health
```

也可以登录服务器检查：

```bash
cd /opt/nba-chat
docker compose ps
docker compose logs --tail=100 nba-chat
curl http://127.0.0.1:8000/api/health
```

## 12. 数据是否会被覆盖

当前 `docker-compose.yml` 使用：

```yaml
volumes:
  - ./data:/app/data
```

因此 SQLite 文件保存在宿主机：

```text
/opt/nba-chat/data/nba_chat.sqlite3
```

以下正常部署操作不会删除数据库：

```bash
git pull --ff-only origin main
docker compose up -d --build --remove-orphans
```

不要在部署脚本中加入以下危险操作：

```bash
rm -rf /opt/nba-chat
rm -rf /opt/nba-chat/data
git clean -fdx
docker compose down -v
```

建议在正式使用前增加数据库备份。最简单的手动备份方式：

```bash
cp /opt/nba-chat/data/nba_chat.sqlite3 \
  /opt/nba-chat/data/nba_chat.sqlite3.backup
```

## 13. 常见错误

### `VULTR_SSH_PRIVATE_KEY is not configured`

原因：Workflow 没有关联正确的 Environment，或 Secret 不在 `production` 中。

检查：

```yaml
environment: production
```

并确认 Secret 名称完全是：

```text
VULTR_SSH_PRIVATE_KEY
```

### `Host key verification failed`

原因：`VULTR_KNOWN_HOSTS` 缺失或内容错误。

重新在服务器执行：

```bash
printf '45.76.199.150 '; cut -d' ' -f1-2 /etc/ssh/ssh_host_ed25519_key.pub
```

把完整输出更新到 `production` 的 `VULTR_KNOWN_HOSTS`。

### `choose_kex: unsupported KEX method`

这是旧版 Windows `ssh-keyscan` 与服务器 OpenSSH 版本协商失败。不要继续使用该次扫描结果，直接从服务器读取 `/etc/ssh/ssh_host_ed25519_key.pub`。

### SSH 输出 usage 并返回 `exit code 255`

通常表示 `VULTR_HOST` 或 `VULTR_USER` 为空。确认它们位于：

```text
Settings → Environments → production → Environment variables
```

### 健康检查失败

登录服务器查看容器状态和日志：

```bash
cd /opt/nba-chat
docker compose ps
docker compose logs --tail=200 nba-chat
```
