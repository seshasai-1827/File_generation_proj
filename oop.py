import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import OrderedDict
import csv

class ManagedObject:
    def __init__(self, mo_class, distname, version, mo_id, operation, paramdict):
        self.mo_class = mo_class
        self.distname = distname
        self.version = version
        self.mo_id = mo_id
        self.operation = operation
        self.paramdict = paramdict

class Document:
    def __init__(self, data_dict, xml_tree=None):
        self.data_dict = data_dict
        self.version_string = self.get_version_string()
        self.num_objects = len(data_dict)
        self.xml_tree = xml_tree

    def get_version_string(self):
        for key, params in self.data_dict.items():
            return params.get('_version', 'UNKNOWN')
        return 'UNKNOWN'

def make_name(st):
    l = st.split('/', 3)
    if len(l) != 4:
        return False
    return l[-1]

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

def build_full_xml(data_dict):
    NS_URI = "raml21.xsd"
    ET.register_namespace('', NS_URI)
    root = ET.Element("raml", {'version': '2.1', 'xmlns': NS_URI})
    cmData = ET.SubElement(root, "cmData", {
        'type': 'plan',
        'scope': 'all',
        'name': 'AIOSC-1-PnP-ProfileD-Basic-Integration-Planfile.xml'
    })

    # Hardcoded initial managed objects
    aiosc = ET.SubElement(cmData, "managedObject", {
        'class': "com.nokia.aiosc:AIOSC",
        'version': get_version_string(data_dict),
        'distName': "PLMN-PLMN/AIOSC-6000039",
        'operation': "create"
    })
    ET.SubElement(aiosc, "p", {'name': "name"}).text = "PLMN-PLMN/AIOSC-6000039"
    ET.SubElement(aiosc, "p", {'name': "AutoConnHWID"}).text = "LBNKIASRC243920029"
    ET.SubElement(aiosc, "p", {'name': "$maintenanceRegionId"}).text = "PNP"
    ET.SubElement(aiosc, "p", {'name': "$maintenanceRegionCId"}).text = "1"
    ET.SubElement(aiosc, "p", {'name': "SparaPara2_CP"}).text = "1"
    ET.SubElement(aiosc, "p", {'name': "SparePara1_CP"}).text = "1"

    integrate = ET.SubElement(cmData, "managedObject", {
        'class': "com.nokia.integrate:INTEGRATE",
        'version': get_version_string(data_dict),
        'distName': "PLMN-PLMN/AIOSC-6000039/INTEGRATE-1",
        'id': "104000",
        'operation': "create"
    })
    ET.SubElement(integrate, "p", {'name': "plannedSWReleaseVersion"}).text = "AIOSC24_01_400_35.aio.sig0"
    ET.SubElement(integrate, "p", {'name': "systemReleaseVersion"}).text = "AIOSC24"
    ET.SubElement(integrate, "p", {'name': "ipVersion"}).text = "0"

    device = ET.SubElement(cmData, "managedObject", {
        'class': "com.nokia.aiosc:Device",
        'version': get_version_string(data_dict),
        'distName': "PLMN-PLMN/AIOSC-6000039",
        'operation': "create"
    })
    ET.SubElement(device, "p", {'name': "UserLabel"}).text = "AIOSC"

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
            ET.SubElement(mo, "p", {'name': pname}).text = val

    return ET.ElementTree(root)

def get_version_string(data_dict):
    for key, params in data_dict.items():
        return params.get('_version', 'UNKNOWN')
    return 'UNKNOWN'

def make_xml(etree, docname):
    rough_string = ET.tostring(etree.getroot(), encoding="utf-8")
    pretty_xml = minidom.parseString(rough_string).toprettyxml(indent="  ")
    with open(f"{docname}.xml", "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    print("XML file generated successfully.")

def update_dictionary(comp_base, comp_update, rename_dict):
    new_objs = []
    for key in comp_update:
        v = rename_dict.get(key, key)
        if v not in comp_base:
            mo = comp_update[key]
            new_objs.append([key, mo.get('_class', 'UNKNOWN'), mo.get('_distName', '')])
            continue

        mo_base = comp_base[v]
        mo_update = comp_update[key]
        for param in list(mo_update):
            if param.startswith('_'):
                continue
            param_rename = rename_dict.get(param, param)
            if param_rename in mo_base:
                mo_update[param] = mo_base[param_rename]
    return comp_update, new_objs

def generate_csv_report(comp_base, comp_update, rename_dict, new_objs):
    deprecated = []
    for key in comp_base:
        if key not in comp_update:
            mo = comp_base[key]
            deprecated.append([key, mo.get('_class', 'UNKNOWN'), mo.get('_distName', '')])

    with open("AIOSC_comparison_report.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Comparison Summary"])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Total in Base Version", len(comp_base)])
        writer.writerow(["Total in Update Version", len(comp_update)])
        writer.writerow(["New Objects", len(new_objs)])
        writer.writerow(["Deprecated Objects", len(deprecated)])
        writer.writerow([])
        writer.writerow(["New Objects"])
        writer.writerow(["Key", "Class", "DistName"])
        writer.writerows(new_objs)
        writer.writerow([])
        writer.writerow(["Deprecated Objects"])
        writer.writerow(["Key", "Class", "DistName"])
        writer.writerows(deprecated)

    print("Unified report written to 'AIOSC_comparison_report.csv'")

if __name__ == "__main__":
    rename_dict = {}
    ns = {'ns': 'raml21.xsd'}
    tree_update = ET.parse("AIOSC25_drop1_dataModel.xml").getroot()
    tree_base = ET.parse("Nokia_AIOSC24_SCF_NIDD4.0_v17.xml").getroot()
    comp_base = simplify_xml(tree_base, ns)
    comp_update = simplify_xml(tree_update, ns)
    update_dict, new_objs = update_dictionary(comp_base, comp_update, rename_dict)
    comp_finalfile = build_full_xml(update_dict)
    docname = input("please enter file name to be created : ")
    make_xml(comp_finalfile, docname)
    print("number of managed objects in the generated file        :", len(comp_update))
    print("number of managed objects in the previous version file :", len(comp_base))
    generate_csv_report(comp_base, comp_update, rename_dict, new_objs)

    base_document = Document(comp_base)
    update_document = Document(comp_update, comp_finalfile)