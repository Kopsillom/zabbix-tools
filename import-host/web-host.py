from zabbix_utils import ZabbixAPI

# Configuration - Replace with your Zabbix details
ZABBIX_URL = "http://127.0.0.1/zabbix/api_jsonrpc.php"
API_TOKEN = "API"
GROUP_NAME = "web-hosts"

def setup_web_monitoring():
    # Use 'token' instead of user/password
    zapi = ZabbixAPI(url=ZABBIX_URL, token=API_TOKEN)

    try:
        print(f"[+] Connected to Zabbix API using Token")

        target_url = input("Enter the website URL (ex. https://google.com): ").strip()
        host_name = target_url.replace("https://", "").replace("http://", "").rstrip('/')

        # 1. Scan for Host Group
        group = zapi.hostgroup.get(filter={"name": GROUP_NAME})
        if not group:
            group_id = zapi.hostgroup.create(name=GROUP_NAME)["groupids"][0]
            print(f"[+] Created new host group: {GROUP_NAME}")
        else:
            group_id = group[0]["groupid"]
            print(f"[+] Acknowledged existing host group: {GROUP_NAME}")

        # 2. Create the Host
        host = zapi.host.create(
            host=host_name,
            groups=[{"groupid": group_id}],
            interfaces=[{
                "type": 1, "main": 1, "useip": 1, "ip": "127.0.0.1", "dns": "", "port": "10050"
            }]
        )
        host_id = host["hostids"][0]
        print(f"[+] Host '{host_name}' created successfully")

        # 3. Create the Web Scenario
        zapi.httptest.create(
            name=f"Monitor {host_name}",
            hostid=host_id,
            delay="1m",
            retries=3,
            steps=[{
                "name": "Check Homepage",
                "url": target_url,
                "status_codes": "200",
                "no": 1
            }]
        )
        print(f"[+] Web scenario added for {target_url}")

    except Exception as e:
        print(f"[-] Error: {e}")
    # Note: zapi.logout() is not strictly required when using Tokens,
    # but it's safe to keep or remove.

if __name__ == "__main__":
    setup_web_monitoring()

