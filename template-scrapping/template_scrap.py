import requests
import json
import os
import re

ZABBIX_URL = 'URL'
AUTH_TOKEN = 'API'
EXPORT_DIR = 'zabbix_json_data'

def sanitize_filename(name):

    return re.sub(r'[\\/*?:"<>|]', "_", name)

def main():
    print(f"Connecting to Zabbix API at: {ZABBIX_URL}")

    # 1. Create the output folder
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    # 2. Get all templates
    get_templates_payload = {
        "jsonrpc": "2.0",
        "method": "template.get",
        "params": {
            "output": ["templateid", "name", "description"]
        },
        "auth": AUTH_TOKEN,
        "id": 1
    }

    try:
        response = requests.post(ZABBIX_URL, json=get_templates_payload).json()
    except requests.exceptions.RequestException as e:
        print(f"[-] Failed to connect: {e}")
        return

    if 'error' in response:
        print(f"[-] API Error: {response['error']['data']}")
        return

    templates = response.get('result', [])
    print(f"Found {len(templates)} templates. Starting JSON extraction...\n")

    success_count = 0
    total_items_scraped = 0

    # 3. Loop through each template, get its items, and save to JSON
    for t in templates:
        t_id = t['templateid']
        t_name = t['name']
        t_desc = t.get('description', '')

        # Fetch items for this specific template
        get_items_payload = {
            "jsonrpc": "2.0",
            "method": "item.get",
            "params": {
                "output": ["itemid", "name", "key_", "delay", "type", "value_type"],
                "templateids": t_id
            },
            "auth": AUTH_TOKEN,
            "id": 2
        }

        try:
            items_response = requests.post(ZABBIX_URL, json=get_items_payload).json()
            items = items_response.get('result', [])

            # 4. Build the JSON structure
            template_data = {
                "template_info": {
                    "id": t_id,
                    "name": t_name,
                    "description": t_desc,
                    "total_items": len(items)
                },
                "items": items
            }

            # 5. Save to a separate JSON file
            safe_name = sanitize_filename(t_name)
            filename = os.path.join(EXPORT_DIR, f"{safe_name}.json")

            with open(filename, 'w', encoding='utf-8') as json_file:
                # indent=4 makes the JSON pretty and human-readable!
                json.dump(template_data, json_file, indent=4, ensure_ascii=False)

            print(f"[+] Saved: {filename} ({len(items)} items)")
            success_count += 1
            total_items_scraped += len(items)

        except Exception as e:
            print(f"[-] Error processing '{t_name}': {e}")

    print(f"\nDone! Scraped {total_items_scraped} items across {success_count} templates.")
    print(f"Check the '{EXPORT_DIR}' folder for your JSON files.")

if __name__ == "__main__":
    main()
