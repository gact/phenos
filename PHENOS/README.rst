Phenos========================


This code provides functions for reading txt files produced by BMG Labtech's MARS analysis software (data produced by their FLUOstar series of microplate readers), combining readings from multiple files, assigning strain and genotype information to readings, visualising growth curves and extracting growth measures, identifying missing colonies in an array, generating instruction files that tell the Singer RotorHDA Stinger how to fill in missing colonies from source plates, or rearray strains based on their growth under particular conditions


__________________________________________
core.py

This module defines some useful general purpose functions.


__________________________________________
dbtypes.py

This module includes:

* Classes for reading various input files. These are all structured in the same way and include checking functions that allow automatic detection of the correct reader for a given type of file.

* Wrapper classes for interacting with PyTables databases, intended to make it much easier to define new types of record and table with complex relationships to other records and tables. Every table is represented by a descendant of the DBTable class, and each record within that table by a descendant of DBRecord. Each record consists of a series of DBAtoms (column fields), which define their own data type and other functions. DBRecords can also be treated as DBAtoms and included in other records, so that it is possible to access atoms of, for example, a PlateLayout record that is itself an atom within a Reading record.
Different DBAtom and DBRecord subclasses are defined, and in some cases sets of records can be defined as subrecords of another type of record, e.g. Each File record has a yield_records method that yields a series of Reading records that are derived from that File.
Any DBTable subclasses that also inherit from the InMemory class will have their objects stored as dictionaries within memory, enabling more rapid access to data without having to open the database.


__________________________________________
gui.py


This module defines some Tkinter-wrapping classes used for the GUI front end script PHENOS.py

__________________________________________
graphics.py


This module contains wrapper classes for matplotlib to generate certain kinds of plots with predefined parameters, and translation functions which accept dbtype objects as inputs and extract the relevant values to pass to the wrapper classes. 

__________________________________________