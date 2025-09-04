# Operator.py
import kopf
import kubernetes
import requests
import base64
import time
import logging
# Load in-cluster config (use load_kube_config for local runs)
try:
   kubernetes.config.load_incluster_config()
except:
   kubernetes.config.load_kube_config()
v1 = kubernetes.client.CoreV1Api()
logger = logging.getLogger("abot-operator")
logger.setLevel(logging.INFO)

# -------- Helpers --------
def get_credentials(namespace, secret_name):
   """Read Abot login credentials from a Kubernetes Secret."""
   secret = v1.read_namespaced_secret(secret_name, namespace)
   email = base64.b64decode(secret.data['email']).decode('utf-8')
   password = base64.b64decode(secret.data['password']).decode('utf-8')
   return email, password

def abot_login(endpoint, email, password):
   """Authenticate with Abot and return headers with Bearer token."""
   url = f"{endpoint}/login"
   resp = requests.post(url, json={"email": email, "password": password}, verify=False)
   resp.raise_for_status()
   token = resp.json().get("token")
   return {"Authorization": f"Bearer {token}"}

def abot_config_update(endpoint, headers, filename, testbedFile, sutVarsFile, overrides):
   """Send config update request to Abot."""
   url = f"{endpoint}/update_config_properties"
   if testbedFile != "false":
     payload = {
         "filename": filename,
         "data": {
          "comment": [],
          "uncomment": [],
          "update": {
              "ABOT.TESTBED": testbedFile  
              }
         }
     }
   else:
     payload = {
         "filename": file,
         "data": {
          "comment": [],
          "uncomment": [],
          "update": {
              "ABOT.SUTVARS": sutVarsFile,
              "ABOT.SUTVARS.ORAN": ""
              }
         }
     }
   logger.info(f"Sending config update: {payload}")
   resp = requests.post(url, json=payload, headers=headers, verify=False)
   resp.raise_for_status()
   return resp.json()

def abot_create_and_execute(endpoint, headers, testTag):
   """Create a test suite and execute it."""
   # Create
   create_url = f"{endpoint}/feature_files/execute"
   resp = requests.post(create_url, json={"params": testTag}, headers=headers, verify=False)
   resp.raise_for_status()
   #suite_id = resp.json().get("id")
   # Execute
   #exec_url = f"{endpoint}/api/testsuites/{suite_id}/execute"
   #resp = requests.post(exec_url, headers=headers, verify=False)
   #resp.raise_for_status()
   exec_id = resp.json().get("status")
   return exec_id

def abot_poll_status(endpoint, headers, exec_id, interval, timeout):
   """Poll Abot execution status until completion or timeout."""
   url = f"{endpoint}/execution_status"
   start = time.time()
   while time.time() - start < timeout:
       resp = requests.get(url, headers=headers, verify=False)
       resp.raise_for_status()
       status = resp.json()
       is_executing_value = status["executing"]["executing"][0]["is_executing"]
       if is_executing in ["false"]:
           return status
       time.sleep(interval)
   return {"phase": "Timeout", "message": "Execution exceeded timeout"}

# -------- Operator Handlers --------
@kopf.on.create('abot.capg.io', 'v1', 'abottestsuites')
@kopf.on.update('abot.capg.io', 'v1', 'abottestsuites')
def handle_abot_testsuite(spec, status, namespace, name, patch, logger, **kwargs):
   logger.info(f"Reconciling AbotTestSuite {name} in {namespace}")
   # --- Extract Spec fields ---
   endpoint = spec.get("endpoint")
   auth = spec.get("auth", {})
   suite = spec.get("suite", {})
   execution = spec.get("execution", {})
   polling = spec.get("polling", {})
   results = spec.get("results", {})
   params = suite.get("params", {})
   testTag = params.get("testTag")
   filename = params.get("filename")
   testbedFile = params.get("testbedFile")
   sutVarsFile = params.get("sutVarsFile")
   overrides = params.get("configOverrides", {})
   secret_name = auth.get("secretRef")
   # --- Step 1: Get credentials ---
   try:
       email, password = get_credentials(namespace, secret_name)
   except Exception as e:
       patch.status['suitePhase'] = "Failed"
       patch.status['message'] = f"Credential read error: {e}"
       raise
   # --- Step 2: Authenticate ---
   try:
       headers = abot_login(endpoint, email, password)
       patch.status['suitePhase'] = "Authenticated"
   except Exception as e:
       patch.status['suitePhase'] = "Failed"
       patch.status['message'] = f"Auth error: {e}"
       raise
   # --- Step 3: Config Update ---
   try:
       abot_config_update(endpoint, headers, filename, testbedFile, "false", overrides)
       abot_config_update(endpoint, headers, filename, "false", sutVarsFile, overrides)
       patch.status['suitePhase'] = "ConfigUpdated"
   except Exception as e:
       patch.status['suitePhase'] = "Failed"
       patch.status['message'] = f"Config update error: {e}"
       raise
   # --- Step 4: Create & Execute ---
   if execution.get("trigger", True):
       try:
           exec_id = abot_create_and_execute(endpoint, headers, testTag)
           patch.status['suitePhase'] = "ExecutionStarted"
           patch.status['executionId'] = exec_id
       except Exception as e:
           patch.status['suitePhase'] = "Failed"
           patch.status['message'] = f"Execution start error: {e}"
           raise
       # --- Step 5: Polling ---
       interval = polling.get("intervalSeconds", 10)
       timeout = polling.get("timeoutSeconds", 600)
       status_resp = abot_poll_status(endpoint, headers, exec_id, interval, timeout)
       patch.status['suitePhase'] = status_resp.get("phase", "Unknown")
       patch.status['message'] = status_resp.get("message", "")
       patch.status['resultsURL'] = status_resp.get("resultsURL", "")
   return {"message": "Handled successfully"}
