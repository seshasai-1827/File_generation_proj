import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import OrderedDict
from datetime import datetime
import csv
import copy
import os
import sys

class CommonAttributes():
    def __init__(self):
        self.dist_name_base = None
        self.id_base = None

def make_name(dist, ctx):
    if not dist:
        return None
    parts = dist.split('/', 2)
    if len(parts) != 3 or parts[-1] in ("INTEGRATE-1", "Device-1"):
        return None
    if ctx.dist_name_base is None:
        ctx.dist_name_base = parts[0] + "/" + parts[1]
    return parts[-1]

def simplify_xml(root, ns, ctx):
    data = OrderedDict()
    for mo in root.iterfind(".//ns:managedObject", ns):
        cls = mo.attrib.get("class")
        leaf = make_name(mo.attrib.get("distName"), ctx)
        if not cls or not leaf:
            continue
        entry = OrderedDict()
        entry['_class'] = cls
        entry['_operation'] = mo.attrib.get("operation", "create")
        if ctx.id_base is None:
            ctx.id_base = mo.attrib.get("id", "10400")
        for p in mo.findall("ns:p", ns):
            if p.text is not None:
                entry[p.attrib["name"]] = p.text
        data.setdefault(cls, OrderedDict())[leaf] = entry
    return data

def count_total_mos(d):
    return sum(len(inner) for inner in d.values())

def merge_dicts(base, skeletal, alarm_list):
    common_objs, carried_objs = [], []
    final_dict = copy.deepcopy(skeletal)
    for cls in skeletal:
        if cls in base:
            for dist in skeletal[cls]:
                if dist not in base[cls]:
                    pass
                else:
                    common_objs.append((cls,dist))
                    for p in skeletal[cls][dist]:
                        if p.startswith('_'):
                            continue
                        if p in base[cls][dist]:
                            final_dict[cls][dist][p] = base[cls][dist][p]
        
    for cls in base:
        if cls not in skeletal:
            pass
        else:
            for dist in base[cls]:
                if dist not in skeletal[cls]:
                    carried_objs.append((cls, dist))
                    final_dict[cls][dist] = base[cls][dist]
    if alarm_list:
        final_dict["com.nokia.aiosc:SupportedAlarm"] = alarm_list
    return final_dict, common_objs, carried_objs

def find_diff(base, final_):
    depr,new = [],[]
    for cls, inner in base.items():
        for dist in inner:
            if cls not in final_:
                depr.append((cls, dist))
            else:
                if dist not in final_[cls]:
                    depr.append((cls, dist))
                     
    for cls, inner in final_.items():
        for dist in inner:
            if cls not in base:
                new.append((cls, dist))
            else:
                if dist not in base[cls]:
                    new.append((cls, dist))
    return new,depr

def build_full_xml(data_dict, ctx, out_name="AIOSC_Merged"):
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
        "name": dist_name_base,
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
        'distName': dist_name_base + "/Device-1", 'id': id_base,
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
                'distName': dist_name_base + "/" + leaf,
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
        txt = minidom.parseString(ET.tostring(tree.getroot(), "utf-8")).toprettyxml(indent="  ")
        with open(name + ".xml", "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\u2713 Successfully wrote {name}.xml")
    except Exception as e:
        print(f"Error writing XML file '{name}.xml': {e}")

def csv_report(base, final_, new, carried, depr, common, name="AIOSC_report.csv"):
    new_set, carried_set, depr_set, common_set = map(set, (new, carried, depr, common))
    total_base = count_total_mos(base)
    total_final = count_total_mos(final_)
    total_new = len(new_set)
    total_carried = len(carried_set)
    total_deprecated = len(depr_set)
    total_common = len(common_set)

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
                if (cls, dist) in common_set:
                    return "COMMON"
                return "UNKNOWN"

            for cls, inner in sorted(final_.items()):
                for dist in sorted(inner):
                    w.writerow([cls, dist, get_status(cls, dist)])

            for cls, dist in sorted(depr_set):
                w.writerow([cls, dist, "DEPRECATED"])
        print(f"\u2713 Successfully wrote {name}")
    except Exception as e:
        print(f"Error writing CSV report '{name}': {e}")

def log_param_changes(base_dict, final_dict, filename="param_changes.log"):
    added, removed, changed = [], [], []
    new_class_params, deprecated_class_params = [], []

    for cls in final_dict:
        if cls not in base_dict:
            # Entirely new class
            for dist in final_dict[cls]:
                for p in final_dict[cls][dist]:
                    if not p.startswith('_'):
                        val = final_dict[cls][dist][p]
                        new_class_params.append((cls, dist, p, val))
                        added.append((cls, dist, p, val))  # ✅ Also consider as added
            continue

        for dist in final_dict[cls]:
            if dist not in base_dict[cls]:
                # New distribution in existing class
                for p in final_dict[cls][dist]:
                    if not p.startswith('_'):
                        val = final_dict[cls][dist][p]
                        new_class_params.append((cls, dist, p, val))
                        added.append((cls, dist, p, val))  # ✅ Also consider as added
                continue

            # Compare parameters in existing class and distribution
            skeletal_entry = final_dict[cls][dist]
            base_entry = base_dict[cls][dist]
            skeletal_keys = set(k for k in skeletal_entry if not k.startswith('_'))
            base_keys = set(k for k in base_entry if not k.startswith('_'))

            for p in skeletal_keys - base_keys:
                added.append((cls, dist, p, skeletal_entry[p]))
            for p in base_keys - skeletal_keys:
                removed.append((cls, dist, p, base_entry[p]))
            for p in skeletal_keys & base_keys:
                if skeletal_entry[p] != base_entry[p]:
                    changed.append((cls, dist, p, base_entry[p], skeletal_entry[p]))

    # Now check for deprecated classes/distributions
    for cls in base_dict:
        if cls not in final_dict:
            for dist in base_dict[cls]:
                for p in base_dict[cls][dist]:
                    if not p.startswith('_'):
                        removed.append((cls, dist, p, base_dict[cls][dist][p]))
        else:
            for dist in base_dict[cls]:
                if dist not in final_dict[cls]:
                    for p in base_dict[cls][dist]:
                        if not p.startswith('_'):
                            removed.append((cls, dist, p, base_dict[cls][dist][p]))

    # Write to file
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("📘 Parameter Change Log\n")
            f.write(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n\n")

            f.write("✅ New Parameters (in existing or new classes/distributions):\n")
            for item in added:
                cls, dist, p, val = item
                f.write(f"[ADDED]     {cls} :: {dist} -> {p} = {val}\n")

            f.write("\n❌ Removed Parameters (dropped in 2025):\n")
            for item in removed:
                cls, dist, p, val = item
                f.write(f"[REMOVED]   {cls} :: {dist} -> {p} = {val}\n")

            f.write("\n🔁 Modified Parameters (value changed):\n")
            for item in changed:
                cls, dist, p, old_val, new_val = item
                f.write(f"[MODIFIED]  {cls} :: {dist} -> {p}: '{old_val}' -> '{new_val}'\n")


        print(f"✅ Logged parameter changes to {filename}")
    except Exception as e:
        print(f"❌ Error writing parameter log file '{filename}': {e}")



def readcsv(file_path):
    d = False
    try:
        if file_path and os.path.isfile(file_path) and file_path.endswith(".csv"):
            with open(file_path, newline='') as csvfile:
                reader = csv.reader(csvfile)
                i = 1
                d = {}
                for row in reader:
                    if len(row) < 3:
                        print(f"Warning: Skipping invalid row in CSV: {row}")
                        continue
                    leaf = "Device-1/FaultMgmt-1/SupportedAlarm-" + str(i)
                    d[leaf] = {
                        "_class": "com.nokia.aiosc:SupportedAlarm",
                        "_operation": "create",
                        "FaultIdn": row[0],
                        "MocIdn": row[1],
                        "ReportingMechanism": row[2]
                    }
                    i += 1
        else:
            if file_path:
                print("Warning: CSV file is invalid or not found.")
    except Exception as e:
        print(f"Warning: Failed to read CSV file: {e}")
    return d

if __name__ == "__main__":
    ns = {'ns': 'raml21.xsd'}
    try:
        base_file = input("Enter the path to the BASE XML file: ").strip()
        skeletal_file = input("Enter the path to the SKELETAL XML file: ").strip()
        csv_file = input("Enter the file path for supported alarms(.csv)(default : None): ").strip()

        if not os.path.isfile(base_file):
            print("Error: BASE XML file not found.")
            exit(1)
        if not os.path.isfile(skeletal_file):
            print("Error: SKELETAL XML file not found.")
            exit(1)

        try:
            base_root = ET.parse(base_file).getroot()
        except ET.ParseError:
            print("Error: BASE file is not valid XML.")
            exit(1)

        try:
            skeletal_root = ET.parse(skeletal_file).getroot()
        except ET.ParseError:
            print("Error: SKELETAL file is not valid XML.")
            exit(1)

        common_attr = CommonAttributes()
        comp_base = simplify_xml(base_root, ns, common_attr)
        comp_skeletal = simplify_xml(skeletal_root, ns, common_attr)
        alarm_list = readcsv(csv_file)

        final_dict,common_objs, carried_objs = merge_dicts(comp_base, comp_skeletal, alarm_list)
        new_objs,deprecated = find_diff(comp_base, final_dict)
        

        print("\n--- Merge Summary ---")
        print("BASE      :", count_total_mos(comp_base))
        print("SKELETAL  :", count_total_mos(comp_skeletal))
        print("FINAL     :", count_total_mos(final_dict))
        print("NEW       :", len(new_objs))
        print("CARRIED   :", len(carried_objs))
        print("COMMON    :", len(common_objs))
        print("DEPRECATED:", len(deprecated))
        print("---------------------\n")

        log_param_changes(comp_base,final_dict)

        out_name = input("Enter the output file name (default: AIOSC_Merged): ").strip() or "AIOSC_Merged"
        tree = build_full_xml(final_dict, common_attr, out_name)
        write_xml(tree, out_name)
        csv_report(comp_base, final_dict, new_objs, carried_objs, deprecated, common_objs)

    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)
