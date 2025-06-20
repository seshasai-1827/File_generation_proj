# Automated SCF File_generation_project

Rules:
#Allow for custom version string
#2025 parameters supercede 2024
#the values from 2024 need to replace the default values of the 2025 datamodel if the same managedobject exists in both files
#if manage object has not gone to the next version then it doesnot need to be added as its depricated
#if a common class is found between the base and skeletal then copy the managed objects directly to the final merged file

Instructions:
On your preffered code editor run the main.py file,then
1.Follow the Prompts:
a.The script will first ask you to:
Enter the path to the BASE XML file: Type the full path or the relative path to your older XML file (e.g., Nokia_AIOSC24_SCF_NIDD4.0_v17.xml). Press Enter.
b.Next, it will ask for:
Enter the path to the SKELETAL XML file: Type the full path or the relative path to your newer XML file (e.g., AIOSC25_drop1_dataModel.xml). Press Enter.
c.Finally, it will ask for a Version String:
You can type your desired version string (e.g., AIOSC25.0_DROP2) which will be applied to the version attribute of all managedObject elements in the output XML.
If you just press Enter, it will use the default version "custom".

2.Review the Output:

After processing, the script will create two new files in the same directory where main.py is located:
a.AIOSC_Merged.xml: This is your new, merged XML file. It incorporates the changes and value transfers based on your input files and renaming map.
b.AIOSC_Merge_Report.csv: This CSV file provides a detailed summary of the merge operation. It includes:
Overall counts of managed objects in the base, skeletal, and final merged files.
Counts of "NEW" (only in skeletal), "CARRIED" (only in base, but brought over), "COMMON" (in both and merged), and "DEPRECATED" (in base but removed from final) objects.
A comprehensive list of each managed object with its determined status.

