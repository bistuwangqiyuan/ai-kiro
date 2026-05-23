#!/usr/bin/env bash
# =============================================================
# cn-deploy.sh — 在火山 ECS / 阿里 ECS / 腾讯 CVM 上一键部署
#
# 适用系统：Ubuntu 22.04 / 24.04（推荐），Debian 12 也兼容。
# 跑此脚本前请：
#   1) 已 SSH 登录 ECS
#   2) 该 ECS 有公网 IP，安全组放行 80、443、22 端口
#   3) /opt/manhuaju 目录权限允许当前用户读写
#
# 用法：
#   bash cn-deploy.sh                          # 全自动安装+起服
#   bash cn-deploy.sh --no-pull                # 跳过 git pull（首次部署时也跳过）
#   bash cn-deploy.sh --image-only             # 只构建镜像，不起服务
#   bash cn-deploy.sh --restart                # 仅重启已有服务
# =============================================================

set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/manhuaju}"
GIT_REPO="${GIT_REPO:-https://github.com/bistuwangqiyuan/ai-kiro.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
COMPOSE_FILE="$PROJECT_DIR/deploy/cn-easy/docker-compose.cn.yml"

# ---------- pretty print ----------
RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; CYN=$'\033[36m'; NC=$'\033[0m'
step()  { echo -e "\n${CYN}==> $*${NC}"; }
ok()    { echo -e "${GRN}OK${NC}  $*"; }
warn()  { echo -e "${YLW}!!${NC}  $*"; }
fail()  { echo -e "${RED}XX${NC}  $*" >&2; exit 1; }

DO_PULL=1
DO_BUILD=1
DO_UP=1

for arg in "$@"; do
    case "$arg" in
        --no-pull) DO_PULL=0 ;;
        --image-only) DO_UP=0 ;;
        --restart) DO_PULL=0; DO_BUILD=0 ;;
        -h|--help) grep -E '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) ;;
    esac
done

[[ $EUID -eq 0 ]] || { warn "建议用 sudo bash $0 运行（首次需 apt 安装）"; }

# ---------- 1) docker + compose ----------
step "1/6 安装 Docker（如已装则跳过）"
if ! command -v docker >/dev/null 2>&1; then
    # 用阿里云镜像源加速
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sh /tmp/get-docker.sh --mirror Aliyun
    systemctl enable --now docker
    ok "Docker 安装完成"
else
    ok "Docker 已存在 $(docker --version | head -c 60)"
fi

# Docker daemon 用国内镜像源加速 pull
DAEMON_JSON="/etc/docker/daemon.json"
if ! grep -q "registry-mirrors" $DAEMON_JSON 2>/dev/null; then
    step "1.1 配置 Docker 国内镜像源（pull 加速 5-10 倍）"
    mkdir -p /etc/docker
    cat >$DAEMON_JSON <<'JSON'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.imgdb.de",
    "https://docker-0.unsee.tech",
    "https://docker.hlmirror.com",
    "https://docker.1ms.run"
  ],
  "log-driver": "json-file",
  "log-opts": {"max-size": "50m", "max-file": "5"}
}
JSON
    systemctl restart docker
    ok "镜像源已配置"
fi

# ---------- 2) git clone / pull ----------
step "2/6 同步代码到 $PROJECT_DIR"
mkdir -p "$(dirname "$PROJECT_DIR")"
if [[ ! -d "$PROJECT_DIR/.git" ]]; then
    git clone --depth 1 -b "$GIT_BRANCH" "$GIT_REPO" "$PROJECT_DIR"
    ok "代码已克隆"
elif [[ $DO_PULL -eq 1 ]]; then
    cd "$PROJECT_DIR"
    git fetch --depth 1 origin "$GIT_BRANCH"
    git reset --hard "origin/$GIT_BRANCH"
    ok "代码已更新到 $(git rev-parse --short HEAD)"
else
    ok "跳过 git pull"
fi

cd "$PROJECT_DIR"

# ---------- 3) .env ----------
step "3/6 确认 .env 已配置"
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    cp "$PROJECT_DIR/deploy/cn-easy/.env.cn-easy.example" "$PROJECT_DIR/.env"
    warn ".env 已从模板复制，请编辑 $PROJECT_DIR/.env 填入火山 3 把 Key 后重跑本脚本"
    warn "  nano $PROJECT_DIR/.env"
    exit 2
fi

# 校验必填项
MISSING=()
source <(grep -E '^(VOLCENGINE_VISUAL_AK|VOLCENGINE_VISUAL_SK|VOLCENGINE_ARK_API_KEY|VOLCENGINE_TOS_AK|VOLCENGINE_TOS_SK|VOLCENGINE_TOS_BUCKET)=' "$PROJECT_DIR/.env" | sed 's/^/export /')
[[ -z "${VOLCENGINE_VISUAL_AK:-}" ]] && MISSING+=(VOLCENGINE_VISUAL_AK)
[[ -z "${VOLCENGINE_VISUAL_SK:-}" ]] && MISSING+=(VOLCENGINE_VISUAL_SK)
[[ -z "${VOLCENGINE_ARK_API_KEY:-}" ]] && MISSING+=(VOLCENGINE_ARK_API_KEY)
[[ -z "${VOLCENGINE_TOS_AK:-}" ]] && MISSING+=(VOLCENGINE_TOS_AK)
[[ -z "${VOLCENGINE_TOS_SK:-}" ]] && MISSING+=(VOLCENGINE_TOS_SK)
if [[ ${#MISSING[@]} -gt 0 ]]; then
    fail ".env 缺少必填项：${MISSING[*]}  请编辑 $PROJECT_DIR/.env 后重跑"
fi
ok ".env 校验通过"

# ---------- 4) build / pull image ----------
step "4/6 构建镜像（首次约 5-8 分钟）"
if [[ $DO_BUILD -eq 1 ]]; then
    # 用 buildkit 加速
    export DOCKER_BUILDKIT=1
    docker compose -f "$COMPOSE_FILE" build --pull api
    ok "镜像构建完成"
else
    ok "跳过镜像构建"
fi

# ---------- 5) up ----------
if [[ $DO_UP -eq 1 ]]; then
    step "5/6 启动 docker compose 栈（api + worker + caddy）"
    docker compose -f "$COMPOSE_FILE" up -d
    sleep 3
    ok "compose up 完成"

    # ---------- 6) health check ----------
    step "6/6 等待服务就绪（最多 90s）"
    for i in $(seq 1 18); do
        sleep 5
        STATUS=$(curl -fsS -m 3 http://127.0.0.1/health 2>/dev/null | grep -o '"status":"ok"' || true)
        if [[ -n "$STATUS" ]]; then
            ok "/health 返回 ok"
            break
        fi
        echo -n "."
    done
    echo ""

    PUBLIC_IP=$(curl -fsS -m 3 https://ipinfo.io/ip 2>/dev/null \
                || curl -fsS -m 3 https://api.ipify.org 2>/dev/null \
                || curl -fsS -m 3 https://ifconfig.me 2>/dev/null || echo "<unknown>")
    DOMAIN=$(grep '^MANHUAJU_DOMAIN=' "$PROJECT_DIR/.env" | cut -d= -f2 | tr -d '"')
    if [[ -n "$DOMAIN" ]]; then
        URL="https://$DOMAIN"
    else
        URL="http://$PUBLIC_IP"
    fi
    echo -e "\n${GRN}========== 上线成功 ==========${NC}"
    echo -e "  Web 控制台 : $URL/"
    echo -e "  API 文档   : $URL/docs"
    echo -e "  健康检查   : $URL/health"
    echo -e "  KPI 看板   : $URL/v1/kpi"
    echo ""
    echo -e "  ECS 公网 IP : ${PUBLIC_IP}"
    if [[ -z "$DOMAIN" ]]; then
        echo -e "  ${YLW}提示：要 HTTPS？在 .env 设 MANHUAJU_DOMAIN=你的域名 → 解析到 ${PUBLIC_IP} → bash $0 --restart${NC}"
    fi
    echo ""
    echo -e "  查看日志   : docker compose -f $COMPOSE_FILE logs -f"
    echo -e "  重启       : bash $0 --restart"
    echo -e "  停止       : docker compose -f $COMPOSE_FILE down"
fi
