#!/usr/bin/python -tt
# -*- coding: utf-8 -*-
"""
Renames the current directory in _current_directory.txt
(in the parent folder of this one)
to match the folder that this script is run from.
"""

################################################################################

import os,sys

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.1"

if __name__=="__main__":
    scriptdir=os.path.dirname(os.path.realpath(sys.argv[0]))
    datdir,datfolder=os.path.split(scriptdir)
    cursorfile=os.path.join(datdir,"_current_directory.txt")
    assert os.path.exists(cursorfile)
    with open(cursorfile,"w") as txtfile:
        txtfile.write(datfolder)
    print "Current directory changed to",datfolder
