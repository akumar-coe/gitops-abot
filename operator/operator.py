from __future__ import annotations
import base64, time
import kopf
from kubernetes import client as k8s
from utils.api_client import AbotClient

def _read_secret(ns: str, name: str) -> dict:
    v1 = k8s.CoreV1Api()
    s = v1.read_namespaced_secret(name, ns)
    # decode base64 values in .data
    data = {}
    for k, v in (s.data or {}).items():
        data[k] = base64.b64decode(v).decode()
    # also merge stringData if present via annotations (defensive)
    return data

def _update_status(body, patch, **fields):
    # convenience: write into .status
    patch.status.update(fields)

def _test_passed(status_obj: dict) -> bool:
    # Heuristic: adapt to your actual Abot response fields
    val = (status_obj.get("overallStatus") or status_obj.get("state") or "").lower()
    return val in ("passed", "succeeded", "completed", "complete")

def _test_failed(status_obj: dict) -> bool:
    val = (status_obj.get("overallStatus") or status_obj.get("state") or "").lower()
    return val in ("failed", "error", "terminated")

# ---------------- AbotTestSuite ----------------
@kopf.on.create('abot.capg.io', 'v1', 'abottestsuites')
def create_suite(spec, name, namespace, logger, patch, body, **_):
    """
    Reconcile AbotTestSuite:
      1) login
      2) optional config update
      3) execute each test
      4) poll status until done or timeout
      5) write summary to status (and optional ConfigMap)
    """
    endpoint = spec.get("endpoint")
    auth = spec.get("auth", {})
    secret_name = auth.get("secretRef")
    options = spec.get("options", {}) or {}
    poll_interval = int(options.get("pollIntervalSeconds", 5))
    timeout = int(options.get("timeoutSeconds", 900))
    fetch_details = bool(options.get("fetchDetails", True))

    logger.info(f"endpoint: {endpoint}")
    logger.info(f"secret_name: {secret_name}")
    if not endpoint or not secret_name:
        raise kopf.PermanentError("spec.endpoint and spec.auth.secretRef are required.")

    # mark running
    _update_status(body, patch, suitePhase="Running", message="Logging into Abot…")

    # secrets expected keys: email, password
    creds = _read_secret(namespace, secret_name)
    email = creds.get("email")
    password = creds.get("password")
    if not email or not password:
        raise kopf.PermanentError("Secret must contain keys: email, password.")

    # create client and optionally validate tags
    client = AbotClient(endpoint, email, password)

    if spec.get("discover", {}).get("validateTags"):
        tags = client.get_feature_tags()
        logger.info(f"Available tags: {tags}")

    # optional config update
    cfg = spec.get("config")
    if cfg and cfg.get("filename"):
        client.update_config_properties(
            filename=cfg["filename"],
            update=cfg.get("update"),
            comment=cfg.get("comment"),
            uncomment=cfg.get("uncomment"),
        )
        logger.info("Config properties updated.")

    tests = spec.get("tests") or []
    results = []

    for t in tests:
        tname = t.get("name") or t.get("execute", {}).get("params")
        exec_spec = t.get("execute") or {}
        params = exec_spec.get("params")
        build = exec_spec.get("build", "default-build")
        if not params:
            logger.warning(f"Skipping test {tname}: missing execute.params")
            results.append({"name": tname, "phase": "Failed", "summary": "missing params"})
            continue

        logger.info(f"Executing test: {tname} (params={params}, build={build})")
        _update_status(body, patch, message=f"Executing {tname}…")

        client.execute_feature(params=params, build=build)

        # poll
        deadline = time.time() + timeout
        final = {"name": tname, "phase": "Running"}
        while time.time() < deadline:
            st = client.detail_execution_status() if fetch_details else client.execution_status()
            if _test_passed(st):
                final.update({"phase": "Succeeded", "summary": st})
                logger.info(f"Test {tname} Succeeded")
                break
            if _test_failed(st):
                final.update({"phase": "Failed", "summary": st})
                logger.info(f"Test {tname} Failed")
                break
            time.sleep(poll_interval)
        else:
            final.update({"phase": "Failed", "summary": {"error": "timeout"}})
            logger.info(f"Test {tname} timed out")

        results.append(final)
        # reflect intermediate progress
        _update_status(body, patch, tests=results)

    suite_phase = "Succeeded" if all(r["phase"] == "Succeeded" for r in results) else "Failed"
    _update_status(body, patch, suitePhase=suite_phase, tests=results, message=f"Suite {suite_phase}")

    # Optional: write compact summary to ConfigMap if requested
    cm_name = (spec.get("artifacts") or {}).get("saveSummaryToConfigMap")
    if cm_name:
        v1 = k8s.CoreV1Api()
        payload = {
            "suitePhase": suite_phase,
            "tests": results,
        }
        cm = k8s.V1ConfigMap(
            metadata=k8s.V1ObjectMeta(name=cm_name, namespace=namespace),
            data={"summary.json": __import__("json").dumps(payload)[:1048576]},
        )
        try:
            v1.replace_namespaced_config_map(cm_name, namespace, cm)
        except Exception:
            v1.create_namespaced_config_map(namespace, cm)

