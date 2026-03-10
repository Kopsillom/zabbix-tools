import math
import sys
from zabbix_utils import ZabbixAPI

# --- CONFIGURATION ---
ZBX_URL = "x.x.x.x"
ZBX_TOKEN = "xxxxxx"

ICON_MAP = {
    "switch": "154", "server": "149", "database": "191", "firewall": "28", "default": "3"
}

zapi = ZabbixAPI(url=ZBX_URL, token=ZBX_TOKEN)

def get_tag(tags, name):
    return next((t['value'] for t in tags if t['tag'] == name), None)

# --- DYNAMIC MAP NAME SELECTION ---
print("\n=== Zabbix Map Generator ===")
custom_map_name = input("Enter map name [Default: Zabbix Map Tree]: ").strip()
MAP_NAME = custom_map_name if custom_map_name else "Zabbix Map Tree"

# 1. Fetch Hosts
try:
    hosts = zapi.host.get(output=["hostid", "host"], selectTags="extend")
    host_lookup = {h['host']: h for h in hosts}
except Exception as e:
    print(f"Connection Error: {e}")
    sys.exit()

# 2. Build Relationship Tree
children = {}
roots = []
for h in hosts:
    parent = get_tag(h['tags'], "am.link.connect_to")
    if parent and parent in host_lookup:
        children.setdefault(parent, []).append(h['host'])
    else:
        roots.append(h['host'])

# --- INTERACTIVE SELECTION ---
print("\n--- Available Root Hosts ---")
sorted_roots = sorted(roots)
for i, root in enumerate(sorted_roots, 1):
    print(f"{i}. {root}")
print(f"{len(roots) + 1}. [MAP EVERYTHING]")
print("0. [CANCEL AND EXIT]")

choice = input("\nSelect Core(s) to map (1  /  1,2  /  all): ").strip().lower()

if choice in ['0', 'q', 'exit', 'quit']:
    print("Operation cancelled.")
    sys.exit()

selected_roots = []
if choice == 'all' or choice == str(len(roots) + 1):
    selected_roots = sorted_roots
else:
    try:
        indices = [int(x.strip()) - 1 for x in choice.split(',')]
        selected_roots = [sorted_roots[i] for i in indices]
    except Exception:
        print("Invalid selection. Exiting.")
        sys.exit()

# 3. POSITION CALCULATION (Hierarchical Logic)
coords = {}
X_SPACING = 200
Y_SPACING = 200

def calculate_subtree_width(hostname):
    kids = children.get(hostname, [])
    if not kids:
        return X_SPACING
    return sum(calculate_subtree_width(child) for child in kids)

def assign_pos(hostname, x_start, depth):
    y = (depth + 1) * Y_SPACING
    kids = children.get(hostname, [])
    subtree_width = calculate_subtree_width(hostname)
    x = x_start + (subtree_width / 2)
    coords[hostname] = (int(x), int(y))
    current_x = x_start
    for child in sorted(kids):
        assign_pos(child, current_x, depth + 1)
        current_x += calculate_subtree_width(child)

current_root_x = 100
for r in selected_roots:
    assign_pos(r, current_root_x, 0)
    current_root_x += calculate_subtree_width(r) + 200

# 4. Create Map Elements
map_elements = []
temp_id_map = {}
final_host_list = list(coords.keys())

for idx, hostname in enumerate(final_host_list, 1):
    h = host_lookup[hostname]
    sid = str(idx)
    temp_id_map[hostname] = sid
    h_type = get_tag(h['tags'], "am.host.type")
    icon_id = ICON_MAP.get(h_type, ICON_MAP["default"])
    x, y = coords[hostname]

    map_elements.append({
        "selementid": sid,
        "elementtype": 0,
        "elements": [{"hostid": h['hostid']}],
        "iconid_off": icon_id,
        "label": "{HOST.NAME}\n{HOST.IP}",
        "x": x, "y": y
    })

# 5. Create Links
map_links = []
for hostname in final_host_list:
    parent = get_tag(host_lookup[hostname]['tags'], "am.link.connect_to")
    if parent in temp_id_map:
        map_links.append({
            "selementid1": temp_id_map[hostname],
            "selementid2": temp_id_map[parent],
            "color": "00FF00", "drawtype": 0
        })

# 6. Update Zabbix Map
try:
    existing = zapi.map.get(filter={"name": MAP_NAME})
    if existing:
        print(f"Map '{MAP_NAME}' already exists. Recreating...")
        zapi.map.delete([existing[0]['sysmapid']])

    zapi.map.create(
        name=MAP_NAME,
        width=max(c[0] for c in coords.values()) + 400,
        height=max(c[1] for c in coords.values()) + 400,
        selements=map_elements,
        links=map_links
    )
    print(f"\n[+]Map '{MAP_NAME}' created with {len(final_host_list)} hosts.")
except Exception as e:
    print(f"[-] Error creating map: {e}")

