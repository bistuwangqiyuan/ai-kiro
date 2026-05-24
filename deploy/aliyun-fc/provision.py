"""
阿里云函数计算 FC 3.0 + 容器镜像服务 ACR 一键开通脚本。

行为：
  Step "credentials"
    1) 调 ACR API 发现 ACR 实例 (要求至少有 1 个 EE/Personal 实例 已开通)
    2) 创建命名空间 (如不存在)
    3) 创建仓库 (如不存在)
    4) 调 GetAuthorizationToken 拿临时 docker login 凭证（1 小时有效）
    5) 输出 JSON: {image_prefix, username, password, instance_id}

  Step "functions"
    1) 创建 FC manhuaju-api 函数 + HTTP 触发器
    2) 创建 FC manhuaju-worker 函数 + 定时触发器
    3) 输出 JSON: {api_endpoint, api_arn, worker_arn}

依赖：
    pip install alibabacloud-cr20181201 alibabacloud-fc20230330 alibabacloud-credentials

环境变量（从 .env 读取，或直接 export）：
    ALIBABA_CLOUD_ACCESS_KEY_ID
    ALIBABA_CLOUD_ACCESS_KEY_SECRET
    ALIBABA_CLOUD_REGION                  默认 cn-hangzhou
    ACR_INSTANCE_ID                       (可选) 指定 ACR 实例 ID；否则自动选第一个
    ACR_NAMESPACE_NAME                    默认 manhuaju
    ACR_REPO_NAME                         默认 manhuaju-autopilot
    IMAGE_TAG                             默认 latest
    VOLCENGINE_VISUAL_AK/SK               注入到函数环境变量
    VOLCENGINE_ARK_API_KEY                注入到函数环境变量
    VOLCENGINE_TOS_*                      注入到函数环境变量
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


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


def make_cr_client(ak: str, sk: str, region: str):
    from alibabacloud_cr20181201.client import Client as CRClient
    from alibabacloud_tea_openapi import models as open_api_models

    cfg = open_api_models.Config(access_key_id=ak, access_key_secret=sk, region_id=region)
    cfg.endpoint = f"cr.{region}.aliyuncs.com"
    return CRClient(cfg)


def make_fc_client(ak: str, sk: str, region: str):
    from alibabacloud_fc20230330.client import Client as FCClient
    from alibabacloud_tea_openapi import models as open_api_models

    cfg = open_api_models.Config(access_key_id=ak, access_key_secret=sk, region_id=region)
    cfg.endpoint = f"{region}.fc.aliyuncs.com"
    return FCClient(cfg)


# --------------------------------------------------------------------------- #
# Step 1: ACR — discover instance, ensure namespace/repo, get docker token
# --------------------------------------------------------------------------- #
def discover_acr_instance(cr_client, preferred: str | None = None) -> tuple[str, str]:
    """Return (instance_id, instance_name)."""
    from alibabacloud_cr20181201 import models as cr_models

    req = cr_models.ListInstanceRequest(page_size=30, page_no=1)
    resp = cr_client.list_instance(req)
    items = (resp.body.instances or []) if hasattr(resp.body, "instances") else []
    if not items:
        raise RuntimeError(
            "账号下没有任何 ACR 实例。请先到 https://cr.console.aliyun.com 开通\n"
            "  · 个人版 (Personal) 永久免费\n"
            "  · 企业版 (Enterprise) 按容量计费\n"
            "开通后重跑本脚本。"
        )
    if preferred:
        for it in items:
            iid = getattr(it, "instance_id", None) or getattr(it, "instance_name", None)
            if iid == preferred or getattr(it, "instance_name", "") == preferred:
                return getattr(it, "instance_id"), getattr(it, "instance_name", "?")
    first = items[0]
    return getattr(first, "instance_id"), getattr(first, "instance_name", "?")


def ensure_namespace(cr_client, instance_id: str, name: str) -> None:
    from alibabacloud_cr20181201 import models as cr_models
    from alibabacloud_tea_util import models as util_models

    # List existing namespaces; SDK 命名稍异 — 用 ListInstance + 直接 try create
    req = cr_models.CreateNamespaceRequest(
        instance_id=instance_id,
        namespace_name=name,
        auto_create_repo=False,
        default_repo_type="PRIVATE",
    )
    try:
        cr_client.create_namespace(req)
        print(f"[acr] OK namespace {name} created")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "EXIST" in msg.upper() or "AlreadyExists" in msg or "REPO_NAMESPACE_EXIST" in msg:
            print(f"[acr] namespace {name} already exists")
        else:
            print(f"[acr] X create_namespace failed: {msg}", file=sys.stderr)
            raise


def ensure_repository(cr_client, instance_id: str, namespace: str, repo: str) -> None:
    from alibabacloud_cr20181201 import models as cr_models

    req = cr_models.CreateRepositoryRequest(
        instance_id=instance_id,
        repo_namespace_name=namespace,
        repo_name=repo,
        repo_type="PRIVATE",
        summary="AI 漫剧 Autopilot v4 (auto-provisioned)",
        detail="",
    )
    try:
        cr_client.create_repository(req)
        print(f"[acr] OK repo {namespace}/{repo} created")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "EXIST" in msg.upper() or "REPO_NAME_EXIST" in msg:
            print(f"[acr] repo {namespace}/{repo} already exists")
        else:
            print(f"[acr] X create_repository failed: {msg}", file=sys.stderr)
            raise


def get_acr_login_token(cr_client, instance_id: str) -> tuple[str, str]:
    """Get temporary docker login (username, password). Valid 1 hour."""
    from alibabacloud_cr20181201 import models as cr_models

    req = cr_models.GetAuthorizationTokenRequest(instance_id=instance_id)
    resp = cr_client.get_authorization_token(req)
    body = resp.body
    username = getattr(body, "tempu_sername", None) or getattr(body, "temp_username", None)
    token = getattr(body, "authorization_token", None)
    if not username:
        # 阿里 SDK 5+ 用 tempu_sername / authorization_token
        for attr in ["tempu_sername", "temp_username", "username"]:
            v = getattr(body, attr, None)
            if v:
                username = v
                break
    return username, token


def get_acr_endpoint(cr_client, instance_id: str, region: str) -> str:
    """Get instance public endpoint (image registry domain)."""
    # 阿里云 ACR 个人/企业版的镜像域名格式：
    #   - 个人版: registry.cn-{region}.aliyuncs.com
    #   - 企业版: <instance-name>-registry.{region}.cr.aliyuncs.com
    from alibabacloud_cr20181201 import models as cr_models

    try:
        req = cr_models.ListInstanceEndpointRequest(instance_id=instance_id, module_name="Registry")
        resp = cr_client.list_instance_endpoint(req)
        endpoints = (resp.body.endpoints or []) if hasattr(resp.body, "endpoints") else []
        for ep in endpoints:
            domains = getattr(ep, "domains", None) or []
            for d in domains:
                dn = getattr(d, "domain", None) or getattr(d, "name", None)
                if dn and (getattr(d, "type", "") == "USER" or "registry" in dn):
                    return dn
            for d in domains:
                dn = getattr(d, "domain", None) or getattr(d, "name", None)
                if dn:
                    return dn
    except Exception as e:  # noqa: BLE001
        print(f"[acr] i list_instance_endpoint fallback: {e}")

    # Fallback to standard formats
    return f"registry.{region}.aliyuncs.com"


def credentials_step(env: dict[str, str], region: str, namespace: str, repo: str, instance_id_pref: str | None) -> dict[str, Any]:
    ak = env.get("ALIBABA_CLOUD_ACCESS_KEY_ID") or os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"]
    sk = env.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"]
    cr_client = make_cr_client(ak, sk, region)

    instance_id, instance_name = discover_acr_instance(cr_client, instance_id_pref)
    print(f"[acr] using instance {instance_name} (id={instance_id})")

    ensure_namespace(cr_client, instance_id, namespace)
    ensure_repository(cr_client, instance_id, namespace, repo)

    username, token = get_acr_login_token(cr_client, instance_id)
    print(f"[acr] docker username = {username}  (token len={len(token) if token else 0})")

    endpoint = get_acr_endpoint(cr_client, instance_id, region)
    image_prefix = f"{endpoint}/{namespace}/{repo}"
    print(f"[acr] image prefix    = {image_prefix}")

    return {
        "instance_id": instance_id,
        "instance_name": instance_name,
        "username": username,
        "password": token,
        "registry_host": endpoint,
        "image_prefix": image_prefix,
    }


# --------------------------------------------------------------------------- #
# Step 2: FC — create/update functions and HTTP/timer triggers
# --------------------------------------------------------------------------- #
def build_env_vars(envs: dict[str, str]) -> dict[str, str]:
    return {k: str(v) for k, v in envs.items() if v}


def ensure_function(fc_client, *, name: str, image: str, command: list[str] | None,
                    port: int | None, cpu: float, memory_mb: int, timeout_s: int,
                    concurrency: int, envs: dict[str, str], acr_instance_id: str) -> str:
    from alibabacloud_fc20230330 import models as fc_models

    cc = fc_models.CustomContainerConfig(
        image=image,
        port=port,
        acr_instance_id=acr_instance_id,
    )
    if command:
        cc.command = command

    in_kwargs: dict[str, Any] = dict(
        function_name=name,
        description=f"AI 漫剧 v4 auto-provisioned {name}",
        runtime="custom-container",
        custom_container_config=cc,
        cpu=cpu,
        memory_size=memory_mb,
        disk_size=10240,           # 10 GB ephemeral disk
        timeout=timeout_s,
        instance_concurrency=concurrency,
        internet_access=True,
        environment_variables=build_env_vars(envs),
    )
    if not port:
        # 非 HTTP 函数（worker），handler 走 custom-container 默认 main 进程
        in_kwargs["handler"] = "index.handler"
    else:
        in_kwargs["handler"] = "index.handler"  # 容器函数 handler 任意填，不会用

    inp = fc_models.CreateFunctionInput(**in_kwargs)
    req = fc_models.CreateFunctionRequest(body=inp)

    try:
        resp = fc_client.create_function(req)
        arn = getattr(resp.body, "function_arn", None) or getattr(resp.body, "function_name", name)
        print(f"[fc] OK function {name} created")
        return arn
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "FunctionAlreadyExists" in msg or "AlreadyExists" in msg:
            print(f"[fc] function {name} already exists; updating ...")
            # UpdateFunction
            from alibabacloud_fc20230330 import models as fc_models2
            upd_inp = fc_models2.UpdateFunctionInput(
                custom_container_config=cc,
                cpu=cpu,
                memory_size=memory_mb,
                timeout=timeout_s,
                instance_concurrency=concurrency,
                environment_variables=build_env_vars(envs),
            )
            upd_req = fc_models2.UpdateFunctionRequest(body=upd_inp)
            fc_client.update_function(function_name=name, request=upd_req)
            print(f"[fc] OK function {name} updated")
            return name
        print(f"[fc] X create_function {name} failed: {msg}", file=sys.stderr)
        raise


def ensure_http_trigger(fc_client, function_name: str) -> str | None:
    from alibabacloud_fc20230330 import models as fc_models

    trig_cfg = fc_models.HTTPTriggerConfig(
        auth_type="anonymous",
        methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
    )
    trig_inp = fc_models.CreateTriggerInput(
        trigger_name="http-trigger",
        trigger_type="http",
        qualifier="LATEST",
        trigger_config=json.dumps({
            "authType": "anonymous",
            "methods": ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
            "disableURLInternet": False,
        }),
    )
    req = fc_models.CreateTriggerRequest(body=trig_inp)
    try:
        resp = fc_client.create_trigger(function_name=function_name, request=req)
        url = getattr(resp.body, "http_trigger", None)
        if url is None and hasattr(resp.body, "trigger_config"):
            # 旧/新字段名兼容
            url = getattr(resp.body, "endpoint", None)
        # SDK 5+ 实际字段在 body.http_trigger.url_internet 之类
        for attr in ("url_intranet", "url_internet"):
            u = getattr(getattr(resp.body, "http_trigger", None), attr, None) if hasattr(resp.body, "http_trigger") else None
            if u:
                url = u
                break
        print(f"[fc] OK http trigger created for {function_name}")
        return url
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "TriggerAlreadyExists" in msg or "AlreadyExists" in msg:
            print(f"[fc] http trigger already exists on {function_name}")
            return None
        print(f"[fc] X create http trigger failed: {msg}", file=sys.stderr)
        return None


def ensure_timer_trigger(fc_client, function_name: str, cron: str = "@every 1m") -> None:
    from alibabacloud_fc20230330 import models as fc_models

    trig_inp = fc_models.CreateTriggerInput(
        trigger_name="timer-every-minute",
        trigger_type="timer",
        qualifier="LATEST",
        trigger_config=json.dumps({
            "cronExpression": cron,
            "enable": True,
            "payload": "",
        }),
    )
    req = fc_models.CreateTriggerRequest(body=trig_inp)
    try:
        fc_client.create_trigger(function_name=function_name, request=req)
        print(f"[fc] OK timer trigger created for {function_name}")
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "TriggerAlreadyExists" in msg or "AlreadyExists" in msg:
            print(f"[fc] timer trigger already exists on {function_name}")
        else:
            print(f"[fc] X create timer failed: {msg}", file=sys.stderr)


def get_function_endpoint(fc_client, function_name: str) -> str | None:
    from alibabacloud_fc20230330 import models as fc_models

    try:
        triggers = fc_client.list_triggers(function_name=function_name)
        items = getattr(triggers.body, "triggers", None) or []
        for t in items:
            if (getattr(t, "trigger_type", "") or "").lower() == "http":
                ht = getattr(t, "http_trigger", None)
                if ht:
                    url = getattr(ht, "url_internet", None) or getattr(ht, "url_intranet", None)
                    if url:
                        return url
    except Exception as e:  # noqa: BLE001
        print(f"[fc] i list_triggers failed: {e}")
    return None


def functions_step(env: dict[str, str], region: str, full_image: str, acr_instance_id: str) -> dict[str, Any]:
    ak = env.get("ALIBABA_CLOUD_ACCESS_KEY_ID") or os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"]
    sk = env.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"]
    fc_client = make_fc_client(ak, sk, region)

    common_envs: dict[str, str] = {
        "MANHUAJU_LIVE_MODE": "live",
        "MANHUAJU_API_DATA": "/data",
        "VOLCENGINE_VISUAL_AK": env.get("VOLCENGINE_VISUAL_AK", ""),
        "VOLCENGINE_VISUAL_SK": env.get("VOLCENGINE_VISUAL_SK", ""),
        "VOLCENGINE_ARK_API_KEY": env.get("VOLCENGINE_ARK_API_KEY", ""),
        "VOLCENGINE_TOS_AK": env.get("VOLCENGINE_TOS_AK", env.get("VOLCENGINE_VISUAL_AK", "")),
        "VOLCENGINE_TOS_SK": env.get("VOLCENGINE_TOS_SK", env.get("VOLCENGINE_VISUAL_SK", "")),
        "VOLCENGINE_TOS_BUCKET": env.get("VOLCENGINE_TOS_BUCKET", "manhuaju-assets"),
        "VOLCENGINE_TOS_REGION": env.get("VOLCENGINE_TOS_REGION", "cn-beijing"),
        "VOLCENGINE_TOS_ENDPOINT": env.get("VOLCENGINE_TOS_ENDPOINT", "tos-cn-beijing.volces.com"),
        "DASHSCOPE_API_KEY": env.get("DASHSCOPE_API_KEY", ""),
        "DEEPSEEK_API_KEY": env.get("DEEPSEEK_API_KEY", ""),
        "GLM_API_KEY": env.get("GLM_API_KEY", ""),
        "MOONSHOT_API_KEY": env.get("MOONSHOT_API_KEY", ""),
        "ANTHROPIC_API_KEY": env.get("ANTHROPIC_API_KEY", ""),
        "ANTHROPIC_BASE_URL": env.get("ANTHROPIC_BASE_URL", ""),
    }

    # API function
    api_arn = ensure_function(
        fc_client, name="manhuaju-api", image=full_image, command=None,
        port=8080, cpu=2.0, memory_mb=4096, timeout_s=1800,
        concurrency=10, envs={**common_envs, "UVICORN_WORKERS": "2"},
        acr_instance_id=acr_instance_id,
    )
    ensure_http_trigger(fc_client, "manhuaju-api")

    # Worker function
    worker_arn = ensure_function(
        fc_client, name="manhuaju-worker", image=full_image,
        command=["python", "-m", "scripts.run_worker_once"],
        port=None, cpu=2.0, memory_mb=4096, timeout_s=1800,
        concurrency=1,
        envs={**common_envs, "MANHUAJU_BURST_JOBS": "1", "MANHUAJU_BURST_BUDGET_S": "1500"},
        acr_instance_id=acr_instance_id,
    )
    ensure_timer_trigger(fc_client, "manhuaju-worker", cron="@every 1m")

    api_endpoint = get_function_endpoint(fc_client, "manhuaju-api")

    return {
        "api_arn": api_arn,
        "worker_arn": worker_arn,
        "api_endpoint": api_endpoint,
    }


# --------------------------------------------------------------------------- #
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--step", choices=["all", "credentials", "functions"], default="all")
    p.add_argument("--region", default=os.environ.get("ALIBABA_CLOUD_REGION", "cn-hangzhou"))
    p.add_argument("--acr-instance", default=os.environ.get("ACR_INSTANCE_ID"))
    p.add_argument("--namespace", default=os.environ.get("ACR_NAMESPACE_NAME", "manhuaju"))
    p.add_argument("--repo", default=os.environ.get("ACR_REPO_NAME", "manhuaju-autopilot"))
    p.add_argument("--image-tag", default=os.environ.get("IMAGE_TAG", "latest"))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    args.region = (args.region or "cn-hangzhou").strip()
    args.namespace = (args.namespace or "manhuaju").strip()
    args.repo = (args.repo or "manhuaju-autopilot").strip()
    args.image_tag = (args.image_tag or "latest").strip()
    if args.acr_instance:
        args.acr_instance = args.acr_instance.strip()

    root = Path(__file__).resolve().parents[2]
    env = load_env(root / ".env")

    ak = (env.get("ALIBABA_CLOUD_ACCESS_KEY_ID") or os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID") or "").strip()
    sk = (env.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or "").strip()
    if not ak or not sk:
        print("X 缺 ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET", file=sys.stderr)
        print("  请到 https://ram.console.aliyun.com/manage/ak 创建 AccessKey, 然后填到 .env", file=sys.stderr)
        return 2

    print("=" * 60)
    print("阿里云 FC 3.0 一键上线")
    print(f"  region    : {args.region}")
    print(f"  namespace : {args.namespace}")
    print(f"  repo      : {args.repo}")
    print(f"  image tag : {args.image_tag}")
    print("=" * 60)

    result: dict[str, Any] = {"step": args.step, "region": args.region}

    if args.step in ("all", "credentials"):
        cred = credentials_step(env, args.region, args.namespace, args.repo, args.acr_instance)
        result.update(cred)

    if args.step in ("all", "functions"):
        image_prefix = result.get("image_prefix") or f"registry.{args.region}.aliyuncs.com/{args.namespace}/{args.repo}"
        full_image = f"{image_prefix}:{args.image_tag}"
        result["full_image"] = full_image
        acr_iid = result.get("instance_id") or os.environ.get("ACR_INSTANCE_ID", "")
        fn = functions_step(env, args.region, full_image, acr_iid)
        result.update(fn)

    if args.json:
        print("===JSON_RESULT===")
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("\nDone:")
        for k, v in result.items():
            if k == "password" and v:
                v = f"({len(v)} chars, hidden)"
            print(f"  {k} = {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
