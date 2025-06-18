import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import OrderedDict
from openpyxl import Workbook
from openpyxl.styles import Font
import os


# ───────────────────────────── helpers ──────────────────────────────
def make_name(st):
    l = st.split('/', 2)
    if len(l) != 3 or l[-1] in ('INTEGRATE-1', 'Device-1'):
        return False
    return l[-1]


def simplify_xml(root, ns):
    """Return {class: OrderedDict{distName: MO‑entry}}."""
    data = OrderedDict()
    for mo in root.iterfind(".//ns:managedObject", ns):
        mo_class = mo.attrib.get("class")
        dist_name = make_name(mo.attrib.get("distName"))
        if not mo_class or not dist_name:
            continue

        entry = OrderedDict()
        entry['_class'] = mo_class
        entry['_distName'] = mo.attrib.get("distName")
        entry['_version'] = mo.attrib.get("version", "UNKNOWN")
        entry['_id'] = mo.attrib.get("id", "10400")
        entry['_operation'] = mo.attrib.get("operation", "create")

        for p in mo.findall("ns:p", ns):
            if p.text is not None:
                entry[p.attrib["name"]] = p.text

        data.setdefault(mo_class, OrderedDict())[dist_name] = entry
    return data


def count_total_mos(d):
    return sum(len(mo_dict) for mo_dict in d.values())


def find_deprecated(comp_base, comp_update):
    """List of (class, distName) that were present in base but not in update."""
    deprecated = []
    for cls, mo_dict in comp_base.items():
        for dist in mo_dict:
            if cls not in comp_update or dist not in comp_update[cls]:
                deprecated.append((cls, dist))
    return deprecated


# ───────────────────────────── merge ────────────────────────────────
def update_dictionary(comp_base, comp_update):
    new_objs = []
    for mo_class in comp_update:
        if mo_class in comp_base:
            # update values
            for dist in comp_update[mo_class]:
                if dist in comp_base[mo_class]:
                    for p in comp_update[mo_class][dist]:
                        if p.startswith('_'):
                            continue
                        if p in comp_base[mo_class][dist]:
                            comp_update[mo_class][dist][p] = \
                                comp_base[mo_class][dist][p]
                else:
                    new_objs.append((mo_class, dist))
            # add missing objects
            for dist in comp_base[mo_class]:
                if dist not in comp_update[mo_class]:
                    new_objs.append((mo_class, dist))
                    comp_update[mo_class][dist] = comp_base[mo_class][dist]
    return comp_update, new_objs


# ─────────────────────────── XML build / save ───────────────────────
def build_full_xml(data_dict, outfile_name="MergedPlan"):
    vers = input("Enter Version String : ")
    NS_URI = "raml21.xsd"
    ET.register_namespace('', NS_URI)
    root = ET.Element("raml", {'version': '2.1', 'xmlns': NS_URI})
    cmData = ET.SubElement(root, "cmData", {
        'type': 'plan', 'scope': 'all', 'name': outfile_name + ".xml"
    })

    for cls, mo_dict in data_dict.items():
        for entry in mo_dict.values():
            params = entry.copy()
            ET_MO = ET.SubElement(cmData, "managedObject", {
                'class': params.pop('_class'),
                'version': vers,
                'distName': params.pop('_distName'),
                'id': params.pop('_id', '10400'),
                'operation': params.pop('_operation', 'create')
            })
            for pname, pval in params.items():
                if pname.startswith('_'):
                    continue  # <-- this line excludes _version and others like _class
                ET.SubElement(ET_MO, "p", {'name': pname}).text = pval

    return ET.ElementTree(root)


def make_xml(etree, docname):
    xml_str = minidom.parseString(
        ET.tostring(etree.getroot(), "utf-8")).toprettyxml(indent="    ")
    with open(docname + ".xml", "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"✓  Wrote '{docname}.xml'")


# ─────────────────────────── Excel report ───────────────────────────
def generate_excel_report(comp_base, comp_update, added, deprecated, filename="AIOSC_report.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Comparison"

    # header
    hdr = Font(bold=True)
    ws.append(["Class", "DistName", "Status"])
    for c in "ABC":
        ws[c + "1"].font = hdr

    added_set = set(added)
    deprecated_set = set(deprecated)

    def rows(comp_dict):
        for cls, dic in comp_dict.items():
            for dist in dic:
                yield cls, dist

    for cls, dist in rows(comp_update):
        status = "NEW" if (cls, dist) in added_set else "COMMON"
        ws.append([cls, dist, status])

    for cls, dist in deprecated_set:
        ws.append([cls, dist, "DEPRECATED"])

    # auto width
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = \
            max(len(str(cell.value)) for cell in col) + 2

    wb.save(filename)
    print(f"✓  Excel report '{filename}' written")

# ───────────────────────────── Main ────────────────────────────────
if __name__ == "__main__":
    ns = {'ns': 'raml21.xsd'}

    base_xml = "Nokia_AIOSC24_SCF_NIDD4.0_v17.xml"
    upd_xml  = "AIOSC25_drop1_dataModel.xml"

    try:
        base_root = ET.parse(base_xml).getroot()
        upd_root  = ET.parse(upd_xml).getroot()
    except Exception as e:
        print("Error loading XML:", e)
        exit(1)

    comp_base   = simplify_xml(base_root, ns)
    comp_update = simplify_xml(upd_root, ns)

    print("Objects  BASE   :", count_total_mos(comp_base))
    print("Objects  UPDATE :", count_total_mos(comp_update))

    comp_final, added = update_dictionary(comp_base, comp_update)
    deprecated = find_deprecated(comp_base, comp_final)

    print("Objects after merge :", count_total_mos(comp_final))
    print("  Added objects     :", len(added))
    print("  Deprecated objects:", len(deprecated))

    merged_tree = build_full_xml(comp_final, outfile_name="AIOSC_Merged")
    make_xml(merged_tree, "AIOSC_Merged")

    generate_excel_report(comp_base, comp_final, added, deprecated)
