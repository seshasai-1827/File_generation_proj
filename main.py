import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import OrderedDict
from datetime import datetime
import csv
import copy
import os

def make_name(dist):
    if not dist:
        return None
    parts = dist.split('/', 2)
    if len(parts) != 3 or parts[-1] in ("INTEGRATE-1", "Device-1"):
        return None
    return parts[-1]

def simplify_xml(root, ns):
    data = OrderedDict()
    for mo in root.iterfind(".//ns:managedObject", ns):
        cls = mo.attrib.get("class")
        leaf = make_name(mo.attrib.get("distName"))
        if not cls or not leaf:
            continue
        entry = OrderedDict()
        entry['_class'] = cls
        entry['_distName'] = mo.attrib.get("distName")
        entry['_version'] = mo.attrib.get("version", "UNKNOWN")
        entry['_id'] = mo.attrib.get("id", "10400")
        entry['_operation'] = mo.attrib.get("operation", "create")
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
                else:
                    for p in skeletal[cls][dist]:
                        if p.startswith('_'):
                            continue
                        if p in base[cls][dist]:
                            final_dict[cls][dist][p] = base[cls][dist][p]
        else:
            for dist in skeletal[cls]:
                new_objs.append((cls, dist))

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

def build_full_xml(data_dict, out_name="AIOSC_Merged"):
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
        'distName': "PLMN-PLMN/AIOSC-6000039", 'operation': "create"
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
        'distName': "PLMN-PLMN/AIOSC-6000039/INTEGRATE-1",
        'id': "104000", 'operation': "create"
    }, {
        "plannedSWReleaseVersion": vers,
        "systemReleaseVersion": vers[:6],
        "ipVersion": "0",
    })

    hdr({
        'class': "com.nokia.aiosc:Device", 'version': vers,
        'distName': "PLMN-PLMN/AIOSC-6000039", 'operation': "create"
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
            distname_fixed = f"PLMN-PLMN/AIOSC-6000039/{leaf}" if leaf else entry.get('_distName')
            tag = ET.SubElement(cmD, "managedObject", {
                'class': entry.get('_class', cls),
                'version': vers,
                'distName': distname_fixed,
                'id': "10400",
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
        print(f"✓ Successfully wrote {name}.xml")
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
        print(f"✓ Successfully wrote {name}")
    except Exception as e:
        print(f"Error writing CSV report '{name}': {e}")

if __name__ == "__main__":
    ns = {'ns': 'raml21.xsd'}
    base_file = input("Enter the path to the BASE XML file: ").strip()
    skeletal_file = input("Enter the path to the SKELETAL XML file: ").strip()

    base_root = ET.parse(base_file).getroot()
    skeletal_root = ET.parse(skeletal_file).getroot()

    comp_base = simplify_xml(base_root, ns)
    comp_skeletal = simplify_xml(skeletal_root, ns)

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

    out_name = input("Enter the output file name (default: AIOSC_Merged): ").strip() or "AIOSC_Merged"
    tree = build_full_xml(final_dict, out_name)
    write_xml(tree, out_name)
    csv_report(comp_base, final_dict, new_objs, carried_objs, deprecated)
