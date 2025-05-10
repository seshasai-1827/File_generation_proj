import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import OrderedDict

PARAM_RENAME_MAP = {
    "GPS-1": {
        "GpsAttemptFixed": "GpsAttemptsTotal",
        "UserLabel": "Label"
    },
    "DeviceInfo-1": {
        "SerialNumber": "DeviceSerial"
    }
}

def make_name(st):
    l = st.split('/', 3)
    return l[-1] if len(l) == 4 else False

def simplify_xml(root, ns):
    base = OrderedDict()
    base_list = root.findall(".//ns:managedObject", ns)
    for element in base_list:
        distName = element.attrib['distName']
        key = make_name(distName)
        if not key:
            continue
        base[key] = OrderedDict()
        base[key]['_class'] = element.attrib.get('class', 'UNKNOWN')
        base[key]['_distName'] = distName
        base[key]['_version'] = element.attrib.get('version', 'UNKNOWN')
        base[key]['_id'] = element.attrib.get('id', '10400')
        base[key]['_operation'] = element.attrib.get('operation', 'create')
        for parameters in element.findall("ns:p", ns):
            if parameters.text:
                base[key][parameters.attrib['name']] = parameters.text
    return base

def update_dictionary(comp_base, comp_update):
    changes = []
    for key in comp_update:
        mo_map = PARAM_RENAME_MAP.get(key, {})
        for param in list(comp_update[key]):
            if param.startswith('_'):
                continue
            if key in comp_base and param in comp_base[key]:
                old_value = comp_update[key][param]
                new_value = comp_base[key][param]
                if old_value != new_value:
                    comp_update[key][param] = new_value
                    changes.append(f"[{key}] {param} updated (direct match): '{old_value}' → '{new_value}'")
                continue
            for old_name, new_name in mo_map.items():
                if param == new_name and old_name in comp_base.get(key, {}):
                    old_value = comp_update[key][param]
                    new_value = comp_base[key][old_name]
                    if old_value != new_value:
                        comp_update[key][param] = new_value
                        changes.append(f"[{key}] {old_name} → {new_name} updated: '{old_value}' → '{new_value}'")
                    break
    with open("changes_log.txt", "w", encoding="utf-8") as f:
        for line in changes:
            f.write(line + "\n")
    print("Changes saved in 'changes_log.txt'")
    return comp_update

def build_full_xml(data_dict):
    NS_URI = "raml21.xsd"
    ET.register_namespace('', NS_URI)
    root = ET.Element("raml", {
        'version': '2.1',
        'xmlns': NS_URI
    })
    cmData = ET.SubElement(root, "cmData", {
        'type': 'plan',
        'scope': 'all',
        'name': 'AIOSC-1-PnP-ProfileD-Basic-Integration-Planfile.xml'
    })
    for key, params in data_dict.items():
        class_attr = params.pop('_class', 'UNKNOWN')
        dist_attr = params.pop('_distName', f"UNSPECIFIED/{key}")
        version = params.pop('_version', 'UNKNOWN')
        mo_id = params.pop('_id', '10400')
        operation = params.pop('_operation', 'create')
        mo = ET.SubElement(cmData, "managedObject", {
            'class': class_attr,
            'version': version,
            'distName': dist_attr,
            'id': mo_id,
            'operation': operation
        })
        for pname, val in params.items():
            p = ET.SubElement(mo, "p", {'name': pname})
            p.text = val
    return ET.ElementTree(root)

def make_xml(etree, docname):
    rough_string = ET.tostring(etree.getroot(), encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    with open(f"{docname}.xml", "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    print(f"XML file '{docname}.xml' generated successfully.")

if __name__ == "__main__":
    path_2024 = r"C:\Users\DELL-P5540\Downloads\Nokia_AIOSC24_SCF_NIDD4.0_v17 (1).xml"
    path_2025 = r"C:\Users\DELL-P5540\Downloads\AIOSC25_drop1_dataModel (1).xml"
    tree_base = ET.parse(path_2024).getroot()
    tree_update = ET.parse(path_2025).getroot()
    ns = {'ns': 'raml21.xsd'}
    comp_base = simplify_xml(tree_base, ns)
    comp_update = simplify_xml(tree_update, ns)
    comp_updated = update_dictionary(comp_base, comp_update)
    output_name = input("Enter output file name (without .xml): ")
    final_xml = build_full_xml(comp_updated)
    make_xml(final_xml, output_name)
