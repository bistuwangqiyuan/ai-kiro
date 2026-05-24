"""
火山 VeFaaS 无服务器一键开通脚本（v2）。

适配新 SDK `volcenginesdkcr` + `volcenginesdkvefaas`，对接用户实际的火山账号资源。

行为：
  1) 用 volcenginesdkcr 自动发现已有 VCR 实例 / 命名空间 / 仓库（如缺则创建）
  2) 自动设置 VCR docker login 密码（API 调用），打印 username / password / image url
  3) 用 volcenginesdkvefaas 创建/更新 manhuaju-api + manhuaju-worker 函数
  4) 给 worker 函数挂定时触发器（每分钟一次）
  5) 打印 API 函数的公网端点

子命令：
    --step credentials   只做 VCR 用户密码设置（输出 JSON：{username, password, image_url}）
    --step functions     只建/更新 VeFaaS 函数（要求镜像已 push 到 VCR）
    --step all (default) 全做

依赖：
    pip install volcengine volcengine-python-sdk redo
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
# .env loader（不依赖 python-dotenv）
# --------------------------------------------------------------------------- #
def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def setup_creds(ak: str, sk: str, region: str) -> None:
    import volcenginesdkcore as core
    cfg = core.Configuration()
    cfg.ak = ak
    cfg.sk = sk
    cfg.region = region
    core.Configuration.set_default(cfg)


# --------------------------------------------------------------------------- #
# Step 1: VCR registry / namespace / repo / docker login password
# --------------------------------------------------------------------------- #
def gen_password() -> str:
    """生成 18 位强密码，符合火山 VCR 密码规则。

    保守集合 = 大写 + 小写 + 数字（火山 VCR 对部分符号会拒，避免风险用纯字母数字）。
    """
    alphabet = string.ascii_letters + string.digits
    must = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(string.digits),
    ]
    rest = [secrets.choice(alphabet) for _ in range(12)]
    pw_list = must + rest
    secrets.SystemRandom().shuffle(pw_list)
    return "".join(pw_list)


def discover_registry(api: Any, prefer: str | None = None) -> str:
    """选第一个 Running 状态的 VCR 实例；缺省优先匹配 `prefer` 名。"""
    import volcenginesdkcr as cr
    r = api.list_registries(cr.ListRegistriesRequest(page_size=50))
    items = getattr(r, "items", None) or []
    if not items:
        raise RuntimeError("账号下没有任何 VCR 实例；请先到 https://console.volcengine.com/cr 开通")
    if prefer:
        for it in items:
            if getattr(it, "name", "") == prefer:
                return prefer
    return getattr(items[0], "name")


def ensure_namespace(api: Any, registry: str, name: str) -> None:
    import volcenginesdkcr as cr
    r = api.list_namespaces(cr.ListNamespacesRequest(registry=registry, page_size=100))
    items = getattr(r, "items", None) or []
    if any(getattr(it, "name", "") == name for it in items):
        print(f"[vcr] namespace '{name}' already exists")
        return
    print(f"[vcr] creating namespace '{name}' ...")
    api.create_namespace(cr.CreateNamespaceRequest(
        name=name, registry=registry, project="default",
    ))
    print(f"[vcr] OK namespace '{name}' created")


def ensure_repository(api: Any, registry: str, namespace: str, repo: str) -> None:
    import volcenginesdkcr as cr
    r = api.list_repositories(cr.ListRepositoriesRequest(registry=registry, page_size=100))
    items = getattr(r, "items", None) or []
    if any(
        getattr(it, "namespace", "") == namespace and getattr(it, "name", "") == repo
        for it in items
    ):
        print(f"[vcr] repo '{namespace}/{repo}' already exists")
        return
    print(f"[vcr] creating repo '{namespace}/{repo}' ...")
    api.create_repository(cr.CreateRepositoryRequest(
        name=repo,
        namespace=namespace,
        registry=registry,
        access_level="Private",
        description="AI 漫剧 Autopilot v4 (auto-provisioned)",
    ))
    print(f"[vcr] OK repo '{namespace}/{repo}' created")


def setup_credentials_step(env: dict[str, str], region: str, vcr_name: str | None, vcr_namespace: str, vcr_repo: str) -> dict[str, Any]:
    """Step 1: 发现 registry + 确保命名空间/仓库存在 + 查询 docker username。

    注意：火山 VCR Micro 版（小微）的 SetUser API 不可用；改用 GHA 内实时拿临时 token
    （GetAuthorizationToken）做 docker login，**无需任何密码** —— 用户零操作。
    """
    import volcenginesdkcr as cr
    api = cr.CRApi()

    registry = discover_registry(api, prefer=vcr_name)
    print(f"[vcr] using registry: {registry}")

    ensure_namespace(api, registry, vcr_namespace)
    ensure_repository(api, registry, vcr_namespace, vcr_repo)

    u = api.get_user(cr.GetUserRequest(registry=registry))
    username = getattr(u, "username", None) or ""
    print(f"[vcr] docker username = {username}")

    # 演示一下临时 token（GHA 里会自己取最新的）
    try:
        tok = api.get_authorization_token(cr.GetAuthorizationTokenRequest(registry=registry))
        print(f"[vcr] sample auth-token expires {getattr(tok, 'expire_time', '?')} (GHA 每次 build 自取最新)")
    except Exception as e:  # noqa: BLE001
        print(f"[vcr] i get_authorization_token check failed: {e}")

    # Volcengine VCR 域名规则：<instance>-<region>.cr.volces.com
    # （旧版 cr-{region}.volces.com 是公共仓库前缀；私有 instance 必须用上面形式）
    image_host = f"{registry}-{region}.cr.volces.com"
    image_prefix = f"{image_host}/{vcr_namespace}/{vcr_repo}"
    print(f"[vcr] image prefix = {image_prefix}")

    return {
        "registry": registry,
        "username": username,
        "image_host": image_host,
        "image_prefix": image_prefix,
    }


# --------------------------------------------------------------------------- #
# Step 2: VeFaaS functions
# --------------------------------------------------------------------------- #
def list_functions(api: Any, name: str) -> list[Any]:
    import volcenginesdkvefaas as vefaas
    r = api.list_functions(vefaas.ListFunctionsRequest(name=name, page_size=20))
    return list(getattr(r, "items", None) or [])


def build_envs(envs: dict[str, str]) -> list[Any]:
    import volcenginesdkvefaas as vefaas
    out = []
    for k, v in envs.items():
        if v is None or v == "":
            continue
        out.append(vefaas.EnvForCreateFunctionInput(key=k, value=str(v)))
    return out


def ensure_function(*, fn_name: str, image: str, command: list[str] | None,
                    port: int | None, cpu_milli: int, memory_mb: int,
                    request_timeout: int, max_concurrency: int,
                    envs: dict[str, str]) -> str:
    import volcenginesdkvefaas as vefaas
    api = vefaas.VEFAASApi()
    existing = list_functions(api, fn_name)
    if existing:
        fid = existing[0].id
        print(f"[vefaas] {fn_name} exists (id={fid}); updating image…")
        try:
            kw: dict[str, Any] = dict(
                id=fid, source=image, source_type="image",
                envs=build_envs(envs),
            )
            if command is not None:
                kw["command"] = command
            api.update_function(vefaas.UpdateFunctionRequest(**kw))
            print(f"[vefaas] OK {fn_name} updated")
            try:
                api.release(vefaas.ReleaseRequest(id=fid))
                print(f"[vefaas] OK {fn_name} released")
            except Exception as e:  # noqa: BLE001
                print(f"[vefaas] i release skipped: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"[vefaas] X update failed: {type(e).__name__}: {e}", file=sys.stderr)
        return fid

    print(f"[vefaas] creating {fn_name} ...")
    kw: dict[str, Any] = dict(
        name=fn_name,
        description=f"AI 漫剧 v4 auto-provisioned {fn_name}",
        runtime="native-custom-container",
        source=image,
        source_type="image",
        cpu_milli=cpu_milli,
        memory_mb=memory_mb,
        request_timeout=request_timeout,
        max_concurrency=max_concurrency,
        envs=build_envs(envs),
    )
    if port is not None:
        kw["port"] = port
    if command is not None:
        kw["command"] = command
    try:
        resp = api.create_function(vefaas.CreateFunctionRequest(**kw))
        fid = resp.id
        print(f"[vefaas] OK {fn_name} created id={fid}")
    except Exception as e:  # noqa: BLE001
        print(f"[vefaas] X create_function {fn_name} failed: {type(e).__name__}: {e}", file=sys.stderr)
        raise

    try:
        api.release(vefaas.ReleaseRequest(id=fid))
        print(f"[vefaas] OK {fn_name} released")
    except Exception as e:  # noqa: BLE001
        print(f"[vefaas] i release skipped: {e}")
    return fid


def ensure_timer(fn_id: str, cron: str = "0 * * * * *") -> None:
    """Crontab format on VeFaaS may use 6 fields (sec min hr day mon dow)."""
    import volcenginesdkvefaas as vefaas
    api = vefaas.VEFAASApi()
    try:
        triggers = api.list_triggers(vefaas.ListTriggersRequest(function_id=fn_id, page_size=20))
        items = getattr(triggers, "items", None) or []
        for t in items:
            t_type = (getattr(t, "type", "") or "").lower()
            if t_type == "timer":
                print(f"[vefaas] timer already attached to {fn_id}")
                return
    except Exception as e:  # noqa: BLE001
        print(f"[vefaas] i list_triggers skipped: {e}")

    print(f"[vefaas] adding timer (cron='{cron}') ...")
    # 火山 VeFaaS Timer crontab：6 字段（秒 分 时 日 月 周）
    try:
        api.create_timer(vefaas.CreateTimerRequest(
            function_id=fn_id, name="every-minute", crontab=cron, enabled=True,
        ))
        print("[vefaas] OK timer added")
    except Exception as e:  # noqa: BLE001
        print(f"[vefaas] X create_timer failed: {type(e).__name__}: {e}", file=sys.stderr)


def get_api_endpoint(fn_id: str) -> str | None:
    import volcenginesdkvefaas as vefaas
    try:
        api = vefaas.VEFAASApi()
        triggers = api.list_triggers(vefaas.ListTriggersRequest(function_id=fn_id, page_size=20))
        for t in getattr(triggers, "items", None) or []:
            ep = getattr(t, "endpoint", None) or getattr(t, "url", None)
            if ep:
                return ep
        r = api.get_function(vefaas.GetFunctionRequest(id=fn_id))
        return getattr(r, "trigger_url", None) or getattr(r, "endpoint", None)
    except Exception:
        return None


def functions_step(env: dict[str, str], full_image: str) -> dict[str, Any]:
    ak = env.get("VOLCENGINE_VISUAL_AK") or os.environ["VOLCENGINE_VISUAL_AK"]
    sk = env.get("VOLCENGINE_VISUAL_SK") or os.environ["VOLCENGINE_VISUAL_SK"]
    common_envs: dict[str, str] = {
        # ---- runtime ----
        "MANHUAJU_LIVE_MODE": "live",
        "MANHUAJU_API_DATA": "/data",
        "MANHUAJU_VIDEO_ENGINE": env.get("MANHUAJU_VIDEO_ENGINE", "auto"),
        # ---- Volcengine Visual (Xiaoyunque + Manhuaju Agent + Seedream + Jimeng) ----
        "VOLCENGINE_VISUAL_AK": ak,
        "VOLCENGINE_VISUAL_SK": sk,
        "VOLCENGINE_VISUAL_REGION": env.get("VOLCENGINE_VISUAL_REGION", "cn-north-1"),
        # ---- Volcengine Ark (Doubao Seed 1.6 LLM + VLM) ----
        "VOLCENGINE_ARK_API_KEY": env.get("VOLCENGINE_ARK_API_KEY", ""),
        # ---- Volcengine TOS ----
        "VOLCENGINE_TOS_AK": env.get("VOLCENGINE_TOS_AK", ak),
        "VOLCENGINE_TOS_SK": env.get("VOLCENGINE_TOS_SK", sk),
        "VOLCENGINE_TOS_BUCKET": env.get("VOLCENGINE_TOS_BUCKET", "manhuaju-assets"),
        "VOLCENGINE_TOS_REGION": env.get("VOLCENGINE_TOS_REGION", "cn-beijing"),
        "VOLCENGINE_TOS_ENDPOINT": env.get("VOLCENGINE_TOS_ENDPOINT", "tos-cn-beijing.volces.com"),
        # ---- 国产 LLM fallback chain ----
        "DASHSCOPE_API_KEY": env.get("DASHSCOPE_API_KEY", ""),
        "TONGYI_API_KEY": env.get("TONGYI_API_KEY", ""),
        "DEEPSEEK_API_KEY": env.get("DEEPSEEK_API_KEY", ""),
        "GLM_API_KEY": env.get("GLM_API_KEY", ""),
        "MOONSHOT_API_KEY": env.get("MOONSHOT_API_KEY", ""),
        "MISTRAL_API_KEY": env.get("MISTRAL_API_KEY", ""),
        "GROQ_API_KEY": env.get("GROQ_API_KEY", ""),
        "XAI_API_KEY": env.get("XAI_API_KEY", ""),
        "SPARK_API_KEY": env.get("SPARK_API_KEY", ""),
        # ---- optional international ----
        "ANTHROPIC_API_KEY": env.get("ANTHROPIC_API_KEY", ""),
        "ANTHROPIC_BASE_URL": env.get("ANTHROPIC_BASE_URL", ""),
        "ELEVENLABS_API_KEY": env.get("ELEVENLABS_API_KEY", ""),
        "FAL_KEY": env.get("FAL_KEY", ""),
    }

    api_fid = ensure_function(
        fn_name="manhuaju-api",
        image=full_image, command=None, port=8080,
        cpu_milli=2000, memory_mb=4096, request_timeout=1800, max_concurrency=10,
        envs={**common_envs, "UVICORN_WORKERS": "2"},
    )
    worker_fid = ensure_function(
        fn_name="manhuaju-worker",
        image=full_image,
        command=["python", "-m", "scripts.run_worker_once"],
        port=None,
        cpu_milli=2000, memory_mb=4096, request_timeout=1800, max_concurrency=1,
        envs={**common_envs, "MANHUAJU_BURST_JOBS": "1", "MANHUAJU_BURST_BUDGET_S": "1500"},
    )
    ensure_timer(worker_fid, cron="0 */1 * * * *")
    return {
        "api_fid": api_fid,
        "worker_fid": worker_fid,
        "api_endpoint": get_api_endpoint(api_fid),
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--step", choices=["all", "credentials", "functions"], default="all")
    p.add_argument("--region", default=os.environ.get("VEFAAS_REGION", "cn-beijing"))
    p.add_argument("--vcr-name", default=os.environ.get("VCR_REGISTRY_NAME"))
    p.add_argument("--vcr-namespace", default=os.environ.get("VCR_NAMESPACE_NAME", "manhuaju"))
    p.add_argument("--vcr-repo", default=os.environ.get("VCR_REPO_NAME", "manhuaju-autopilot"))
    p.add_argument("--image-tag", default=os.environ.get("IMAGE_TAG", "latest"))
    p.add_argument("--json", action="store_true", help="output final result as JSON to stdout")
    args = p.parse_args()

    root = Path(__file__).resolve().parents[2]
    env = load_env(root / ".env")
    ak = env.get("VOLCENGINE_VISUAL_AK") or os.environ.get("VOLCENGINE_VISUAL_AK")
    sk = env.get("VOLCENGINE_VISUAL_SK") or os.environ.get("VOLCENGINE_VISUAL_SK")
    if not ak or not sk:
        print("X 缺 VOLCENGINE_VISUAL_AK/SK", file=sys.stderr)
        return 2

    setup_creds(ak, sk, args.region)

    result: dict[str, Any] = {"step": args.step}

    if args.step in ("all", "credentials"):
        cred = setup_credentials_step(env, args.region, args.vcr_name, args.vcr_namespace, args.vcr_repo)
        result.update(cred)

    if args.step in ("all", "functions"):
        # Prefer prefix from credentials_step; otherwise discover registry on the fly
        image_prefix = result.get("image_prefix")
        if not image_prefix:
            import volcenginesdkcr as cr
            api = cr.CRApi()
            registry = discover_registry(api, prefer=args.vcr_name)
            image_prefix = f"{registry}-{args.region}.cr.volces.com/{args.vcr_namespace}/{args.vcr_repo}"
        full_image = f"{image_prefix}:{args.image_tag}"
        result["full_image"] = full_image
        fn = functions_step(env, full_image)
        result.update(fn)

    if args.json:
        # 仅最后一行打印 JSON 让 PS 解析；密码用占位符避免 stdout 泄露
        safe = dict(result)
        if "password" in safe and len(safe.get("password", "")) > 0:
            safe["password"] = safe["password"]  # 必须输出否则 PS 拿不到
        print("===JSON_RESULT===")
        print(json.dumps(safe, ensure_ascii=False))
    else:
        print("\nDone:")
        for k, v in result.items():
            display = v if k != "password" else f"({len(v)} chars, hidden)"
            print(f"  {k} = {display}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
