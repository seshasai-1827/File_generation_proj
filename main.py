
#rules
#dont change the version strings
#2025 parameters supercede 2024
#the values from 2024 need to replace the default values of the 2025 datamodel
#if manage object has not gone to the next version then it doesnot need to be added as its depricated

#phase 1
#for implementation
#develop a map of the file
#perform crud operations

#phase 2
#if parameter names are changed...

#parse through the old version file if tag is found in the new one then tranfer the parmeter values
#for the second phse if the parameter names have been changed then edit the old versions parameter names then perform same operation 

#TO DO
#need to add initial 3 parts
#the id and operation have been hardcoded, needs to be update based
import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
import dicttoxml
from collections import OrderedDict
from xml.dom import minidom


def make_name(st):
    l = st.split('/',3)
    if len(l) != 4:
        return False
    return l[-1]


def simplify_xml(root, ns):
    base = OrderedDict()
    base_list = root.findall(".//ns:managedObject", ns)
    for element in base_list:
        class_base = element.attrib['class']
        distName = element.attrib['distName']
        key = make_name(distName)
        if key is False:
            continue
        base[key] = OrderedDict()
        base[key]['_class'] = class_base
        base[key]['_distName'] = distName
        for parameters in element.findall("ns:p", ns):
            if parameters.text:
                base[key][parameters.attrib['name']] = parameters.text
    return base



def build_full_xml(data_dict):
    NS_URI = "raml21.xsd"
    ET.register_namespace('', NS_URI)
    version = input("enter version string : ")
    root = ET.Element("raml", {
        'version': '2.1',
        'xmlns': NS_URI
    })

    cmData = ET.SubElement(root,"cmData", {
        'type': 'plan',
        'scope': 'all',
        'name': 'AIOSC-1-PnP-ProfileD-Basic-Integration-Planfile.xml'
    })

    for key, params in data_dict.items():
        class_attr = params.pop('_class', 'UNKNOWN')
        dist_attr = params.pop('_distName', f"UNSPECIFIED/{key}")

        mo = ET.SubElement(cmData, "managedObject", {
            'class': class_attr,
            'version': version,
            'distName': dist_attr,
            'id': "10400",
            'operation' : "create",
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

    print("XML file generated successfully.")

def update_dictionary(comp_base,comp_update):
    for x in comp_update:
        for y in comp_update[x]:
            try:
                up_val = comp_base[x][y]
                comp_update[x][y] = up_val
            except:
                pass
    return comp_update

tree_update = ET.parse(r"C:\Users\Seshasai chillara\OneDrive\Desktop\nokia\AIOSC25_drop1_dataModel.xml").getroot()
tree_base = ET.parse(r"C:\Users\Seshasai chillara\OneDrive\Desktop\nokia\Nokia_AIOSC24_SCF_NIDD4.0_v17.xml").getroot()

ns = {'ns':'raml21.xsd'}

comp_base = simplify_xml(tree_base,ns)
comp_update = simplify_xml(tree_update,ns)


comp_finalfile = build_full_xml(update_dictionary(comp_base,comp_update))
make_xml(comp_finalfile,input("please enter file name to be created : "))