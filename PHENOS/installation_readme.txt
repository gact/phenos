Installation instructions for Windows

PHENOS is written for Windows as it operates alongside the Omega software from BGM Labtech which is also on Windows. It's been tested on Windows 7.


ONLINE

1) Install Python 2.7 from https://www.python.org/downloads/release/python-2711/, to, for example C:\Python27

2) Add this directory to Path, as described in http://superuser.com/questions/143119/how-to-add-python-to-the-windows-path

3) Download the PHENOS files from https://github.com/gact/phenos

4) Place the PHENOS files within a directory e.g. C:\PHENOS

5) Open the command console (cmd.exe) in administrator mode

6) If necessary change to the drive where the PHENOS files are. E.g. if on the D drive, type "d:"

7) Type "cd C:\PHENOS" (or whatever the path of the directory where you put the files)

8) Type "python setup.py install"


OFFLINE

If the target PC is not online, you must...

1) copy all installation files for Python 2.7, as well as the whole PHENOS package and the necessary wheel files for modules used in PHENOS, to the computer, e.g. with a USB drive. The wheel files are all provided in https://github.com/gact/phenos/tree/master/PHENOS/Installation%20files, with two subfolders for 32 bit and 64 bit versions of Windows.Alternatively you can get most of them from http://www.lfd.uci.edu/~gohlke/pythonlibs/ or from https://pypi.python.org/.

2) Run the Python installer and install Python 2.7 to, for example, C:\Python27

3) Add this directory to Path, as described in http://superuser.com/questions/143119/how-to-add-python-to-the-windows-path

4) Open the command console (cmd.exe) in administrator mode and navigate to the folder containing wheel files, (e.g. C:\PHENOS\Installation files\32bit)

5) Apart from xlrd and brewer2mpl, which can be installed at any point, the other wheel files should be installed in the following order:
	Cython
	numpy
	numexpr
	urllib3
	six
	h5py
	tables
	scipy
	pytz
	dateutil
	cycler
	pyparsing
	matplotlib
	biopython
For each wheel file, type "python -m pip install [full name of wheel file]"


FINAL SET-UP

After following the online or offline steps above...

1) Find config.txt in your users AppData folder, e.g. C:\Users\me\AppData\Roaming\PHENOS

2) Manually edit it to change the source_directory entry to whereever your platereader saves its data files, and the target_directory to wherever you wish you place all renamed files and visualizations.

3) If your display resolution is lower, you should edit the GUI position field to change 1100,800,50,50 to something like 800,600,50,50. These fix the size and position of the PHENOS windows to the specified height and width (in pixels), and x and y distance from the top left of the screen.

The config.txt file should then look something like this:
"""
[Locations]
source_directory = C:\Platetreader_output
target_directory = C:\PHENOSDATA
user_folder = Test

[Graphics]
type = png

[GUI]
position = 800,600,50,50

[Controls]
controls = YPD, YPD 30C, COM, COM 30C, Control
"""

Note that you can also specify here which treatment names are treated as control experiments, and add new treatment names to this list as needed.

4) Ensure that you have created Layout files for the arrays you use, and check and update target_directory\Genotypes\strains.csv with your strain information, and pointers to any genotype files stored in the same directory.

5) Find PHENOS.py and click it to run. Create a shortcut to it for convenience.



