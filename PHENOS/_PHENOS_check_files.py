#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
"""

################################################################################

import os, sys
import pprint
from phenos import *

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.1"
#

if __name__=="__main__":
    setup_logging("INFO")
    sys.excepthook=log_uncaught_exceptions

    LOG.info("checking new files in {} for errors".format(Locations().currentdirectory))

    found_paths=[os.path.normpath(p) for p in Files().get_dmonitor()]
    stored_files=[f for f in Files()]
    stored_paths=[f["filepath"].norm() for f in Files()]
    stored_dict=dict(zip(stored_paths,stored_files))
    new_paths=[p for p in found_paths if p not in stored_paths]

    passed={}
    failed={}
    LOG.info("{} new files found".format(len(new_paths)))
    def MULTILOG(f,E):
        LOG.warning(E)
        f.errorlist.append(E)
        failed[f.value]=f

    for newpath in new_paths:
        LOG.info("checking {}".format(newpath))
        f=File(filepath=newpath)
        f["platelayout"].calculate()
        f.calculate_all()
        f.errorlist=[]
        if not f["platelayout"].is_readable():
            MULTILOG("problem with {}: platelayout {} isn't readable"
                     .format(os.path.basename(newpath),
                             f["platelayout"].value))
        
        FNP=f.filenamereader.properties
        for field in ['layout','user','fileletter',
                      'experimentnumber','treatment']:
            if not FNP.get(field,None):
                MULTILOG("problem with {}: {} field isn't readable"
                         .format(os.path.basename(newpath),field))
        if f["fileid"].value in Files():
            MULTILOG("problem with {}: file called {} already in Files()"
                     .format(os.path.basename(newpath),f["fileid"].value))
        readresult=f.read(store=False)
        if not readresult:
            MULTILOG("problem with {}: can't be read"
                     .format(os.path.basename(newpath)))

        if f.value not in failed:
            LOG.info("{} looks fine: {}".format(f.value,f))
            passed[f.value]=f
    
    lastlogpath=Locations().get_last_log(openfolder=False)
    open_on_Windows(lastlogpath)