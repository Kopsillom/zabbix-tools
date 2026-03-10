import sys
from zabbix_utils import ZabbixAPI

# --- CONFIGURATION ---
ZBX_URL = "URL"
ZBX_TOKEN = "API"

# Set this to your bandwidth item key (e.g., net.if.in[eth0])
BW_ITEM_KEY = "net.if.in[eth0]"

# Colors for Link Indicators based on trigger severity
DEFAULT_LINK_COLOR = "00FF00" # Green
TRIGGER_COLORS = {
    "2": "FFFF00",  # Warning -> Yellow
    "3": "FF8000",  # Average -> Orange
    "4": "FF0000",  # High -> Red
    "5": "990000"   # Disaster -> Dark Red
}

ICON_MAP = {
    "switch": "154", "server": "149", "database": "191", "firewall": "28", "default": "3"
}

# 1. Initialize Zabbix API
zapi = ZabbixAPI(url=ZBX_URL, token=ZBX_TOKEN)

def get_tag(tags, name):
    return next((t['value'] for t in tags if t['tag'] == name), None)

# --- DYNAMIC MAP NAME SELECTION ---
print("\n=== Zabbix Map Generator with Bandwidth Links ===")
custom_map_name = input("Enter map name [Default: Network Automap]: ").strip()
MAP_NAME = custom_map_name if custom_map_name else "Network Automap"

# 2. Fetch Hosts with Triggers
try:
    # Correct zabbix-utils syntax: zapi.host.get(...)
    hosts = zapi.host.get(
        output=["hostid", "host"], 
        selectTags="extend",
        selectTriggers=["triggerid", "description", "priority"]
    )
    host_lookup = {h['host']: h for h in hosts}
except Exception as e:
    print(f"Connection Error: {e}")
    sys.exit()

# 3. Build Relationship Tree
children = {}
roots = []
for h in hosts:
    parent = get_tag(h['tags'], "am.link.connect_to")
    if parent and parent in host_lookup:
        children.setdefault(parent, []).append(h['host'])
    else:
        roots.append(h['host'])

# --- INTERACTIVE SELECTION ---
sorted_roots = sorted(roots)
for i, root in enumerate(sorted_roots, 1):
    print(f"{i}. {root}")
print(f"{len(roots) + 1}. [MAP EVERYTHING]")

choice = input("\nSelect Core(s) to map (e.g., 1 or 1,2 or all): ").strip().lower()
if choice in ['0', 'q', 'exit']: sys.exit()

if choice == str(len(roots) + 1) or choice == 'all':
    selected_roots = sorted_roots
else:
    indices = [int(x.strip()) - 1 for x in choice.split(',')]
    selected_roots = [sorted_roots[i] for i in indices]

# 4. POSITION CALCULATION
coords = {}
X_SPACING, Y_SPACING = 250, 200

def calculate_subtree_width(hostname):
    kids = children.get(hostname, [])
    return sum(calculate_subtree_width(k) for k in kids) if kids else X_SPACING

def assign_pos(hostname, x_start, depth):
    subtree_width = calculate_subtree_width(hostname)
    coords[hostname] = (int(x_start + subtree_width/2), (depth + 1) * Y_SPACING)
    curr_x = x_start
    for child in sorted(children.get(hostname, [])):
        assign_pos(child, curr_x, depth + 1)
        curr_x += calculate_subtree_width(child)

current_root_x = 100
for r in selected_roots:
    assign_pos(r, current_root_x, 0)
    current_root_x += calculate_subtree_width(r) + 200

# 5. CREATE MAP ELEMENTS
map_elements, temp_id_map = [], {}
final_host_list = list(coords.keys())

for idx, hostname in enumerate(final_host_list, 1):
    h = host_lookup[hostname]
    sid = str(idx)
    temp_id_map[hostname] = sid
    x, y = coords[hostname]
    h_type = get_tag(h['tags'], "am.host.type")
    icon_id = ICON_MAP.get(h_type, ICON_MAP["default"])

    map_elements.append({
        "selementid": sid, 
        "elementtype": 0, 
        "elements": [{"hostid": h['hostid']}],
        "iconid_off": icon_id, 
        "label": "{HOST.NAME}\n{HOST.IP}", 
        "x": x, "y": y
    })

# 6. CREATE LINKS WITH BANDWIDTH AND INDICATORS
map_links = []
for hostname in final_host_list:
    host_data = host_lookup[hostname]
    parent = get_tag(host_data['tags'], "am.link.connect_to")
    
    if parent in temp_id_map:
        # Bandwidth Macro for live label on the map
        bw_label = f"BW: {{?last(/{hostname}/{BW_ITEM_KEY})}}"
        
        # Link Indicators (Dynamic Color based on Trigger status)
        link_triggers = []
        for t in host_data.get('triggers', []):
            desc = t['description'].lower()
            if any(word in desc for word in ["bandwidth", "utilization", "traffic"]):
                link_triggers.append({
                    "triggerid": t['triggerid'],
                    "color": TRIGGER_COLORS.get(t['priority'], "FF0000"),
                    "drawtype": 2 # Bold line when active
                })

        map_links.append({
            "selementid1": temp_id_map[hostname],
            "selementid2": temp_id_map[parent],
            "color": DEFAULT_LINK_COLOR,
            "label": bw_label,
            "linktriggers": link_triggers
        })

# 7. UPDATE ZABBIX MAP
try:
    existing = zapi.map.get(filter={"name": MAP_NAME})
    if existing:
        print(f"Map '{MAP_NAME}' exists. Recreating...")
        zapi.map.delete([existing[0]['sysmapid']])

    zapi.map.create(
        name=MAP_NAME,
        width=max(c[0] for c in coords.values()) + 400,
        height=max(c[1] for c in coords.values()) + 400,
        selements=map_elements,
        links=map_links
    )
    print(f"\n[+] Success! Created '{MAP_NAME}' with {len(final_host_list)} hosts.")
except Exception as e:
    print(f"[-] API Error: {e}")

