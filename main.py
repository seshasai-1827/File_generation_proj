import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import OrderedDict
from datetime import datetime
import csv
import copy
import os

class CommonAttributes():
    def __init__(self):
        self.dist_name_base = None
        self.id_base = None

def make_name(dist,ctx):
    global dist_name_base
    if not dist:
        return None
    parts = dist.split('/', 2)
    if len(parts) != 3 or parts[-1] in ("INTEGRATE-1", "Device-1"):
        return None
    if ctx.dist_name_base is None:
        ctx.dist_name_base = parts[0] + "/" + parts[1]
    return parts[-1]

def simplify_xml(root, ns,ctx):
    data = OrderedDict()
    for mo in root.iterfind(".//ns:managedObject", ns):
        cls = mo.attrib.get("class")
        leaf = make_name(mo.attrib.get("distName"),ctx)
        if not cls or not leaf:
            continue
        entry = OrderedDict()
        entry['_class'] = cls
        #entry['_distName'] = mo.attrib.get("distName")
        #entry['_version'] = mo.attrib.get("version", "UNKNOWN")
        #entry['_id'] = mo.attrib.get("id", "10400")
        entry['_operation'] = mo.attrib.get("operation", "create")
        if ctx.id_base == None:
            ctx.id_base =  mo.attrib.get("id", "10400")       
        for p in mo.findall("ns:p", ns):
            if p.text is not None:
                entry[p.attrib["name"]] = p.text
        data.setdefault(cls, OrderedDict())[leaf] = entry
    return data

def count_total_mos(d):
    return sum(len(inner) for inner in d.values())

def merge_dicts(base, skeletal):
    new_objs, carried_objs = [], []
    final_dict = copy.deepcopy(skeletal)
    for cls in skeletal:
        if cls in base:
            for dist in skeletal[cls]:
                if dist not in base[cls]:
                    new_objs.append((cls, dist))
                    if base[cls]:
                        sample = next(iter(base[cls].values()))
                        #final_dict[cls][dist]['_id'] = sample.get('_id', '10400')
                        #final_dict[cls][dist]['_distName'] = f"{dist_name_base}/{dist}"
                else:
                    for p in skeletal[cls][dist]:
                        if p.startswith('_'):
                            continue
                        if p in base[cls][dist]:
                            final_dict[cls][dist][p] = base[cls][dist][p]
        else:
            for dist in skeletal[cls]:
                new_objs.append((cls, dist))
                if base:
                    for base_class in base:
                        if base[base_class]:
                            sample = next(iter(base[base_class].values()))
                            #final_dict[cls][dist]['_id'] = sample.get('_id', '10400')
                            #final_dict[cls][dist]['_distName'] = f"{dist_name_base}/{dist}"
                            break
    for cls in base:
        if cls not in skeletal:
            continue
        for dist in base[cls]:
            if dist not in skeletal[cls]:
                carried_objs.append((cls, dist))
                final_dict[cls][dist] = base[cls][dist]
    return final_dict, new_objs, carried_objs

def find_deprecated(base, final_):
    depr = []
    for cls, inner in base.items():
        for dist in inner:
            if cls not in final_ or dist not in final_[cls]:
                depr.append((cls, dist))
    return depr

def build_full_xml(data_dict,ctx, out_name="AIOSC_Merged"):
    dist_name_base = ctx.dist_name_base
    id_base = ctx.id_base
    vers = input("Enter Version String (e.g., AIOSC25.0_DROP2, default: custom): ").strip() or "custom"
    NS_URI = "raml21.xsd"
    ET.register_namespace('', NS_URI)
    root = ET.Element("raml", {'version': '2.1', 'xmlns': NS_URI})
    cmD = ET.SubElement(root, "cmData", {'type': 'plan', 'scope': 'all'})

    def hdr(attrs, param_dict):
        mo = ET.SubElement(cmD, "managedObject", attrs)
        for n, v in param_dict.items():
            ET.SubElement(mo, "p", {'name': n}).text = v

    hdr({
        'class': "com.nokia.aiosc:AIOSC", 'version': vers,
        'distName': dist_name_base, 'operation': "create"
    }, {
        "name": "PLMN-PLMN/AIOSC-6000039",
        "AutoConnHWID": "LBNKIASRC243920029",
        "$maintenanceRegionId": "PNP",
        "$maintenanceRegionCId": "1",
        "SparaPara2_CP": "1",
        "SparePara1_CP": "1",
    })

    hdr({
        'class': "com.nokia.integrate:INTEGRATE", 'version': vers,
        'distName': dist_name_base + "/INTEGRATE-1",
        'id': id_base, 'operation': "create"
    }, {
        "plannedSWReleaseVersion": vers,
        "systemReleaseVersion": vers[:6],
        "ipVersion": "0",
    })

    hdr({
        'class': "com.nokia.aiosc:Device", 'version': vers,
        'distName': dist_name_base+ "/Device-1",'id': id_base,
        'operation': "create"
    }, {"UserLabel": "AIOSC"})

    skip_hdr_classes = {
        "com.nokia.aiosc:AIOSC",
        "com.nokia.integrate:INTEGRATE",
        "com.nokia.aiosc:Device",
    }

    for cls, inner in data_dict.items():
        if cls in skip_hdr_classes:
            continue
        for leaf, entry in inner.items():
            tag = ET.SubElement(cmD, "managedObject", {
                'class': entry.get('_class', cls),
                'version': vers,
                'distName': dist_name_base +"/" + leaf,
                'id': id_base,
                'operation': entry.get('_operation', 'create')
            })
            for pname, pval in entry.items():
                if pname.startswith('_'):
                    continue
                ET.SubElement(tag, "p", {'name': pname}).text = pval

    return ET.ElementTree(root)

def write_xml(tree, name="AIOSC_Merged"):
    try:
        txt = minidom.parseString(ET.tostring(tree.getroot(), "utf-8"))\
                     .toprettyxml(indent="    ")
        with open(name + ".xml", "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\u2713 Successfully wrote {name}.xml")
    except Exception as e:
        print(f"Error writing XML file '{name}.xml': {e}")

def csv_report(base, final_, new, carried, depr, name="AIOSC_report.csv"):
    new_set, carried_set, depr_set = map(set, (new, carried, depr))
    total_base = count_total_mos(base)
    total_final = count_total_mos(final_)
    total_new = len(new_set)
    total_carried = len(carried_set)
    total_deprecated = len(depr_set)
    total_common = total_final - total_new - total_carried

    try:
        with open(name, "w", newline='', encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["AIOSC Merge Report"])
            w.writerow(["Generated", datetime.now().isoformat(timespec='seconds')])
            w.writerow([])
            w.writerow(["Metric", "Count"])
            w.writerow(["Objects in BASE (Original)", total_base])
            w.writerow(["Objects in FINAL (Merged)", total_final])
            w.writerow(["NEW (from Skeletal)", total_new])
            w.writerow(["CARRIED (from Base)", total_carried])
            w.writerow(["COMMON (shared & modified)", total_common])
            w.writerow(["DEPRECATED (removed from Base)", total_deprecated])
            w.writerow([])
            w.writerow(["Class", "DistName", "Status"])

            def get_status(cls, dist):
                if (cls, dist) in new_set:
                    return "NEW"
                if (cls, dist) in carried_set:
                    return "CARRIED"
                return "COMMON"

            for cls, inner in sorted(final_.items()):
                for dist in sorted(inner):
                    w.writerow([cls, dist, get_status(cls, dist)])

            for cls, dist in sorted(depr_set):
                w.writerow([cls, dist, "DEPRECATED"])
        print(f"\u2713 Successfully wrote {name}")
    except Exception as e:
        print(f"Error writing CSV report '{name}': {e}")

def log_param_changes(base, skeletal, log_file="param_changes_2025.log"):
    added, removed = [], []

    for cls in skeletal:
        for dist in skeletal[cls]:
            skeletal_entry = skeletal[cls][dist]
            skeletal_keys = {k for k in skeletal_entry if not k.startswith("_")}

            base_entry = base.get(cls, {}).get(dist)
            base_keys = {k for k in base_entry if not k.startswith("_")} if base_entry else set()

            new_params = skeletal_keys - base_keys
            old_params = base_keys - skeletal_keys

            for p in new_params:
                added.append((cls, dist, p))

            for p in old_params:
                removed.append((cls, dist, p))

    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("Parameter Changes Between 2024 and 2025\n")
            f.write("========================================\n\n")

            f.write("✅ New Parameters in 2025:\n")
            for cls, dist, p in added:
                f.write(f"[NEW] {cls} :: {dist} -> {p}\n")

            f.write("\n❌ Dropped Parameters from 2024:\n")
            for cls, dist, p in removed:
                f.write(f"[REMOVED] {cls} :: {dist} -> {p}\n")

        print(f"✓ Logged parameter changes to {log_file}")
    except Exception as e:
        print(f"Error writing parameter change log: {e}")

if __name__ == "__main__":
    ns = {'ns': 'raml21.xsd'}
    base_file = input("Enter the path to the BASE XML file: ").strip()
    skeletal_file = input("Enter the path to the SKELETAL XML file: ").strip()
    
    base_root = ET.parse(base_file).getroot()
    skeletal_root = ET.parse(skeletal_file).getroot()

    common_attr = CommonAttributes()
    comp_base = simplify_xml(base_root, ns,common_attr)
    comp_skeletal = simplify_xml(skeletal_root, ns,common_attr)

    final_dict, new_objs, carried_objs = merge_dicts(comp_base, comp_skeletal)
    deprecated = find_deprecated(comp_base, final_dict)

    print("\n--- Merge Summary ---")
    print("BASE      :", count_total_mos(comp_base))
    print("SKELETAL  :", count_total_mos(comp_skeletal))
    print("FINAL     :", count_total_mos(final_dict))
    print("NEW       :", len(new_objs))
    print("CARRIED   :", len(carried_objs))
    print("DEPRECATED:", len(deprecated))
    print("---------------------\n")

    log_param_changes(comp_base, comp_skeletal)

    out_name = input("Enter the output file name (default: AIOSC_Merged): ").strip() or "AIOSC_Merged"
    tree = build_full_xml(final_dict, common_attr,out_name)
    write_xml(tree, out_name)
    csv_report(comp_base, final_dict, new_objs, carried_objs, deprecated)
