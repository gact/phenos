#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
"""

################################################################################

import os, sys
from phenos import *
import logging

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.1"

global LOG
LOG=logging.getLogger()
LOGLEVEL=logging.INFO#DEBUG

def revert(individualonly=True):
    """
    NOT WORKING BECAUSE DB.FILEOB.CLOSE() DOESN'T SEEM TO BE HAPPENING
    """
    if individualonly:
        dbases=[Locations().get_individualdbase()]
    else:
        dbases=[Locations().get_individualdbase(),
               Locations().get_shareddbase(),
               Locations().get_controlsdbase()]
    for db in dbases:
        rootpath,name=os.path.split(db.filepath)
        basename,extension=os.path.splitext(name)
        backuppath=os.path.join(rootpath,basename+".backup")
        if os.path.exists(backuppath):
            try:
                db.fileob.close()
            except Exception as e:
                LOG.error("unable to close db {} because {}"
                          .format(db.filepath,e))
            try:
                os.remove(db.filepath)
            except Exception as e:
                LOG.error("unable to remove db {} because {}"
                          .format(db.filepath,e))
            try:
                os.rename(backuppath,db.filepath)
                LOG.info("renamed {} to {}"
                          .format(backuppath,db.filepath))
            except Exception as e:
                LOG.error("unable to rename {} to {} because {}"
                          .format(backuppath,db.filepath,e))
#
if __name__=="__main__":
    setup_logging()
    sys.excepthook=log_uncaught_exceptions
    revert()
    answer=raw_input("Hit ENTER to close")
