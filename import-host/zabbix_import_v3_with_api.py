import requests
import csv
import argparse
import sys

# ---------------- CONFIG ----------------
# /zabbix/api_jsonrpc.php at the end of your URL
ZABBIX_URL = "http://127.0.0.1/zabbix/api_jsonrpc.php"
API_TOKEN = "12fdfde6f685b117a303153896338abcd00ae27a404889e93ddd6970f89d669d"

# Cache to avoid thousands of repetitive API calls
cache = {"groups": {}, "templates": {}}

def api_call(method, params):
    """Standardized wrapper for Zabbix JSON-RPC calls."""
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
        "auth": API_TOKEN
    }
    try:
        response = requests.post(ZABBIX_URL, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        res_json = response.json()

        if "error" in res_json:
            return {"error": res_json["error"].get("data", res_json["error"].get("message"))}
        return {"result": res_json.get("result")}
    except Exception as e:
        return {"error": str(e)}

def get_group_id(name):
    """Checks cache first. If not found, checks Zabbix. If still not found, creates it."""
    name = name.strip()
    if name in cache["groups"]:
        return cache["groups"][name]

    res = api_call("hostgroup.get", {"filter": {"name": name}})

    if res.get("result") and len(res["result"]) > 0:
        # Group exists
        gid = res["result"][0]["groupid"]
    else:
        # Group doesn't exist, create it
        create = api_call("hostgroup.create", {"name": name})
        if "error" in create:
            raise Exception(f"Group creation failed for '{name}': {create['error']}")
        gid = create["result"]["groupids"][0]

    cache["groups"][name] = gid
    return gid

def get_template_id(name):
    """Fetches template ID with local caching."""
    name = name.strip()
    if name in cache["templates"]:
        return cache["templates"][name]

    res = api_call("template.get", {"filter": {"host": name}, "output": ["templateid"]})

    if not res.get("result") or len(res["result"]) == 0:
        raise Exception(f"Template '{name}' not found. Please check Zabbix.")

    tid = res["result"][0]["templateid"]
    cache["templates"][name] = tid
    return tid

def process_host(row):
    hostname = row['hostname']

    # 1. Check if host exists (Update vs Create)
    existing = api_call("host.get", {"filter": {"host": hostname}, "output": ["hostid"]})
    host_id = None
    if existing.get("result") and len(existing["result"]) > 0:
        host_id = existing["result"][0]["hostid"]

    # 2. Resolve Groups (Creates them if they don't exist)
    groups = [{"groupid": get_group_id(g)} for g in row['groups'].split(";") if g.strip()]

    # 3. Resolve Templates
    templates = [{"templateid": get_template_id(t)} for t in row['templates'].split(";") if t.strip()]

    # 4. Parse Tags (Format: Key1=Val1;Key2=Val2)
    tags = []
    if row.get('tags'):
        for pair in row['tags'].split(";"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                tags.append({"tag": k.strip(), "value": v.strip()})

    # 5. Interface logic
    type_map = {"agent": 1, "snmp": 2, "ipmi": 3, "jmx": 4}
    iface_type_str = row.get('interface_type', 'agent').lower()
    iface_type = type_map.get(iface_type_str, 1)

    params = {
        "host": hostname,
        "groups": groups,
        "templates": templates,
        "tags": tags,
        "status": 0,         # 0 = Monitored
        "inventory_mode": 1  # 1 = Automatic
    }

    if host_id:
        params["hostid"] = host_id
        method = "host.update"
    else:
        method = "host.create"
        # Interface is required for creation
        interface = {
            "type": iface_type,
            "main": 1,
            "useip": 1,
            "port": row.get('port', '161' if iface_type == 2 else '10050'),
            "ip": row.get('ip', '127.0.0.1'),
            "dns": ""
        }

        # SNMP details required for SNMP templates
        if iface_type == 2:
            interface["details"] = {
                "version": 2,
                "bulk": 1,
                "community": row.get('snmp_community', 'public')
            }
        params["interfaces"] = [interface]

    # 6. Execute API Call
    res = api_call(method, params)
    if "error" in res:
        print(f"[-] Failed {method}: {hostname} | Error: {res['error']}")
    else:
        action = "Updated" if host_id else "Created"
        print(f"[+] {action}: {hostname}")

def main(csv_file):
    print(f"Connecting to {ZABBIX_URL}...")
    try:
        # utf-8-sig handles BOM characters often added by Excel
        with open(csv_file, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    process_host(row)
                except Exception as e:
                    print(f"[-] Skip {row.get('hostname', 'Unknown')}: {e}")
    except FileNotFoundError:
        print(f"Error: File '{csv_file}' not found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zabbix Host Importer")
    parser.add_argument("--file", required=True, help="Path to your CSV file")
    args = parser.parse_args()
    main(args.file)
