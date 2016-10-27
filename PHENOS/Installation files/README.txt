To install 

Copy files and folders to e.g. C:/PHENOS

Create user config folder, e.g. 


Run Python installer

Install modules

Wheel files come from http://www.lfd.uci.edu/~gohlke/pythonlibs/

Add C:\Python27 to Path (see http://superuser.com/questions/143119/how-to-add-python-to-the-windows-path)

Run cmd.exe in Admin mode

Navigate to the folder containing wheel files, (e.g. C:\PHENOS\Installation files\32bit)

python -m pip install [full name of wheel file]

The following modules should be installed in the following order:
Cython
numpy
numexpr
urllib3
six
h5py
tables
scipy
matplotlib
biopython

Any order:
xlrd
brewer2mpl



Edit config.txt and leave it in e.g. C:\Users\localadmin1\AppData\Roaming\PHENOS


[Locations]
source_directory = C:\Users\localadmin1\Desktop\Platereader output
target_directory = C:\PHENOS
user_folder = Test

[Controls]
controls = YPD, YPD 30C, COM, COM 30C, Control
