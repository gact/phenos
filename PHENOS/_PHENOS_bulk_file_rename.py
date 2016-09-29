#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
Dangerous tool for renaming masses of filepaths at once
"""

################################################################################

import os, sys
from phenos import *

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.1"

namelogfile="rename.log"
namelogpath=os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])),
                         namelogfile)



def read_rename_file(renamefile="rename.txt"):
    fullpath=os.path.join(scriptdir(),renamefile)
    if not os.path.exists(fullpath):
        return False
    with open(fullpath,"rb") as fileob:
        reader=csv.reader(fileob,delimiter="\t")
        contents=[row for row in reader]
    return contents

def yield_files(tdir,dig=True):
    if dig:
        for root,dirs,files in os.walk(tdir,topdown=True):
            for name in files:
                yield os.path.join(root,name)
    else:
        for subpath in os.listdir(tdir):
            if os.path.isfile(os.path.join(tdir,subpath)):
                yield os.path.join(tdir,subpath)

def bulkrename(tdir,
               searchstring,
               replacestring,
               dig=True,
               includedatabases=True,
               countonly=False):
    """
    Renames all file paths in specified directory
    with all searchstrings replaced with replacestring

    stores log of all changes so they can be undone
    by the undorename function if necessary
    """

    changed=[]
    if os.path.exists(namelogpath):
        mode="a"
    else:
        mode="w"
    with open(namelogpath,mode) as fileob:
        #dig through directory
        for oldpath in yield_files(tdir,dig=dig):
            if searchstring in oldpath:
                newpath=oldpath.replace(searchstring,replacestring)
                changed.append((oldpath,newpath))
                if not countonly:
                    try:
                        #prepare_path(newpath)
                        os.renames(oldpath,newpath)
                        fileob.write("{}\t{}\n".format(oldpath,newpath))
                    except Exception as e:
                        LOG.error("couldn't rename {} to {} because {}\n"
                                  .format(oldpath,newpath,e))
    LOG.debug("finished bulkrename of {} to {} in {} ({} changes)"
              .format(searchstring,replacestring,tdir,len(changed)))
    return changed

def undorename(dir=None):
    with open(namelogpath,"r") as fileob:
        for line in fileob.readlines():
            oldpath,newpath=line.split("\t")
            try:
                #prepare_path(newpath)
                os.renames(newpath,oldpath)
            except Exception as e:
                LOG.error("couldn't undo rename {} to {} because {}\n"
                          .format(newpath,oldpath,e))

def bulkrename_in_databases(searchstring,replacestring):
    #create copy of each database file before changing
    pass
#
if __name__=="__main__":
    setup_logging("DEBUG")
    sys.excepthook=log_uncaught_exceptions

    rrf=read_rename_file()
    if rrf is False:
        rrf=[raw_input("Enter search term:"),
             raw_input("Enter replace term:")]

    targetdirectories=[Locations().currentdirectory,
                       Locations().get_plotspath(),
                       Locations().get_controlsdirectory()]

    changed=[]
    for tdir in targetdirectories:
        if os.path.exists(tdir):
            LOG.info("looking in {}".format(tdir))
            for original,changed in rrf:
                LOG.info("looking for {} to change to {}"
                         .format(original,changed))
                n_changes=len(bulkrename(tdir,original,changed,
                                         dig=True,
                                         includedatabases=False,
                                         countonly=True))
                if n_changes:
                    mess=("Will rename {} files in {} with "
                          "{} replaced with {}. Proceed?"
                          .format(n_changes,tdir,original,changed))
                    LOG.info(mess)
                    goahead=raw_input(mess)
                    if goahead.lower().startswith("y"):
                        results=bulkrename(tdir,original,changed,
                                           dig=True,
                                           includedatabases=False,
                                           countonly=False)
                        changed+=results
                    
#    if changed:
#        aftercheck=raw_input("Have renamed {} files in {}. Undo?"
#                             .format(len(changed),
#                                     ', '.join(targetdirectories)))
#        if aftercheck.lower().startswith("y"):
#            undorename()
