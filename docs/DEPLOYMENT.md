# Cairn 生产部署手册（阿里云）

> 目标读者：把 Cairn 从本地 Windows 开发环境发布到阿里云服务器（ECS 或轻量应用服务器）。
> 按章节顺序执行即可完成首次上线；第 8 章之后是日常运维与故障排查。
> 配套部署文件：`Dockerfile`、`docker-compose.prod.yml`、`apps/web/Dockerfile`、`apps/web/nginx.conf`、`.env.production.example`、`scripts/deploy.sh`。

## 目录

1. [部署架构](#1-部署架构)
2. [前置准备：买什么、怎么选](#2-前置准备)
3. [服务器初始化](#3-服务器初始化)
4. [获取代码](#4-获取代码)
5. [生产配置](#5-生产配置)
6. [首次部署与验证](#6-首次部署与验证)
7. [域名、备案与 HTTPS](#7-域名备案与-https)
8. [日常运维：发布、回滚、日志](#8-日常运维)
9. [备份与恢复](#9-备份与恢复)
10. [监控与告警](#10-监控与告警)
11. [安全清单](#11-安全清单)
12. [常见问题 FAQ](#12-常见问题-faq)
13. [与本地开发环境的差异对照](#13-与本地开发环境的差异对照)

---

## 1. 部署架构

```
浏览器
   │  HTTP(80) / HTTPS(443)
   ▼
web 容器（Nginx，唯一对外入口）
   ├── /            → Vue 静态产物（apps/web 构建出的 dist）
   ├── /assets/     → 静态资源长缓存
   └── /api/*       → 反向代理到 api 容器（SSE 已关闭缓冲）
                        │
                        ▼
                     api 容器（FastAPI + uvicorn :8000）
                        ├── postgres 容器（pgvector/pg16，数据卷 pgdata，不暴露公网）
                        ├── redis 容器（AOF 持久化，数据卷 redisdata，不暴露公网）
                        └── 出网调用 DeepSeek / 火山方舟 / 腾讯混元 API
```

设计要点：

- **只有 web 容器占用 80/443 端口**；PostgreSQL 和 Redis 不映射宿主端口，公网完全不可达。
- 前端 `client.ts` 使用相对路径 `/api/v1`，同域反代后不存在跨域，`CORS_ORIGINS` 只需填自己的站点。
- Nginx 对 `/api/` 关闭了缓冲（`proxy_buffering off`），这是 SSE 进度和流式输出能逐字显示的前提。
- 所有服务都在 `docker-compose.prod.yml` 中编排，`restart: unless-stopped` 保证开机自启与崩溃拉起。

## 2. 前置准备

### 2.1 服务器选型

| 项 | 推荐 | 说明 |
|---|---|---|
| 产品 | **轻量应用服务器**（首选） | 便宜、有控制台面板、防火墙配置简单；个人项目够用。想要更细的安全组/网络控制选 ECS |
| 规格 | **2核4G** 宽裕，**2核2G** 可用 | pgvector HNSW 索引 + LangGraph 多 Agent 应用有内存开销；2G 需加 swap，见下方说明 |
| 系统 | **Ubuntu 22.04 / 24.04 LTS** | 本手册命令基于 Ubuntu |
| 地域 | 大陆（华东1/华北2等） | DeepSeek/火山/腾讯 API 都是国内服务，出网无障碍 |
| 带宽 | 按流量 3~5M 峰值 或 固定带宽 | 前端静态资源 + API 报文都很小，模型调用是出网方向 |
| 价格 | 约 ¥50~120/月 | 以控制台实时价格与活动为准 |

> 2核2G 也能跑（自用足够）：实测空闲时 PostgreSQL 约 50MB、Redis 约 10MB、后端约 80MB。**2G 机器必须先加 swap（3.4 节）再构建镜像**——内存峰值出现在构建阶段的 npm / vite，而不是运行时。

### 2.2 地域与备案的关键决策

| 情况 | 结论 |
|---|---|
| 大陆地域 + 想用域名 | **必须 ICP 备案**。阿里云控制台「ICP 备案」入口发起，免费，通常 1~3 周；备案期间可先用 IP 访问开发调试 |
| 大陆地域 + 纯自用（IP 访问） | 不需要域名和备案，直接跳到 7.4 节的替代方案 |
| 香港地域 | 域名免备案，但访问延迟略高；注意香港服务器出网访问国内模型 API 正常 |

> 备案要求域名在国内注册商处实名认证，且服务器在阿里云大陆地域。HTTPS 证书的签发也依赖域名（IP 无法签发 Let's Encrypt 证书）。

### 2.3 准备清单

- [ ] 服务器已购买，拿到公网 IP
- [ ] （可选）域名已购买并实名认证；大陆服务器计划绑域名则发起备案
- [ ] 至少一个模型 API Key（DeepSeek / 火山 / 混元任一）
- [ ] 代码已推送到 Git 远端（GitHub 或 Gitee）

## 3. 服务器初始化

### 3.1 首次登录与基础设置

```bash
ssh root@<服务器IP>

# 时区
timedatectl set-timezone Asia/Shanghai

# 创建部署用户（可选但推荐，之后都用 deploy 操作）
adduser deploy
usermod -aG sudo deploy
```

建议本地配置 SSH 密钥登录后关闭密码登录（轻量/ECS 控制台重置密钥也可）：

```bash
# 本地（Git Bash / PowerShell 均可）
ssh-keygen -t ed25519
ssh-copy-id deploy@<服务器IP>   # Windows 无 ssh-copy-id 时，手动把公钥追加到服务器 ~/.ssh/authorized_keys
```

### 3.2 安装 Docker

```bash
# 官方脚本（阿里云镜像源）
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
systemctl enable --now docker

# 验证
docker --version && docker compose version
```

配置镜像加速（拉取 pgvector/redis/nginx 等基础镜像必须，否则大陆服务器拉取超时）：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io"
  ]
}
EOF
sudo systemctl restart docker
```

> 阿里云容器镜像服务控制台可为每个账号生成专属加速器地址（形如 `https://<id>.mirror.aliyuncs.com`），把它加进上面列表最稳。公共加速器地址时常失效，拉不动时换一个即可。

### 3.3 防火墙 / 安全组：只放行 22、80、443

- **轻量应用服务器**：控制台实例详情 →「防火墙」→ 添加规则，放行 TCP 80、443（22 默认已放行）。
- **ECS**：控制台实例 →「安全组」→ 配置规则，添加入方向规则放行 80/443。

> ⚠️ 绝对不要放行 5432（PostgreSQL）和 6379（Redis）。生产编排里这两个服务本就没有映射宿主端口，防火墙是第二道保险。

### 3.4 加 swap（2G 内存机器必须执行，4G 及以上可选）

内存紧张时，内核会直接杀掉占内存最多的进程（通常是构建中的 node，或线上的后端）。加 swap 后是变慢而不是被杀。

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 4. 获取代码

在服务器上以 deploy 用户操作：

```bash
sudo apt update && sudo apt install -y git
cd ~

# 推荐 Gitee（大陆拉取快）；GitHub 也可达但偶尔慢
git clone https://gitee.com/<你的用户名>/cairn.git
cd cairn
```

私有仓库的免密方式：Gitee 仓库 →「管理」→「部署公钥」添加服务器公钥（只读即可），或 HTTPS + 私人令牌。

克隆后先确认源码包完整（该包曾因 `.gitignore` 的 `samples/` 规则被误忽略而未入库，缺它后端无法启动）：

```bash
ls apps/api/samples     # 应有 __init__.py coverage.py router.py schemas.py 四个文件
```

## 5. 生产配置

### 5.1 生成 `.env.production`

```bash
cd ~/cairn
cp .env.production.example .env.production

# 生成三个随机值，逐项填入 .env.production
openssl rand -hex 32   # → CAIRN_SECRET_KEY
openssl rand -hex 32   # → JWT_SECRET（与上面不同）
openssl rand -hex 16   # → POSTGRES_PASSWORD（记得同步改 DATABASE_URL 里的密码）
vim .env.production
```

### 5.2 必须正确填写的项

| 配置项 | 要求 | 常见错误 |
|---|---|---|
| `POSTGRES_PASSWORD` / `DATABASE_URL` | 两处密码一致；主机名是 **`postgres`**（容器名） | 写成 `127.0.0.1:5433`（那是本地开发端口映射） |
| `CAIRN_SECRET_KEY` / `JWT_SECRET` | `openssl rand -hex 32` 生成，**不能用 example 里的默认值** | 与本地 `.env` 复用同一把 |
| `CORS_ORIGINS` | JSON 数组格式，如 `["https://your-domain.com"]`；没有域名时填 `["http://<服务器IP>"]` | 写成逗号分隔字符串 |
| `ENVIRONMENT` | `prod` | — |
| 模型 `*_API_KEY` | 至少启用一个；注释打开填 Key | 提交到 Git |

### 5.3 模型密钥的两种方式

1. **环境变量**（单实例自用最简单）：直接写在 `.env.production`，不落库、不进日志。
2. **加密凭证**（多用户/正式对外推荐）：保持 `*_API_KEY` 注释状态，上线后在前端「凭证」面板录入，服务端加密存库。

两者机制已在 M1 落地，见 `docs/ARCHITECTURE.md`；个人部署用方式 1 即可。

### 5.4 创建证书与备份目录

```bash
mkdir -p certs certbot-www backups
```

## 6. 首次部署与验证

### 6.1 一键部署

```bash
cd ~/cairn
bash scripts/deploy.sh
```

脚本依次执行：构建 api/web 两个镜像 → 启动全部服务 → 等待 `/api/v1/health` 通过 → `alembic upgrade head` 迁移 → 打印服务状态。

### 6.2 手动分步（等价，排查问题时用）

```bash
C="docker compose -f docker-compose.prod.yml --env-file .env.production"

$C build                 # 构建镜像
$C up -d                 # 启动（postgres/redis 先健康，api 再起，web 最后）
$C ps                    # 确认四个服务都是 healthy/running
$C exec api python -m alembic upgrade head   # 数据库迁移
curl http://127.0.0.1/api/v1/health          # 本机自检
```

### 6.3 验证清单

浏览器逐项确认（用 IP 访问时先完成 2.3 的防火墙放行）：

- [ ] `http://<服务器IP>/` 打开前端登录页
- [ ] `http://<服务器IP>/api/v1/health` 返回健康 JSON
- [ ] `http://<服务器IP>/docs` 打开 API 文档
- [ ] 注册账号 → 登录成功
- [ ] 在对话页发一条消息，模型能正常回复（验证出网到模型 Provider、密钥生效）
- [ ] 上传一个 Markdown/ZIP 触发复盘，**观察进度条逐字流式出现**（验证 SSE 反代配置）
- [ ] 「评测」页能看到延迟/成本数据（验证计量埋点）

全部通过即上线完成。按 `RELEASE_CHECKLIST.md` 的灰度节奏：先自用 1~2 周，再放内测。

## 7. 域名、备案与 HTTPS

前提：域名已完成 ICP 备案（大陆服务器）并添加 A 记录解析到服务器 IP。

### 7.1 方案 A：阿里云免费证书（推荐，最简单）

1. 控制台 → 搜索「SSL 证书」→ 免费证书 → 申请，填域名，DNS 自动验证，签发约几分钟。
2. 下载证书，格式选 **Nginx**，解压得到 `.pem`（证书）和 `.key`（私钥）。
3. 上传到服务器并重命名：

   ```bash
   # 本地执行（Git Bash）
   scp xxx.pem deploy@<服务器IP>:~/cairn/certs/server.crt
   scp xxx.key deploy@<服务器IP>:~/cairn/certs/server.key
   ```
4. 把 `apps/web/nginx.conf` 的 80 端口 server 块替换为下面的 HTTPS 模板（见 7.3），重新部署 web：

   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build web
   ```
5. **到期续期**：目前阿里云个人免费证书有效期 3 个月，设置日历提醒，到期前重新申请并重复 3~4 步。

### 7.2 方案 B：certbot 自动续期

```bash
# 服务器上
sudo apt install -y certbot
sudo certbot certonly --webroot -w ~/cairn/certbot-www -d your-domain.com \
  --email <你的邮箱> --agree-tos --no-eff-email
```

`certbot-www` 目录已由 web 容器挂载为 `/var/www/certbot`，`http://域名/.well-known/acme-challenge/` 路由已在 nginx.conf 中放行，HTTP-01 验证可以直接通过。

自动续期 hook：

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-cairn.sh <<'EOF'
#!/bin/bash
cd /home/deploy/cairn
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T web nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-cairn.sh
sudo certbot renew --dry-run   # 验证续期流程
```

> 容器需要读取宿主机 `/etc/letsencrypt`：在 `docker-compose.prod.yml` 的 web 服务 volumes 里加一行 `- /etc/letsencrypt:/etc/letsencrypt:ro`。

### 7.3 HTTPS 版 nginx.conf 模板

把 `apps/web/nginx.conf` 整体替换为（证书路径按方案 A/B 二选一）：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    http2 on;
    server_name your-domain.com;

    # 方案 A（阿里云证书）
    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
    # 方案 B（certbot）改用下面两行
    # ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    client_max_body_size 50m;
    root /usr/share/nginx/html;
    index index.html;
    gzip on;
    gzip_min_length 1k;
    gzip_types text/css application/javascript application/json image/svg+xml;

    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    location /api/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;          # SSE 关键，勿删
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location / { try_files $uri $uri/ /index.html; }
}
```

同时把 `.env.production` 的 `CORS_ORIGINS` 更新为 `["https://your-domain.com"]` 后重启 api。

### 7.4 没有域名 / 备案期间的替代方案

- 直接用 `http://<服务器IP>/` 访问（本手册默认状态），功能完整，仅无加密。**自用阶段可接受；一旦有第二个人用，必须上 HTTPS**——登录 JWT 与对话内容都是明文传输。
- 临时替代：香港地域服务器 + 域名（免备案）+ 方案 B 证书。

## 8. 日常运维

所有命令都在服务器 `~/cairn` 目录执行，`C` 代表 `docker compose -f docker-compose.prod.yml --env-file .env.production`。

### 8.1 发布新版本

```bash
# 本地：提交并推送
git push

# 服务器：
git pull
bash scripts/deploy.sh
```

`deploy.sh` 每次都会执行迁移，有新迁移时自动应用；没有则幂等跳过。

### 8.2 回滚

```bash
git log --oneline -5          # 找到上一个可用版本
git checkout <commit或tag>
bash scripts/deploy.sh
```

> 注意：若新版本包含**不可逆**的数据库迁移（删列、改类型），回滚前先按第 9 章备份，必要时恢复到备份点。常规新增列/新表的迁移向前兼容，可直接回滚代码。

### 8.3 日志

```bash
$C logs -f api        # 后端日志（含 request_id，可串联一次对话全链路）
$C logs -f web        # nginx 访问/错误日志
$C logs -f postgres
docker stats          # 实时资源占用
```

排障顺序：先看 `$C ps` 是否有服务不健康 → `$C logs api` 找报错 → 带上日志里的 `request_id` 检索该次请求全链路。

### 8.4 磁盘与镜像清理

```bash
docker system df                     # 查看 Docker 占用
docker image prune -f                # 清理悬空镜像（每次重新 build 会产生旧层）
```

## 9. 备份与恢复

### 9.1 手动备份

```bash
mkdir -p backups
$C exec -T postgres pg_dump -U cairn -d cairn | gzip > backups/cairn-$(date +%F).sql.gz
```

### 9.2 定时备份（cron，保留 14 天）

```bash
crontab -e   # 以 deploy 用户
```

```cron
0 3 * * * cd /home/deploy/cairn && docker compose -f docker-compose.prod.yml --env-file .env.production exec -T postgres pg_dump -U cairn -d cairn | gzip > backups/cairn-$$(date +\%F).sql.gz && find backups -name 'cairn-*.sql.gz' -mtime +14 -delete
```

> cron 里 `%` 必须转义为 `\%`，`$$` 是让 cron 用 shell 执行 date。

**异地容灾**：单机备份挡不住磁盘损坏。二选一：

- 阿里云 OSS：安装 ossutil，cron 追加一条 `ossutil cp backups/cairn-$(date +%F).sql.gz oss://<bucket>/db/`；
- 简易版：cron 里 `scp` 到本地家里的机器 / 另一台服务器。

### 9.3 恢复演练（上线后一周内做一次）

```bash
# 恢复到临时库验证备份可用，不动线上库
$C exec -T postgres psql -U cairn -d cairn -c "CREATE DATABASE cairn_restore;"
gunzip -c backups/cairn-<某日期>.sql.gz | $C exec -T postgres psql -U cairn -d cairn_restore
$C exec -T postgres psql -U cairn -d cairn_restore -c "\dt"   # 确认表齐全
$C exec -T postgres psql -U cairn -d cairn -c "DROP DATABASE cairn_restore;"
```

真实恢复（灾难场景）：先 `$C stop api`，对 `cairn` 库执行同样的 psql 导入，再 `$C start api`。

### 9.4 其他持久化数据

- PostgreSQL 数据在 named volume `pgdata`；Redis 数据在 `redisdata`（AOF）。Redis 仅作缓存，**丢失可重建**，无需备份。
- 升级 pgvector/pg16 大版本需要 `pg_dump` 逻辑迁移，不能直接换镜像复用卷。

## 10. 监控与告警

- **存活探活**：阿里云控制台 → 云监控 → 站点监控，添加 `http://<IP>/api/v1/health`（或 HTTPS 域名），失败时短信/邮件告警。免费额度足够个人使用。
- **资源告警**：云监控对实例 CPU/内存/磁盘设阈值（内存 >85%、磁盘 >80% 告警）。
- **应用内指标**：前端「评测」页已呈现延迟 P50/P95、Token 成本、Schema 通过率等六维指标（M12 埋点）；定期查看，成本异常=凭证泄露或死循环调用的第一信号。
- **熔断与限流**：网关 QPS=5、并发=20、熔断已内置；上线后如需收紧，改 `.env.production` 的 `GATEWAY_*` 后 `$C up -d api`。

## 11. 安全清单

对应 `docs/RELEASE_CHECKLIST.md`，发布前逐项确认：

- [ ] `.env.production` 三个默认值已全部替换（数据库密码、两把 Secret），文件未进 Git（`.gitignore` 已排除，`git status` 确认）
- [ ] 防火墙/安全组只开 22/80/443，5432/6379 公网不可达（可用 `nmap -p 5432 <IP>` 从外网验证，应为 filtered/closed）
- [ ] 模型 API Key 走环境变量或加密凭证，未硬编码、未提交；在 Provider 控制台设置 Key 的用量上限
- [ ] `git log --all --full-history -- .env` 确认历史中无 `.env` 提交记录
- [ ] HTTPS 启用后，`CORS_ORIGINS` 只留正式域名
- [ ] 对外提供服务前补齐：隐私说明（收集什么、存多久、如何删除）、账号注销与数据导出路径（导出功能 M9 已有，删除路径 M16 已有）
- [ ] SSH 已用密钥登录（可选：关闭密码登录 `/etc/ssh/sshd_config` 中 `PasswordAuthentication no`）

## 12. 常见问题 FAQ

**Q1：对话进度/回复不逐字出现，一次性刷出来**
Nginx 缓冲了 SSE。确认 `nginx.conf` 的 `/api/` 块里有 `proxy_buffering off;`，改完 `up -d --build web` 重建。

**Q2：前端能打开，接口全部 502**
`$C ps` 看 api 是否 healthy；`$C logs api` 看启动报错。最常见原因：`.env.production` 的 `DATABASE_URL` 写成了 `127.0.0.1`（容器内指向自身），必须用容器名 `postgres`。

**Q3：`docker compose up` 报错 `POSTGRES_PASSWORD is required`**
compose 命令漏了 `--env-file .env.production`，或该文件还没创建。deploy.sh 会自动带参数并预检。

**Q4：拉镜像超时 / `pgvector` 镜像拉不动**
`/etc/docker/daemon.json` 镜像加速器失效，换一个加速地址重启 docker（3.2 节）。

**Q5：构建 api 镜像时 pip/uv 超时**
Dockerfile 已默认走清华 PyPI 镜像；若仍失败，构建时显式覆盖：
`docker build --build-arg UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ .`

**Q6：构建 web 镜像时 npm 卡住或 lockfile 校验失败**
Dockerfile 用 `npm ci` 严格按 lockfile 安装；若 `package-lock.json` 与 `package.json` 不同步，先本地 `npm install` 更新 lockfile 并提交，再重新发布。

**Q7：服务莫名重启 / 响应变慢**
`docker stats` 看内存；2G 机器大概率 OOM。按 3.4 加 swap，或升配 4G。`$C logs api` 结尾出现 `Killed` 即为 OOM。

**Q8：迁移报错 `Can't locate revision`**
迁移版本与数据库 `alembic_version` 不一致（回滚后发布旧代码等场景）。先备份，再决定 `alembic downgrade` 或 `alembic stamp`。

**Q9：访问域名被提示未备案**
大陆服务器 + 未备案域名会被阿里云拦截。完成备案前用 IP 访问，或换香港地域。

**Q10：服务器时间/日志时区不对**
镜像已设 `TZ=Asia/Shanghai`；宿主机执行 `timedatectl set-timezone Asia/Shanghai`。

## 13. 与本地开发环境的差异对照

| 维度 | 本地开发（README） | 生产（本手册） |
|---|---|---|
| 编排文件 | `docker-compose.yml`（只含 pg+redis，映射 5433/6379） | `docker-compose.prod.yml`（四服务，pg/redis 不映射端口） |
| 后端启动 | `.venv/Scripts/python.exe -m uvicorn --reload` | api 容器内置 CMD，`restart: unless-stopped` |
| 依赖管理 | uv + `.venv` | 镜像内 `uv sync --frozen`，版本由 `uv.lock` 锁定 |
| 前端 | Vite dev server（:5173，代理 /api） | 构建产物进 Nginx 容器，同域反代 |
| 数据库地址 | `127.0.0.1:5433` | `postgres:5432`（容器网络） |
| 配置文件 | `.env` | `.env.production`（不进 Git） |
| 迁移 | 手动 `alembic upgrade head` | `deploy.sh` 每次发布自动执行 |
| 入口 | 两个端口（5173/8000） | 单端口 80/443 |
