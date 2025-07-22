import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import OrderedDict
from datetime import datetime
import csv
import copy
import os
import sys
import re # Import regex module for filename validation

class CommonAttributes:
    """
    A class to hold common attributes extracted from the XML,
    such as the base distribution name and ID.
    """
    def __init__(self):
        self.dist_name_base = None
        self.id_base = None

def make_name(dist, ctx):
    """
    Extracts the leaf name from a full distinguished name (distName).
    Also sets the base distName for the context if not already set.

    Args:
        dist (str): The full distinguished name (e.g., "AIOSC-1/Device-1/Moc-1").
        ctx (CommonAttributes): The context object to store base attributes.

    Returns:
        str: The leaf name (e.g., "Moc-1") or None if invalid.
    """
    if not dist:
        return None
    parts = dist.split('/', 2)
    # Exclude base objects like INTEGRATE-1 or Device-1 from being considered as leaves
    if len(parts) != 3 or parts[-1] in ("INTEGRATE-1", "Device-1"):
        return None
    if ctx.dist_name_base is None:
        ctx.dist_name_base = parts[0] + "/" + parts[1]
    return parts[-1]

def simplify_xml(root, ns, ctx):
    """
    Parses the XML tree and extracts managed objects and their parameters
    into a simplified dictionary structure.

    Args:
        root (xml.etree.ElementTree.Element): The root element of the XML tree.
        ns (dict): Namespace dictionary for XML parsing.
        ctx (CommonAttributes): The context object to store base attributes.

    Returns:
        OrderedDict: A nested dictionary representing simplified XML data.
                     Format: {class_name: {leaf_name: {param_name: param_value, ...}}}
    """
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
            ctx.id_base = mo.attrib.get("id", "10400") # Default ID if not found
        for p in mo.findall("ns:p", ns):
            if p.text is not None:
                entry[p.attrib["name"]] = p.text
        data.setdefault(cls, OrderedDict())[leaf] = entry
    return data

def count_total_mos(d):
    """
    Counts the total number of managed objects in a simplified dictionary.

    Args:
        d (OrderedDict): The simplified XML data dictionary.

    Returns:
        int: Total count of managed objects.
    """
    return sum(len(inner) for inner in d.values())

def merge_dicts(base, skeletal, alarm_list):
    """
    Merges the skeletal dictionary into the base dictionary, prioritizing
    skeletal for new objects and base for parameter values in common objects.
    Adds a separate alarm_list if provided.

    Args:
        base (OrderedDict): The simplified data from the base XML file.
        skeletal (OrderedDict): The simplified data from the skeletal XML file.
        alarm_list (OrderedDict): A dictionary of supported alarms from CSV.

    Returns:
        tuple: A tuple containing:
            - final_dict (OrderedDict): The merged dictionary.
            - common_objs (list): List of (class, distName) tuples for common objects.
            - carried_objs (list): List of (class, distName) tuples for objects carried from base.
    """
    common_objs, carried_objs = [], []
    final_dict = copy.deepcopy(skeletal) # Start with skeletal as the base for merge

    # Process objects present in both skeletal and base
    for cls in skeletal:
        if cls in base:
            for dist in skeletal[cls]:
                if dist in base[cls]:
                    common_objs.append((cls, dist))
                    # For common objects, update parameters from base
                    for p_name, p_val in skeletal[cls][dist].items():
                        if p_name.startswith('_'): # Skip internal attributes like _class, _operation
                            continue
                        if p_name in base[cls][dist]:
                            final_dict[cls][dist][p_name] = base[cls][dist][p_name]
                # If dist not in base[cls], it's a new object from skeletal, already in final_dict

    # Add objects from base that are not in skeletal (carried over)
    for cls in base:
        if cls not in skeletal:
            # If an entire class is new in base, carry all its objects
            for dist in base[cls]:
                carried_objs.append((cls, dist))
                final_dict.setdefault(cls, OrderedDict())[dist] = base[cls][dist]
        else:
            for dist in base[cls]:
                if dist not in skeletal[cls]:
                    # If a specific object is new in base within an existing class, carry it
                    carried_objs.append((cls, dist))
                    final_dict[cls][dist] = base[cls][dist]

    # Add supported alarms from the CSV if available
    if alarm_list:
        final_dict["com.nokia.aiosc:SupportedAlarm"] = alarm_list
    return final_dict, common_objs, carried_objs

def find_diff(base, final_):
    """
    Identifies new and deprecated managed objects between two dictionaries.

    Args:
        base (OrderedDict): The original base dictionary.
        final_ (OrderedDict): The final merged dictionary.

    Returns:
        tuple: A tuple containing:
            - new (list): List of (class, distName) tuples for new objects.
            - depr (list): List of (class, distName) tuples for deprecated objects.
    """
    depr, new = [], []

    # Find deprecated objects (in base but not in final_)
    for cls, inner in base.items():
        for dist in inner:
            if cls not in final_ or dist not in final_[cls]:
                depr.append((cls, dist))

    # Find new objects (in final_ but not in base)
    for cls, inner in final_.items():
        for dist in inner:
            if cls not in base or dist not in base[cls]:
                new.append((cls, dist))
    return new, depr

def build_full_xml(data_dict, ctx, out_name="AIOSC_Merged"):
    """
    Builds a full XML ElementTree from the merged data dictionary.

    Args:
        data_dict (OrderedDict): The merged data dictionary.
        ctx (CommonAttributes): The context object containing base attributes.
        out_name (str): The desired output file name (used for version string prompt).

    Returns:
        xml.etree.ElementTree.ElementTree: The complete XML ElementTree.
    """
    dist_name_base = ctx.dist_name_base
    id_base = ctx.id_base
    vers = input("Enter Version String (e.g., AIOSC25.0_DROP2, default: custom): ").strip() or "custom"
    NS_URI = "raml21.xsd"
    ET.register_namespace('', NS_URI) # Register default namespace
    root = ET.Element("raml", {'version': '2.1', 'xmlns': NS_URI})
    cmD = ET.SubElement(root, "cmData", {'type': 'plan', 'scope': 'all'})

    def hdr(attrs, param_dict):
        """Helper to create managedObject and its parameters."""
        mo = ET.SubElement(cmD, "managedObject", attrs)
        for n, v in param_dict.items():
            ET.SubElement(mo, "p", {'name': n}).text = v

    # Add standard header managed objects
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

    # Classes that are handled by specific header functions, so skip in general loop
    skip_hdr_classes = {
        "com.nokia.aiosc:AIOSC",
        "com.nokia.integrate:INTEGRATE",
        "com.nokia.aiosc:Device",
    }

    # Add all other managed objects from the merged data
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
                if pname.startswith('_'): # Skip internal attributes
                    continue
                ET.SubElement(tag, "p", {'name': pname}).text = pval

    return ET.ElementTree(root)

def write_xml(tree, name="AIOSC_Merged"):
    """
    Writes the XML ElementTree to a file with pretty printing.

    Args:
        tree (xml.etree.ElementTree.ElementTree): The XML tree to write.
        name (str): The desired output file name (without extension).

    Raises:
        Exception: If there's an error during file writing (e.g., permissions).
    """
    try:
        # Use minidom for pretty printing; tostring produces bytes, so decode
        txt = minidom.parseString(ET.tostring(tree.getroot(), "utf-8")).toprettyxml(indent="    ")
        with open(name + ".xml", "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"\u2713 Successfully wrote {name}.xml")
    except Exception as e:
        print(f"Error writing XML file '{name}.xml': {e}")
        raise # Re-raise to be caught by main error handler

def csv_report(base, final_, new, carried, depr, common, name="AIOSC_report.csv"):
    """
    Generates a CSV report summarizing the merge operation.

    Args:
        base (OrderedDict): The simplified data from the base XML file.
        final_ (OrderedDict): The final merged dictionary.
        new (list): List of new objects.
        carried (list): List of carried objects.
        depr (list): List of deprecated objects.
        common (list): List of common objects.
        name (str): The desired output CSV file name.

    Raises:
        Exception: If there's an error during file writing.
    """
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
            w.writerow([]) # Blank row for readability
            w.writerow(["Metric", "Count"])
            w.writerow(["Objects in BASE (Original)", total_base])
            w.writerow(["Objects in FINAL (Merged)", total_final])
            w.writerow(["NEW (from Skeletal)", total_new])
            w.writerow(["CARRIED (from Base)", total_carried])
            w.writerow(["COMMON (shared & modified)", total_common])
            w.writerow(["DEPRECATED (removed from Base)", total_deprecated])
            w.writerow([]) # Blank row for readability
            w.writerow(["Class", "DistName", "Status"])

            def get_status(cls, dist):
                """Determines the status of an object for the report."""
                if (cls, dist) in new_set:
                    return "NEW"
                if (cls, dist) in carried_set:
                    return "CARRIED"
                if (cls, dist) in common_set:
                    return "COMMON"
                return "UNKNOWN"

            # Write status for objects in the final merged dictionary
            for cls, inner in sorted(final_.items()):
                for dist in sorted(inner):
                    w.writerow([cls, dist, get_status(cls, dist)])

            # Write status for deprecated objects
            for cls, dist in sorted(depr_set):
                w.writerow([cls, dist, "DEPRECATED"])
        print(f"\u2713 Successfully wrote {name}")
    except Exception as e:
        print(f"Error writing CSV report '{name}': {e}")
        raise # Re-raise to be caught by main error handler

def log_param_changes(base_dict, final_dict, filename="param_changes.log"):
    """
    Generates a log file detailing parameter additions, removals, and modifications
    between the base and final dictionaries.

    Args:
        base_dict (OrderedDict): The simplified data from the base XML file.
        final_dict (OrderedDict): The final merged dictionary.
        filename (str): The desired output log file name.

    Raises:
        Exception: If there's an error during file writing.
    """
    added, removed, changed = [], [], []

    # Iterate through the final dictionary to find new and changed parameters/objects
    for cls in final_dict:
        if cls not in base_dict:
            # Entirely new class added in skeletal
            for dist in final_dict[cls]:
                for p_name, p_val in final_dict[cls][dist].items():
                    if not p_name.startswith('_'):
                        added.append((cls, dist, p_name, p_val))
            continue

        for dist in final_dict[cls]:
            if dist not in base_dict[cls]:
                # New distribution in an existing class
                for p_name, p_val in final_dict[cls][dist].items():
                    if not p_name.startswith('_'):
                        added.append((cls, dist, p_name, p_val))
                continue

            # Compare parameters for existing class and distribution
            skeletal_entry = final_dict[cls][dist]
            base_entry = base_dict[cls][dist]
            skeletal_keys = set(k for k in skeletal_entry if not k.startswith('_'))
            base_keys = set(k for k in base_entry if not k.startswith('_'))

            # Parameters added to an existing object
            for p_name in skeletal_keys - base_keys:
                added.append((cls, dist, p_name, skeletal_entry[p_name]))
            # Parameters removed from an existing object
            for p_name in base_keys - skeletal_keys:
                removed.append((cls, dist, p_name, base_entry[p_name]))
            # Parameters whose values have changed
            for p_name in skeletal_keys.intersection(base_keys):
                if skeletal_entry[p_name] != base_entry[p_name]:
                    changed.append((cls, dist, p_name, base_entry[p_name], skeletal_entry[p_name]))

    # Iterate through the base dictionary to find removed classes/distributions
    for cls in base_dict:
        if cls not in final_dict:
            # Entire class removed
            for dist in base_dict[cls]:
                for p_name, p_val in base_dict[cls][dist].items():
                    if not p_name.startswith('_'):
                        removed.append((cls, dist, p_name, p_val))
        else:
            for dist in base_dict[cls]:
                if dist not in final_dict[cls]:
                    # Specific distribution removed within an existing class
                    for p_name, p_val in base_dict[cls][dist].items():
                        if not p_name.startswith('_'):
                            removed.append((cls, dist, p_name, p_val))

    # Write to file
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("📘 Parameter Change Log\n")
            f.write(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n\n")

            f.write("✅ New Parameters (in existing or new classes/distributions):\n")
            if not added:
                f.write("  No parameters added.\n")
            for item in added:
                cls, dist, p, val = item
                f.write(f"  [ADDED]     Class: {cls}, Object: {dist}, Parameter: {p}, Value: '{val}'\n")

            f.write("\n❌ Removed Parameters (no longer present in final configuration):\n")
            if not removed:
                f.write("  No parameters removed.\n")
            for item in removed:
                cls, dist, p, val = item
                f.write(f"  [REMOVED]   Class: {cls}, Object: {dist}, Parameter: {p}, Original Value: '{val}'\n")

            f.write("\n🔁 Modified Parameters (value changed):\n")
            if not changed:
                f.write("  No parameters modified.\n")
            for item in changed:
                cls, dist, p, old_val, new_val = item
                f.write(f"  [MODIFIED]  Class: {cls}, Object: {dist}, Parameter: {p}, Old Value: '{old_val}', New Value: '{new_val}'\n")

        print(f"✅ Logged parameter changes to {filename}")
    except Exception as e:
        print(f"❌ Error writing parameter log file '{filename}': {e}")
        raise # Re-raise to be caught by main error handler

def readcsv(file_path):
    """
    Reads a CSV file to extract supported alarm definitions.

    The CSV is expected to have at least 3 columns:
    1. FaultIdn
    2. MocIdn
    3. ReportingMechanism

    Args:
        file_path (str): The path to the CSV file. This path is assumed to be valid and existing
                         as it's validated in the main block.

    Returns:
        OrderedDict: A dictionary of supported alarms, or an empty OrderedDict
                     if the file is empty or contains only invalid rows.

    Raises:
        UnicodeDecodeError: If the CSV file encoding is not UTF-8.
        Exception: For other unexpected errors during CSV parsing.
    """
    d = OrderedDict()
    try:
        with open(file_path, newline='', encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            i = 1 # Counter for unique leaf names
            for row in reader:
                # Basic validation for row length
                if len(row) < 3:
                    print(f"Warning: Skipping invalid row in CSV: {row} - Expected at least 3 columns (FaultIdn, MocIdn, ReportingMechanism).")
                    continue
                leaf = f"Device-1/FaultMgmt-1/SupportedAlarm-{i}"
                d[leaf] = {
                    "_class": "com.nokia.aiosc:SupportedAlarm",
                    "_operation": "create",
                    "FaultIdn": row[0].strip(), # Trim whitespace
                    "MocIdn": row[1].strip(),
                    "ReportingMechanism": row[2].strip()
                }
                i += 1
    except UnicodeDecodeError as e:
        print(f"Error: Failed to read CSV file '{file_path}' due to encoding issues. Please ensure it's UTF-8 encoded: {e}")
        raise # Re-raise to be caught by main error handler
    except Exception as e:
        print(f"Error: An unexpected error occurred while parsing CSV file '{file_path}': {e}")
        raise # Re-raise to be caught by main error handler
    return d

def is_valid_filename(filename):
    """
    Checks if a string is a valid filename for common operating systems.
    Prevents characters often disallowed or problematic.

    Args:
        filename (str): The filename to check.

    Returns:
        bool: True if the filename is valid, False otherwise.
    """
    if not filename:
        return False
    # Characters generally disallowed in Windows, macOS, Linux
    # Also disallow leading/trailing spaces and filenames that are just '.' or '..'
    invalid_chars = r'[<>:"/\\|?*\x00-\x1F]' # ASCII control characters also invalid
    if re.search(invalid_chars, filename):
        return False
    if filename.strip() != filename: # Check for leading/trailing spaces
        return False
    if filename in ('.', '..'): # Special directory names
        return False
    # Additional check for Windows reserved names (e.g., CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    # (Optional, but good for robustness if targeting Windows)
    if sys.platform == "win32":
        windows_reserved_names = [
            'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5',
            'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4',
            'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        ]
        if filename.upper().split('.')[0] in windows_reserved_names:
            return False
    return True


def help_menu(error_type=None):
    """
    Provides context-sensitive help and instructions based on the type of error encountered.

    Args:
        error_type (str, optional): A string indicating the type of error.
                                    Expected values: "FileNotFound", "XMLParseError",
                                    "CSVReadError", "FileWriteError", "OutputFilenameError", "GeneralError".
    """
    print("\n--- 🆘 HELP MENU 🆘 ---")
    if error_type == "FileNotFound":
        print("💡 **File Not Found Error**: The path you provided for an XML or CSV file does not exist or is incorrect.")
        print("   * **Instructions**:")
        print("     1. **Verify the path**: Double-check the spelling and ensure the full path is correct.")
        print("     2. **Check file existence**: Confirm that the file actually resides at the specified location.")
        print("     3. **Absolute vs. Relative Paths**: If the file is in the same directory as this script, you can simply type its name (e.g., '`base.xml`'). Otherwise, provide the **full absolute path** (e.g., '`C:\\Users\\YourName\\Documents\\base.xml`' on Windows or '`/home/yourname/data/base.xml`' on Linux/macOS).")
        print("     4. **Permissions**: Ensure you have read permissions for the file and its containing directory.")
    elif error_type == "XMLParseError":
        print("⚠️ **XML Parsing Error**: The XML file you provided is malformed, corrupted, or does not conform to expected XML standards.")
        print("   * **Instructions**:")
        print("     1. **Open the XML file**: Use a robust text editor (like VS Code, Notepad++, Sublime Text) or an XML validator tool.")
        print("     2. **Check for well-formedness**: All XML tags must be correctly opened and closed (e.g., `<tag>` and `</tag>`). Tags must be properly nested.")
        print("     3. **Look for unescaped characters**: Special characters within XML content must be escaped: `<` as `&lt;`, `>` as `&gt;`, `&` as `&amp;`, `'` as `&apos;`, `\"` as `&quot;`.")
        print("     4. **Validate XML structure**: Ensure the XML adheres to the expected schema (`raml21.xsd`). Missing root elements or incorrect attribute syntax are common culprits.")
        print("     5. **Encoding issues**: Confirm the file is saved with a compatible encoding, preferably **UTF-8**, to avoid character parsing problems.")
    elif error_type == "CSVReadError":
        print("❌ **CSV Reading Error**: There was an issue processing the CSV file intended for supported alarms.")
        print("   * **Instructions**:")
        print("     1. **Verify CSV column format**: Each row in the CSV must contain at least **3 columns** in the following order: `FaultIdn`, `MocIdn`, and `ReportingMechanism`.")
        print("     2. **Check delimiters**: Ensure the CSV uses a **comma (`,`)** as the primary delimiter between values.")
        print("     3. **Empty rows or malformed data**: Remove any entirely empty rows or rows that have an inconsistent number of columns (less than 3).")
        print("     4. **File encoding**: Confirm the CSV is saved as **UTF-8** to prevent character decoding errors.")
        print("     5. **No header row expected**: This script expects raw data starting from the first line; do not include a header row in the CSV.")
    elif error_type == "OutputFilenameError":
        print("🚫 **Invalid Output Filename**: The name you provided for the output file contains disallowed characters or formatting.")
        print("   * **Instructions**:")
        print("     1. **Avoid special characters**: Do not use characters like `\\`, `/`, `:`, `*`, `?`, `\"`, `<`, `>`, `|` in the filename.")
        print("     2. **No leading/trailing spaces**: Filenames should not start or end with spaces.")
        print("     3. **Avoid reserved names**: Do not use names like `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9` (especially on Windows).")
        print("     4. **Simple names**: Stick to letters, numbers, hyphens (`-`), underscores (`_`), and periods (`.`) for the extension. For example, '`MyMergedXML`' or '`merged_data_v2`'.")
    elif error_type == "FileWriteError":
        print("🚫 **File Write Error**: The script encountered an issue when attempting to create or write to an output file (merged XML or CSV report), *after* the filename was deemed valid.")
        print("   * **Instructions**:")
        print("     1. **Check disk space**: Ensure you have sufficient free space on your storage drive.")
        print("     2. **Verify directory permissions**: Make sure the script has **write permissions** in the directory where you are trying to save the output files.")
        print("     3. **File already open**: Ensure the target output file isn't currently open in another program (e.g., text editor, Excel), which can prevent writing.")
        print("     4. **Antivirus/Security software**: Temporarily check if any antivirus or security software is blocking file write operations for this script.")
    else: # General catch-all for uncategorized errors
        print("❓ **General Error**: An unexpected issue occurred during script execution.")
        print("   * **Instructions**:")
        print("     1. **Review previous messages**: Look at the specific error message printed just before this help menu for more clues.")
        print("     2. **Validate all inputs**: Double-check the validity and format of all input files (XMLs and CSV, if used).")
        print("     3. **Re-run the script**: Sometimes, transient issues can be resolved by simply trying again.")
        print("     4. **Contact support**: If the issue persists, provide the full console output, including the error message, along with your input files to the script maintainer for further assistance.")
    print("--- 🏁 END HELP MENU 🏁 ---")

if __name__ == "__main__":
    ns = {'ns': 'raml21.xsd'}
    last_error_type = None # Tracks the type of the last significant error for targeted help

    try:
        print("--- AIOSC XML Merge Tool ---")

        # --- Input File Path Validation Loop for BASE XML ---
        while True:
            base_file = input("Enter the path to the BASE XML file: ").strip()
            if not base_file:
                print("Error: Base XML file path cannot be empty. Please try again.")
                last_error_type = "FileNotFound"
                help_menu(last_error_type)
                continue
            if not os.path.isfile(base_file):
                print(f"Error: BASE XML file '{base_file}' not found. Please re-enter the path.")
                last_error_type = "FileNotFound"
                help_menu(last_error_type)
                continue
            if not base_file.lower().endswith(".xml"):
                print(f"Error: BASE file '{base_file}' does not have an XML extension. Please re-enter the path.")
                last_error_type = "XMLParseError" # Likely a format issue
                continue
            break # Valid path

        # --- Input File Path Validation Loop for SKELETAL XML ---
        while True:
            skeletal_file = input("Enter the path to the SKELETAL XML file: ").strip()
            if not skeletal_file:
                print("Error: Skeletal XML file path cannot be empty. Please try again.")
                last_error_type = "FileNotFound"
                help_menu(last_error_type)
                continue
            if not os.path.isfile(skeletal_file):
                print(f"Error: SKELETAL XML file '{skeletal_file}' not found. Please re-enter the path.")
                last_error_type = "FileNotFound"
                help_menu(last_error_type)
                continue
            if not skeletal_file.lower().endswith(".xml"):
                print(f"Error: SKELETAL file '{skeletal_file}' does not have an XML extension. Please re-enter the path.")
                last_error_type = "XMLParseError"
                continue
            break # Valid path

        # --- Input File Path Validation Loop for CSV (optional) ---
        while True:
            csv_file = input("Enter the file path for supported alarms (.csv) (default: None): ").strip()
            if not csv_file: # User chose not to provide a CSV
                print("No CSV file provided for supported alarms. Skipping.")
                break
            if not os.path.isfile(csv_file):
                print(f"Error: CSV file '{csv_file}' not found. Please re-enter the path or leave blank to skip.")
                last_error_type = "FileNotFound"
                help_menu(last_error_type)
                continue
            if not csv_file.lower().endswith(".csv"):
                print(f"Error: CSV file '{csv_file}' does not have a CSV extension. Please re-enter the path or leave blank to skip.")
                last_error_type = "CSVReadError" # Likely a format issue
                help_menu(last_error_type)
                continue
            break # Valid path

        # --- XML Parsing ---
        try:
            print(f"Attempting to parse BASE XML: {base_file}")
            base_root = ET.parse(base_file).getroot()
        except ET.ParseError as e:
            print(f"Fatal Error: BASE XML file '{base_file}' is not a valid XML format: {e}")
            last_error_type = "XMLParseError"
            raise # Re-raise to be caught by the main error handler
        except Exception as e:
            print(f"An unexpected error occurred while processing BASE XML '{base_file}': {e}")
            last_error_type = "XMLParseError" # Categorize as XML parse for general help
            raise

        try:
            print(f"Attempting to parse SKELETAL XML: {skeletal_file}")
            skeletal_root = ET.parse(skeletal_file).getroot()
        except ET.ParseError as e:
            print(f"Fatal Error: SKELETAL XML file '{skeletal_file}' is not a valid XML format: {e}")
            last_error_type = "XMLParseError"
            raise # Re-raise to be caught by the main error handler
        except Exception as e:
            print(f"An unexpected error occurred while processing SKELETAL XML '{skeletal_file}': {e}")
            last_error_type = "XMLParseError" # Categorize as XML parse for general help
            raise

        # --- Data Simplification and CSV Import ---
        common_attr = CommonAttributes()
        print("Simplifying BASE XML data...")
        comp_base = simplify_xml(base_root, ns, common_attr)
        print("Simplifying SKELETAL XML data...")
        comp_skeletal = simplify_xml(skeletal_root, ns, common_attr)
        
        alarm_list = OrderedDict() # Initialize empty
        if csv_file: # Only attempt to read CSV if a path was provided and validated
            print(f"Attempting to read supported alarms from CSV: {csv_file}")
            try:
                alarm_list = readcsv(csv_file)
            except Exception as e:
                # readcsv already prints specific errors, but we catch here to set error type and prompt help
                last_error_type = "CSVReadError"
                raise # Re-raise to trigger the finally block for help

        # --- Merge and Diff Operations ---
        print("Merging XML data...")
        final_dict, common_objs, carried_objs = merge_dicts(comp_base, comp_skeletal, alarm_list)
        new_objs, deprecated = find_diff(comp_base, final_dict)
        
        print("\n--- Merge Summary ---")
        print(f"Objects in BASE (Original)    : {count_total_mos(comp_base)}")
        print(f"Objects in SKELETAL           : {count_total_mos(comp_skeletal)}")
        print(f"Objects in FINAL (Merged)     : {count_total_mos(final_dict)}")
        print(f"NEW Objects (from Skeletal)   : {len(new_objs)}")
        print(f"CARRIED Objects (from Base)   : {len(carried_objs)}")
        print(f"COMMON Objects (shared)       : {len(common_objs)}")
        print(f"DEPRECATED Objects (removed)  : {len(deprecated)}")
        print("---------------------\n")

        # --- Output Generation ---
        # Log parameter changes
        try:
            log_param_changes(comp_base, final_dict)
        except Exception: # log_param_changes prints specific error, just re-raise for help
            last_error_type = "FileWriteError" # Keep general as it's a write issue
            raise

        # --- Output Filename Validation Loop ---
        while True:
            out_name = input("Enter the output file name (default: AIOSC_Merged): ").strip() or "AIOSC_Merged"
            if not is_valid_filename(out_name):
                print(f"Error: The output filename '{out_name}' contains invalid characters or formatting. Please try again.")
                last_error_type = "OutputFilenameError"
                help_menu(last_error_type)
                continue
            break # Valid filename

        print(f"Building final XML structure for '{out_name}.xml'...")
        tree = build_full_xml(final_dict, common_attr, out_name)
        
        # Write merged XML
        try:
            write_xml(tree, out_name)
        except Exception: # write_xml prints specific error, just re-raise for help
            last_error_type = "FileWriteError" # Keep general as it's a write issue (permissions, file open, etc.)
            raise

        # Generate CSV report
        try:
            # We use the same 'out_name' as a base for the report, but append "_report.csv"
            # The 'is_valid_filename' check for 'out_name' should cover this implicitly
            csv_report(comp_base, final_dict, new_objs, carried_objs, deprecated, common_objs, f"{out_name}_report.csv")
        except Exception: # csv_report prints specific error, just re-raise for help
            last_error_type = "FileWriteError" # Keep general as it's a write issue
            raise


    except FileNotFoundError as e:
        print(f"Fatal Error: {e}")
    except ET.ParseError as e:
        print(f"Fatal XML Parsing Error: {e}")
    except Exception as e:
        print(f"An unexpected critical error occurred: {e}")
        if last_error_type is None:
            last_error_type = "GeneralError"
    finally:
        if last_error_type:
            while True:
                user_input = input("\nType 'help' for troubleshooting guidance, or 'exit' to quit: ").strip().lower()
                if user_input == "help":
                    help_menu(last_error_type)
                elif user_input == "exit":
                    print("Exiting the AIOSC XML Merge Tool. Goodbye!")
                    break
                else:
                    print("Invalid input. Please type 'help' or 'exit'.")
        # Check if an exception was raised and caught (meaning last_error_type was set)
        # If not, it means the script completed successfully without hitting an error
        elif 'e' not in locals(): # This checks if the exception variable 'e' was created in the try block
            print("No errors detected. Script finished.")