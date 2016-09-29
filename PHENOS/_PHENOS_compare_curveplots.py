#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
Works out what folder it's in, what the database name should be,
and calls the primary functions with that information
"""

################################################################################

import os, sys
from phenos import *
import logging

################################################################################

filename = os.path.basename(__file__)
authors = ("Dave B. H. Barton")
version = "0.2"

global LOG
LOG=logging.getLogger()
LOGLEVEL=logging.INFO#DEBUG
#
def yield_subdirectorypaths(directory):
    for subpath in os.listdir(directory):
        if os.path.isdir(os.path.join(directory,subpath)):
            yield os.path.join(directory,subpath)

def yield_filepaths(directory):
    for path in os.listdir(directory):
        fullpath=os.path.join(directory,path)
        if os.path.isfile(fullpath):
            #print "#",fullpath
            yield fullpath
#
if __name__=="__main__":
    """
    e.g. "D:\PHENOS2\Plots\Majed\MA11ab 'FS401-596 384.xlsx' () Ethanol 10%\CurvePlot MA11ab FS401-596 384.xlsx (Ethanol 10%) rawmeasuredvalues , colored by platedmass.jpg"
    plotspath="D:\PHENOS2\Plots\"
    userfolder="Majed\"
    experimentfolder="MA11ab 'FS401-596 384.xlsx' () Ethanol 10%\"
    plotname="CurvePlot MA11ab FS401-596 384.xlsx (Ethanol 10%) rawmeasuredvalues , colored by platedmass.jpg"
    curveplotfolder="D:\PHENOS2\Plots\_All_CurvePlots\"
    destinationfolderpath="D:\PHENOS2\Plots\_All_CurvePlots\Majed"
    newpath="D:\PHENOS2\Plots\_All_CurvePlots\Majed\CurvePlot MA11ab FS401-596 384.xlsx (Ethanol 10%) rawmeasuredvalues , colored by platedmass.jpg"
    """
    setup_logging()
    sys.excepthook=log_uncaught_exceptions
    
    plotspath=Locations()["plots"]
    curveplotfolder=os.path.join(plotspath,"_All_CurvePlots")

    for userfolderpath in yield_subdirectorypaths(plotspath):
        X,userfolder=os.path.split(userfolderpath)
        if userfolder.startswith("_"):
            LOG.info("ignoring {} as starts with '_'".format(userfolder))
        else:
            LOG.debug("userfolderpath: {}".format(userfolderpath))
            destinationfolderpath=os.path.join(curveplotfolder,userfolder)
            if not os.path.exists(destinationfolderpath):
                os.makedirs(destinationfolderpath)
            for experimentfolderpath in yield_subdirectorypaths(userfolderpath):
                Y,experimentfolder=os.path.split(experimentfolderpath)
                LOG.debug("experimentfolderpath: {}".format(experimentfolderpath))
                for filepath in yield_filepaths(experimentfolderpath):
                    Z,filename=os.path.split(filepath)
                    LOG.debug("filepath: {}".format(filepath))
                    #checks
                    if filename.startswith("5_Curves"):
                        if "rawmeasuredvaluesminusagar" in filename:
                            newpath=os.path.join(destinationfolderpath,filename)
                            if not os.path.exists(newpath):
                                shutil.copy(filepath,newpath)
                                LOG.info("copy created: {}".format(filename))
    subprocess.Popen('explorer "{}"'.format(curveplotfolder))