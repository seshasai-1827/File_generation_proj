
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

import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
import dicttoxml

def make_name(st):
    l = st.split('/',3)
    if len(l) != 4:
        return False
    return l[-1]


def simplify_xml(root,ns):
    base = {}
    base_list = root.findall(".//ns:managedObject",ns)
    for element in base_list:
        class_base =  element.attrib['class']
        distName = element.attrib['distName']#this is unique ig
        key = make_name(distName)
        if key == False:
            continue

        base[key] = {}
        '''if class_base not in base.keys():
            base[class_base] = {}
    
        base[class_base][distName] = {}'''
        for parameters in element.findall("ns:p",ns):
            #print(parameters.attrib['name'],parameters.text)
            if parameters.text:
                #base[class_base][distName][parameters.attrib['name']] = parameters.text
                base[key][parameters.attrib['name']] = parameters.text
    #print(base)
    xml = dicttoxml.dicttoxml(base)
    dom = parseString(xml)
    return base,dom

def convert_dict_xml(dictionary):
    xml = dicttoxml.dicttoxml(dictionary)
    dom = parseString(xml)
    return dom


def make_xml(domstring,docname):  
    with open(f"{docname}.xml", "w", encoding="utf-8") as f:
        f.write(domstring.toprettyxml())
        print("output file generated")

def update_dictionary(comp_base,comp_update):
    for x in comp_update:
        for y in comp_update[x]:
            print(x,y)
            try:
                up_val = comp_base[x][y]
                comp_update[x][y] = up_val
            except:
                pass
    return comp_update

tree_update = ET.parse(r"C:\Users\Seshasai chillara\OneDrive\Desktop\nokia\AIOSC25_drop1_dataModel.xml").getroot()
tree_base = ET.parse(r"C:\Users\Seshasai chillara\OneDrive\Desktop\nokia\Nokia_AIOSC24_SCF_NIDD4.0_v17.xml").getroot()

ns = {'ns':'raml21.xsd'}

comp_base,comp_basefile = simplify_xml(tree_base,ns)
comp_update,comp_updatefile = simplify_xml(tree_update,ns)

print("base file : \n\n")
print(comp_base)
print("\n\n\nupdate file :\n\n")
print(comp_update)

comp_finalfile = convert_dict_xml(update_dictionary(comp_base,comp_update))
make_xml(comp_finalfile,input("please enter file name to be created : "))