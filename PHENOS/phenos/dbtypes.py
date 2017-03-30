#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""

"""
#STANDARD LIBRARY
import os,sys,platform,shutil,copy,re,csv
import logging,ConfigParser,traceback,colorsys
import time,subprocess,urllib2
from datetime import datetime
from collections import defaultdict,Counter
from itertools import combinations,izip,chain,product
from math import ceil
from string import Formatter
from random import shuffle
#OTHER
import win32com.client
import xlrd
import tables as tbs
import numpy as np
from scipy.stats import ttest_ind, norm, ttest_ind, levene
import brewer2mpl
import matplotlib.pyplot as pyplt
import matplotlib.cm as clrmap
import matplotlib.pylab as pylab
from matplotlib import animation,colors,patches,ticker
#phenos
from core import *
from graphics import *
from gui import browse
#
try:
    if sys.platform.startswith("win"):
        os.environ["R_USER"] = "localadmin1"
    import rpy2.robjects as ro
    from rpy2.robjects.packages import importr
    import rpy2.robjects.numpy2ri as rpyn
    hasrqtl=True
    R=ro.r
    R('library(qtl)')
except:
    hasrqtl=False

try:
    import Bio
    hasbiopython=True
except:
    hasbiopython=False

# #############################################################################

filename=os.path.basename(__file__)
authors=("David B. H. Barton")
version="2.7"

usecontrolsdatabase=True
shareddbasenameroot="_phenos_shared_database"

#
def recurse_through_filereadertypes(cls,filepath,
                                    passerrorsto=None,report=False):
    if cls.__subclasses__()==[]:
        #then bottom of tree and can check and return itself
        if cls.include_in_format_search:
            inst=cls(filepath,passerrorsto=passerrorsto)
            if inst.is_correct_format(report=report):
                #print "{} says YES!".format(cls)
                return inst
            else:
                #print "{} says no.".format(cls)
                return None
    else:
        #print "{} asking subclasses to check themselves".format(cls)
        matching_formatparsers=[]
        for subclass in cls.__subclasses__():
            
            answer=recurse_through_filereadertypes(subclass,filepath)
            
            if answer is not None:
                matching_formatparsers.append(answer)
        if len(matching_formatparsers)>1:
            if report:
                LOG.debug("{}: multiple matching formats: {}"
                          .format(cls.__name__,matching_formatparsers))
            return matching_formatparsers
        elif len(matching_formatparsers)==0:
            return None
        else:
            return matching_formatparsers[0]

def find_format_of(filepath,
                   passerrorsto=None,report=False):
    """
    >>> testfilename="EX4a (YPD) [Basic384] t-1 (DATParserWithoutTemp).csv"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
    >>> r=find_format_of(testfilepath)
    >>> print r.__class__.__name__
    DATReaderWithoutTemp
    """
    extension=os.path.splitext(filepath)[-1]
    if extension==".xlsx": cls=_XlsxReader
    elif extension==".DAT": cls=_DATReader
    elif extension==".csv":
        tried=recurse_through_filereadertypes(_DATReader,filepath,
                                              passerrorsto=passerrorsto,
                                              report=report)
        if tried is not None: return tried
        tried=recurse_through_filereadertypes(_CsvReader,filepath,
                                              passerrorsto=passerrorsto,
                                              report=report)
        if tried is not None: return tried
    return recurse_through_filereadertypes(_FileReader,filepath,
                                           passerrorsto=passerrorsto,
                                           report=report)

def read_data_file(filepath):
    parser=find_format_of(filepath)
    shareddata,rowdata=parser.parse()
    allmeasures=[]
    for row in rowdata:
        allmeasures+=list(row["measurements"])
    shareddata["minimummeasure"]=min(allmeasures)
    shareddata["maximummeasure"]=max(allmeasures)
    shareddata["finishedtime"]=os.path.getmtime(filepath)
    shareddata["extension"]=os.path.splitext(filepath)[-1]
    difftime=shareddata["finishedtime"]-shareddata["exp_datetime"]
    shareddata["runtime_hours"]=difftime/3600.0
    return shareddata,rowdata

def originalfilename_from_shareddata(shareddata):
    """
    e.g. os.path.join(platereader_output,"Ab384-emptyplate_160422_1722.csv")
    """
    DT=time.strftime("%y%m%d_%H%M",time.localtime(shareddata["finishedtime"]))
    return "{}_{}{}".format(shareddata["platereaderprogram"],
                            DT,
                            shareddata["extension"])

def split_records_by_rQTLgroup(ob):
    if not hasattr(ob,"records_by_rQTLgroup"):
        ob.records_by_rQTLgroup=defaultdict(list)
        for cr in ob.yield_records():
            rqg=cr["rqtlgroup"].value
            ob.records_by_rQTLgroup[rqg].append(cr)
    return ob.records_by_rQTLgroup

def screen_records(records,remove_ignore=True,**kwargs):
    screened=[]
    skipnoalleles=kwargs.setdefault("skipnoalleles",True)
    for r in records:
        SIG=r.should_ignore()
        if remove_ignore and SIG:
            LOG.debug("ignoring record {} ({})".format(r.value,SIG))
            continue
        if skipnoalleles:
            if r.alleles() in [None,False,[]]:
                LOG.debug("no alleles found for {}".format(r.value))
                continue
        screened.append(r)
    return screened

def copydatato(experimentid,targetfolder=None,
               datafiles='copy',
               plotfiles='shortcut',
               dbaseobs='copy',
               report=True):
    if targetfolder is None:
        targetfolder=os.path.split(Locations().get_userpath()+"_ok")[-1]
    CF=CombiFiles()[experimentid]
    if not CF:
        LOG.critical("can't find experimentid {} in {}"
                     .format(experimentid,Locations().currentdbasepath))
        return False
    datasourcepath=Locations().get_userpath()
    
    subfoldername=CF.get_subfoldername()
    plotssourcefolder=os.path.join(Locations().get_plotspath(),
                                   subfoldername)
    datatargetfolder=os.path.join(Locations()["datafiles"],targetfolder)
    prepare_path(datatargetfolder)
    plotstargetfolder=os.path.join(Locations()["plots"],targetfolder,
                                   subfoldername)
    prepare_path(plotstargetfolder)
    #
    #Copy data files
    newfilestostore=[]
    newreadingstostore=[]
    for FL in CF.yield_sourcefiles():
        FL2=FL.copy_in_other_folder(targetfolder)
        datafilepath=FL["filepath"].get_fullpath()
        targetfilepath=FL2["filepath"].get_fullpath()
        if datafiles=='copy':
            copy_to(datafilepath,targetfilepath,report=report)
        elif datafiles=='shortcut':
            FN=os.path.basename(targetfilepath)
            shortcutname="~{}.lnk".format(os.path.splitext(FN)[0])
            shortcutpath=os.path.join(datatargetfolder,shortcutname)
            create_Windows_shortcut(targetfilepath,
                                    shortcutpath,
                                    report=report)

        newfilestostore.append(FL2)
        newreadingstostore+=[c.copy_in_other_folder(targetfolder)
                             for c in FL.yield_records()]

    newcombifilestostore=[CF.copy_in_other_folder(targetfolder)]
    newcombireadingstostore=[c.copy_in_other_folder(targetfolder)
                             for c in CF.yield_records()]
    #Copy Plots
    if plotfiles=='copy':
        copy_contents_to(plotssourcefolder,plotstargetfolder,report=report,
                         ignore=[".lnk"])
        #Recreate datafiles>plots shortcut
        shortcutpath=os.path.join(plotstargetfolder,
                                  "~{}.lnk".format(targetfolder))
        create_Windows_shortcut(datatargetfolder,
                                shortcutpath,
                                report=report)

        #Recreate plots>datafiles shortcut
        shortcutpath=os.path.join(datatargetfolder,
                                  "~{}.lnk".format(subfoldername))
        create_Windows_shortcut(plotstargetfolder,
                                shortcutpath,
                                report=report)
    elif plotfiles=='shortcut':
        shortcutpath=os.path.join(datatargetfolder,
                                  "~{}.lnk".format(os.path.split(plotssourcefolder)[-1]))
        create_Windows_shortcut(plotssourcefolder,
                                shortcutpath,
                                report=report)

    #Copy CF, File and readings to new db
    if dbaseobs=='copy':
        Files(targetfolder).store_many_record_objects(newfilestostore)
        Readings(targetfolder).store_many_record_objects(newreadingstostore)
        CombiFiles(targetfolder).store_many_record_objects(newcombifilestostore)
        CombiReadings(targetfolder).store_many_record_objects(newcombireadingstostore)

def combidict(*obs):
    """
    Returns a dictionary of atom values shared by all obs
    """
    output=defaultdict(list)
    headers=[]
    for ob in obs:
        for k in ob.keys():
            if k not in headers:
                headers.append(k)
    for h in headers:
        for ob in obs:
            try:
                atm=ob[h]
                if atm.is_valid():
                    if atm.value not in output[h]:
                        output[h].append(atm.value)
            except:
                pass
    return output

def convert_to_cell_count(reading):
    """
    Determined empirically from experiments in which platereader readings
    were compared to haemocytometer cell counts.
    """
    R=reading
    e=math.e
    return 54927*(e**(1.83924751759787*R))

def diagnostics():
    warnings=[]
    for dp in Locations().datpaths:
        dbasenameroot=os.path.basename(dp)
        warnings+=Files().diagnostics()
    print warnings

#LOCATIONS ####################################################################

class Locations(object):
    """
    Singleton class that detects and stores all key file folders for easy access
    e.g. Locations["datafiles"]: "PHENOS2/Data files"
         Locations["layouts"]:  "PHENOS2/Layouts"
         Locations[0]:          "PHENOS2/Dat files/Experiment1"
    Also ensures that all paths exist and create them if not
    """
    _shared_state={}
    subfolderlookup={"datafiles":"Data files",
                     "genotypes":"Genotypes",
                     "layouts":"Layouts",
                     "logs":"Logs",
                     "plots":"Plots",
                     "rqtlinput":"rQTL input",
                     "stingerfiles":"Stinger files"}
    cursorfilename="_current_directory.txt"

    scriptdir=os.path.dirname(os.path.realpath(sys.argv[0]))
    rootdirectory=None
    userfolders=[]
    userdbases={}
    mainlocs=[]
    currentuserfolder=None
    currentuserdbasepath=None
    currentuserdbase=None
    shareddbase=None
    graphicstype="jpg"

    def __init__(self,userfolder=None):
        self.__dict__ = self._shared_state
        if Locations.rootdirectory is None:
            self.get_config_info()
        self.get_userfolders()
        if userfolder is not None:
            self.set_userfolder(userfolder)

    def get_config_dict(self):
        if not hasattr(Locations,"configdict"):
            Locations.configdict=get_config_dict()
        return Locations.configdict

    def get_config_info(self):
        CD=self.get_config_dict()
        Locations.config_filepath=CD["config_filepath"]
        Locations.configparser=CD["configparser"]
        try:
            Locations.platereader_output=CD["source_directory"]
        except:
            LOG.critical("No platereader_output directory defined")
            sys.exit()
        Locations.rootdirectory=CD["target_directory"]
        Locations.currentuserfolder=CD["user_folder"]
        Locations.graphicstype=CD["graphicstype"]
        Locations.windowposition=CD["windowposition"]
        return Locations.configparser

    def find_mainlocs(self):
        mainlocs=[]
        for mainloc in Locations.subfolderlookup.values():
            mainlocs.append(os.path.join(Locations.rootdirectory,
                                         mainloc))
        Locations.mainlocs=mainlocs
        return Locations.mainlocs

    def get_userfolders(self):
        userfolders=[]
        for userfolder in os.listdir(self["datafiles"]):
            userfolderpath=self.userfolder_to_userpath(userfolder)
            if os.path.isdir(userfolderpath):
                userfolders.append(userfolder)
        Locations.userfolders=userfolders
        return Locations.userfolders

    def get_dbase(self,userfolder=None,reload=False):
        if userfolder==shareddbasenameroot:
            if reload or not Locations.shareddbase:
                filepath=os.path.join(Locations.rootdirectory,
                                      "_{}.h5".format(userfolder))
                Locations.shareddbase=DBase(filepath)
            return Locations.shareddbase
        
        if userfolder is None:
            userfolder=Locations.currentuserfolder
        
        if userfolder not in Locations.userfolders:
            LOG.error("Can't find user folder '{}' so creating it"
                      .format(userfolder))
            self.set_userfolder(userfolder,create=True)
        
        if reload:
            if userfolder in Locations.userdbases:
                del Locations.userdbases[userfolder]
        
        if userfolder not in Locations.userdbases:
            DIR=self.get_dbasedir(userfolder)
            pth=os.path.join(DIR,"_{}.h5".format(userfolder))
            Locations.userdbases[userfolder]=DBase(pth)
        return Locations.userdbases[userfolder]

    def get_dbasedir(self,userfolder):
        if userfolder==shareddbasenameroot:
            DIR=Locations.rootdirectory
        else:
            DIR=os.path.join(self["datafiles"],userfolder)
        return DIR

    def get_plotspath(self):
        pp=os.path.join(self["plots"],Locations.currentuserfolder)
        prepare_path(pp)
        return pp

    def get_emptyplatespath(self):
        pp=os.path.join(self["plots"],"Empty plate plots")
        prepare_path(pp)
        return pp

    def get_newlogpath(self):
        pp=os.path.join(self["logs"],
                        "phenos{}.log"
                        .format(time.strftime("%y%m%d%H%M%S")))
        return pp

    def get_last_log(self,openfolder=False):
        logfolder=self["logs"]
        if openfolder:
            open_on_Windows(logfolder)

        sortedlogs=[]
        for f in os.listdir(logfolder):
            fpath=os.path.join(logfolder,f)
            sortedlogs.append((os.path.getctime(fpath),fpath))
        sortedlogs.sort()
        return sortedlogs[-1][-1]

    def __exit__(self,type=None,value=None,traceback=None):
        if Locations.currentuserdbase:
            try:
                Locations.currentuserdbase.fileob.close()
            except Exception as e:
                LOG.warning("couldn't properly shut Locations.currentdbase")
            Locations.currentuserdbase=None
        if Locations.shareddbase:
            try:
                Locations.shareddbase.fileob.close()
            except Exception as e:
                LOG.warning("couldn't properly shut Locations.shareddbase")
            Locations.shareddbase=None

    def __getitem__(self,key):
        key=key.lower().replace(" ","")
        if key in Locations.subfolderlookup:
            fullpath=os.path.join(Locations.rootdirectory,
                                  Locations.subfolderlookup[key])
        elif key in self.get_userfolders():
            fullpath=os.path.join(Locations.rootdirectory,
                                  Locations.subfolderlookup["datafiles"],
                                  key)
        fullpath=check_path(fullpath)
        prepare_path(fullpath)
        return fullpath

    def __str__(self):
        output=[Locations.rootdirectory]
        output+=Locations.userfolders
        output+=["> "+Locations.currentuserfolder]
        return os.linesep.join(output)
        return output
#
    def userfolder_to_userpath(self,userfolder):
        return os.path.join(self["datafiles"],userfolder)

    def set_userfolder(self,userfolder,create=False):
        if userfolder==Locations.currentuserfolder:
            return True
        if userfolder not in self.get_userfolders():
            if create:
                self.add_new_userfolder(userfolder,setfolder=False)
            else:
                previoususerfolder=userfolder
                userfolder="Test"
                LOG.error("Can't find userfolder {} "
                          "so setting to Software Test"
                          .format(previoususerfolder,userfolder))
        #
        Locations.currentuserfolder=userfolder
        Locations.configparser.set('Locations', 'user_folder', userfolder)
        self.write_to_config()

    change=set_userfolder

    def write_to_config(self):
        with open(Locations.config_filepath,'w') as configfile:
            Locations.configparser.write(configfile)

    def add_new_userfolder(self,newname,setfolder=True):
        """
        """
        copyfolderpath=os.path.join(self["datafiles"],"New folder")
        newpath=self.get_userpath(newname)
        if not os.path.exists(copyfolderpath):
            os.makedirs(copyfolderpath)
        if newname in Locations.userfolders:
            LOG.error("{} already exists".format(newpath))
            return None
        else:
            try:
                copy_contents_to(copyfolderpath,newpath,report=True)
                Locations.userfolders.append(newname)
                LOG.info("created new data folder {}"
                          .format(newname))
                if setfolder:
                    self.set_userfolder(newname)
                return newpath
            except Exception as e:
                LOG.error("couldn't create new data folder {} because {} {}"
                          .format(newname,e,get_traceback()))
                return None

    def get_userpath(self,userfolder=None):
        if userfolder is None:
            userfolder=Locations.currentuserfolder
        return os.path.join(self["datafiles"],userfolder)

    def yield_userpaths(self):
        for f in Locations.userfolders:
            yield self.get_userpath(f)
#

class GraphicGenerator(object):
    pathformatter="{plotfolder}/{userfolder}/{experimentfolder}/{prefix}{graphicsnameroot}{suffix}.{extension}"
    def preparseformat(self,formatstring):
        """
        Retrieves, as a dictionary, only the terms required by the
        formatstring, and checks that values are returned for each,
        even by atoms
        """
        output={}
        for l in Formatter().parse(formatstring):
            field=l[1]
            try:
                result=self.__getitem__(field,report=False)
                output[field]=ATOMORNOT(result)
            except:
                pass
        return output

    def get_subfoldername(self,**kwargs):
        """
        e.g.
        MA5ab 'TW201-296a 384.xlsx' (MA test 5) YPD
        """
        if not hasattr(self,"subfoldername"):
            formatstring=self.subfoldernameformat
            formatdict=self.preparseformat(formatstring)
            self.subfoldername=formatstring.format(**formatdict)
            self.subfoldername.replace("/","~")
        return self.subfoldername

    def get_plotssubfolderpath(self,root=None):
        if root is None:
            root=Locations().get_plotspath()
        return os.path.join(root,self.get_subfoldername())

    def get_graphicsnameroot(self,**kwargs):
        """
        e.g.
        CurvePlot MA5ab TW201-296a 384.xlsx (YPD) colored by platedmass.jpg
                  --------nameroot---------------
        Central part 
        """
        if not hasattr(self,"graphicsnameroot"):
            formatstring=kwargs.get("namerootformatter",
                                    self.graphicsnamerootformat)
            formatdict=self.preparseformat(formatstring)
            formatdict.update(kwargs)
            self.graphicsnameroot=formatstring.format(**formatdict)
            self.graphicsnameroot.replace("/","~")
        return self.graphicsnameroot

    def get_graphicstitle(self,**kwargs):
        titleformatstring=kwargs.get("titleformatstring",self.titleformat)
        TFD=self.preparseformat(titleformatstring)
        TFD.update(kwargs)
        kwargs=TFD
        kwargs.setdefault("graphicsnameroot",self.get_graphicsnameroot())
        kwargs.setdefault("prefix",None)
        kwargs.setdefault("suffix",None)
        if "prefix" in kwargs:
            if kwargs["prefix"] is None:
                kwargs["prefix"]=""
            else:
                kwargs["prefix"]=kwargs["prefix"].strip()+" "
        if "number" in kwargs:
            if kwargs["number"] is not None:
                kwargs["prefix"]="{}_{}".format(kwargs["number"],
                                                kwargs["prefix"])
        if "suffix" in kwargs:
            if kwargs["suffix"] is None:
                kwargs["suffix"]=""
            else:
                kwargs["suffix"]=" "+kwargs["suffix"].strip()
        try:
            return os.path.normpath(titleformatstring.format(**kwargs))
        except Exception as e:
            LOG.error("unable to format graphicstitle for {} because {} {}"
                      .format(self.value,e,get_traceback()))
            return False

    def get_graphicspath(self,**kwargs):
        pathformatter=kwargs.get("pathformatter",self.pathformatter)
        kwargs.setdefault("plotfolder",Locations()["plots"])
        CD=Locations().get_userpath()
        kwargs.setdefault("userfolder",os.path.split(CD)[-1])
        kwargs.setdefault("experimentfolder",self.get_subfoldername())
        kwargs.setdefault("graphicsnameroot",self.get_graphicsnameroot())
        kwargs.setdefault("extension",Locations.graphicstype)
        kwargs.setdefault("prefix",None)
        kwargs.setdefault("suffix",None)
        
        if "prefix" in kwargs:
            if kwargs["prefix"] is None:
                kwargs["prefix"]=""
            else:
                kwargs["prefix"]=kwargs["prefix"].strip()+" "
        if "number" in kwargs:
            if kwargs["number"] is not None:
                kwargs["prefix"]="{}_{}".format(kwargs["number"],
                                                kwargs["prefix"])
        if "suffix" in kwargs:
            if kwargs["suffix"] is None:
                kwargs["suffix"]=""
            else:
                kwargs["suffix"]=" "+kwargs["suffix"].strip()
        try:
            return os.path.normpath(pathformatter.format(**kwargs))
        except Exception as e:
            LOG.error("unable to format graphicspath for {}: {}"
                      .format(self.value,e))
            return False
        """
        e.g.
        D:\PHENOS2\Plots\     Majed\                          MA5ab 'TW201-296a 384.xlsx' (MA test 5) YPD\                        CurvePlot MA5ab TW201-296a 384.xlsx (YPD) colored by platedmass.jpg
        D:\PHENOS2\Plots\     Majed\                          MA5ab 'TW201-296a 384.xlsx' (MA test 5) YPD\    ReplicatePlots\     ReplicatePlot TW203, CombiFile MA5ab TW201-296a 384.xlsx (YPD).jpg
        D:\PHENOS2\Plots\     Majed\_Strain_plots\                                                                                Strain FS002 across multiple experiments (colorby=treatment).jpg
        D:\PHENOS2\Plots\           _All_CurvePlots\Majed\                                                                        CurvePlot MA3ab TW201-296a 384.xlsx (YPD) rawmeasuredvalues , colored by platedmass.jpg
        D:\PHENOS2\Plots\           _Empty plate views\Majed\                                                                     EmptyPlate MA1a (MA test 1) TW201-296a 384.xlsx (YPD) empty readings local.jpg
        """


#FILEREADERS ##################################################################
class ReadingFileNameReader(object):
    """
    If filenames follow this pattern then key experimental information
    can be automatically extracted from them:
    e.g. DB4a (YPD) [FS1536]R {FS101=contaminated} St-1 (divider v2.1 test).DAT
         aabc (ddd) [eeeeee]f gggggggggggggggggggg hiii (jjjjjjjjjjjjjjjjj)
     a... (Optional) user initials (1-5 letters only)
     b... (Required) experiment number
     c... (Required) experiment subID (single letter unique to each file that is part of
                                       the same experiment number)
     d... (Required) treatment (numbers or letters in brackets)
     e... (Required) layout (in square brackets, the filename of the file in
                             the Layouts folder. The extension isn't needed.
                             Single quotes can be used for legacy reasons.
                             Pingrid patterns (e.g. '0XX,1XX,2XX,3XX')
                             are no longer supported).
     f... (Optional) 'R' indicates the plate was put in the reader the wrong way up and
                            data must be rotated 180 degrees, or nothing
     g... (Optional) flags (in curly braces, with wellnames/strainnames (multiple can
                            be comma-separated), linked to flag text by = sign
                            (multiple pairs of id=flag can be semicolon-separated, e.g.
                                {FS101,FS102=missing;A12=contaminated}
     h... (Optional) 'S' indicates a survivor experiment, or nothing
     i... (Optional) time offset (t+24 adds 24 hrs to each timepoint therein, whereas
                                 t-1 indicates empty readings taken before any cells have been added
                                 If blank or t+0, timepoints are taken at face value)
     j... (Optional) note (additional key info about the experiment; in brackets, containing
                          any amount of letters, numbers or filename-compatible symbols)

    >>> r=ReadingFileNameReader("TEST35g (MMS 0.04%) ['ExampleLayout.csv'] t+25 (DATParserWithoutTemp).DAT")
    >>> print r["user"]
    TEST
    >>> print r["layout"]
    'ExampleLayout.csv'
    """
    filenameregexes=[re.compile("^(?P<user>\D*)\d+.*"),
                     re.compile("^\D*(?P<experimentnumber>\d+).*"),
                     re.compile("^\D*\d+(?P<fileletter>\D?).*"),
                     re.compile("^.*\((?P<treatment>.*)\)[ _]\[.*"),
                     re.compile("^.*\[(?P<layout>.*)\].*"),
                     re.compile("^.*\](?P<reorient>R).*"),
                     re.compile("^.*\]R? ?{(?P<flags>.*)}.*"),
                     re.compile("^.* S[tT](?P<survivorstart>\d*)[-+].*"),
                     re.compile("^.*S?[tT]\d*(?P<timeoffset>[-+]\d+).*"),
                     re.compile("^.* \((?P<note>.*)\)\.\D{1,5}$"),
                     re.compile("^.*(?P<extension>\.\D{1,5})$")]
    keyproperties=["experimentnumber",
                   "fileletter",
                   "treatment",
                   "layout"]

    def __init__(self,path,passerrorsto=None):
        """
        >>> r=ReadingFileNameReader("TEST35g (MMS 0.04%) ['ExampleLayout.csv'] t+25 (DATParserWithoutTemp).DAT")
        >>> print r.properties
        {'note': 'DATParserWithoutTemp', 'layout': "'ExampleLayout.csv'", 'user': 'TEST', 'extension': '.DAT', 'timeoffset': 25, 'fileletter': 'g', 'experimentnumber': 35, 'treatment': 'MMS 0.04%'}
        """
        if passerrorsto is not None:
            self.passerrorsto=passerrorsto
        self.path=path
        self.properties=self._build_dictionary_from_filepath()
        self.properties=self._type_conversions()

    def __str__(self):
        """
        >>> r=ReadingFileNameReader("TEST35g (MMS 0.04%) ['ExampleLayout.csv'] t+25 (DATParserWithoutTemp).DAT")
        >>> print str(r)        #or just >>> print r
        {'note': 'DATParserWithoutTemp', 'layout': "'ExampleLayout.csv'", 'user': 'TEST', 'extension': '.DAT', 'timeoffset': 25, 'fileletter': 'g', 'experimentnumber': 35, 'treatment': 'MMS 0.04%'}
        """        
        if hasattr(self,"properties"):
            return str(self.properties)
        else:
            return "{}({})".format(self.__class__.__name__,self.path)

    def __contains__(self,value):
        """
        >>> r=ReadingFileNameReader("TEST35g (MMS 0.04%) ['ExampleLayout.csv'] t+25 (DATParserWithoutTemp).DAT")
        >>> print 'note' in r
        True
        >>> print 'reorient' in r
        False
        """
        return value in self.properties

    def __getitem__(self,value):
        """
        >>> r=ReadingFileNameReader("TEST35g (MMS 0.04%) ['ExampleLayout.csv'] t+25 (DATParserWithoutTemp).DAT")
        >>> print r['extension']
        .DAT
        """
        return self.properties[value]

    def __len__(self):
        return len(self.properties)

    def _build_dictionary_from_filepath(self):
        directories,filename=os.path.split(self.path)
        output={}
        self.not_OK=False
        for regex in self.filenameregexes:
            matches=[m.groupdict() for m in regex.finditer(filename)]
            patternname=list(regex.groupindex)[0]
            if matches==[]:
                if patternname in self.keyproperties:
                    LOG.error("FileNameReader: '{}' has no recognizable '{}' "
                              "field"
                              .format(self.path,patternname))
                    self.not_OK=True
            else:
                for match in matches:
                    output.update(match)
        if self.not_OK:
            self.is_OK=False
        else:
            self.is_OK=True
        return output

    def _process_flags(self,flagsstring):
        """
        e.g. "FS101,A12=missing;FS159=contaminated"
        """
        output={}
        section1=flagsstring.split(";")
        for s1 in section1:
            section2=s1.split("=")
            cells=section2[0].split(",")
            if len(section2)==1:
                reason="unspecified"
            else:
                reason=section2[1]
            for cell in cells:
                output[cell]=reason
        return output

    def _type_conversions(self):
        output=self.properties
        #type conversions
        if "timeoffset" in output:
            output["timeoffset"]=int(output["timeoffset"])
            if output["timeoffset"]==-1:
                del output["timeoffset"]
                output["emptyreading"]=True
        else:
            output["timeoffset"]=0
        if "experimentnumber" in output:
            output["experimentnumber"]=int(output["experimentnumber"])
        if "reorient" in output:
            if output["reorient"]=="R":
                output["reorient"]=True
        if "survivorstart" in output:
            output["issurvivor"]=True
            if "survivors" not in output["treatment"]:
                output["treatment"]=output["treatment"]+" survivors"
            if output["survivorstart"] not in [None,""]:
                output["survivorstart"]=int(output["survivorstart"])
            else:
                output["survivorstart"]=0
        if "flags" in output:
            output["flags"]=self._process_flags(output["flags"])
        return output

    def get_is_OK(self):
        return self.is_OK

class GenotypeFileNameReader(ReadingFileNameReader):
    """
    DEPRECATED
    >>> g=GenotypeFileNameReader("FS001-096 AS.csv")
    >>> print g
    {'extension': '.csv', 'samplestart': '001', 'crosscode': 'AS', 'externalprefix': 'FS', 'timeoffset': 0, 'sampleend': '096'}
    """
    #filenameregexes=[re.compile("^(?P<samplestart>\d\d\d)-"),
    #                 re.compile("^.*-(?P<sampleend>\d\d\d) "),
    #                 re.compile("^.* (?P<crosscode>\D\D).csv$")]
    filenameregexes=[re.compile("^(?P<externalprefix>\D*).*$"),
                     re.compile("^\D*(?P<samplestart>\d*)-.*$"),
                     re.compile("^.*-(?P<sampleend>\d*) .*$"),
                     re.compile("^.* (?P<crosscode>\D*)\..*$"),
                     re.compile("^.*(?P<extension>\.\D+)$")]
    keyproperties=["samplestart","sampleend","crosscode"]

class rQTLFileNameReader(ReadingFileNameReader):
    """
    e.g. rQTL TS1abc (YPD) FS001-096 (AS) IT SR.csv
    """
    filenameregexes=[re.compile("^rQTL (?P<combifileid>\w*\d+\w+) .*\.csv$"),
                     re.compile("^rQTL \w*\d+\w+ \((?P<treatment>[ \w]+)\).*\.csv$"),
                     re.compile("^rQTL \w*\d+\w+ \([ \w]+\) (?P<strainrange>.*) \(\w*\).*\.csv$"),
                     re.compile("^rQTL \w*\d+\w+ \([ \w]+\)[^\(\)]*\(?(?P<alleleset>\w*)\)?.*\.csv$"),
                     re.compile("^rQTL .*(?P<individualtimepoints>IT).*\.csv$"),
                     re.compile("^rQTL .*(?P<separatereplicates>SR).*\.csv$")]
    keyproperties=[]

    def _type_conversions(self):
        return self.properties

class rQTLFileNameReader2(ReadingFileNameReader):
    """
    e.g. 'rQTL MA100ab_TS10ab AS+AE01fc 384 (Levulinic acid 1%) TR(15.8hrs+-0.5),AWA(15.8hrs+-0.5) AE01fc.hdf5'
    """
    filenameregexes=[re.compile("^rQTL (?P<controlledexperimentid>\w*\d+\w+) .*$"),
                     re.compile("^rQTL (?P<combifile>\w*\d+\w+)_.*$"),
                     re.compile("^rQTL \w* (?P<layout>.+) \(.*$"),
                     re.compile("^rQTL .* \((?P<treatment>[^)]+)\).*$"),
                     re.compile("^rQTL .* (?P<genotypegroup>\w*)\..+$")]
    keyproperties=[]

    def _type_conversions(self):
        return self.properties

class PlateCheckFileNameReader(ReadingFileNameReader):
    """
    NOT FULLY IMPLEMENTED
    >>> p=PlateCheckFileNameReader("'FS1536b.xlsx'.DAT")
    >>> print p
    {'timeoffset': 0, 'layoutfile': 'FS1536b.xlsx', 'extension': '.DAT'}
    """
    filenameregexes=[re.compile("^'(?P<layoutfile>.*)'\..*$"),
                     re.compile("^.*(?P<extension>\..*)$"),]
    keyproperties=["layoutfile","extension"]
                     
#
class _FileReader(object):
    include_in_format_search=False
    checks=[]

    def __init__(self,filepath,passerrorsto=None,read=True):
        if passerrorsto is not None:
            self.passerrorsto=passerrorsto
        self.filepath=filepath
        self.shareddata={"readerclass":self.__class__.__name__}
        self.rowdata=[]
        if read:
            self.read_basic()

    def read_basic(self):
        return

    def __call__(self):
        self.parse()

    def __getitem__(self,query):
        if query in self.shareddata:
            return self.shareddata[query]
        else:
            if self.rowdata==[]:
                self.parse()
            if type(query)==int:
                return self.rowdata[query]
            elif query in self.shareddata:
                return self.shareddata[query]

    def _number_to_lettercode(self,number):
        """
        >>> print _FileReader(None)._number_to_lettercode(3)
        C
        >>> print _FileReader(None)._number_to_lettercode(27)
        AA
        """
        lettercode=""
        while number>0:
            modulo=(number-1)%26
            lettercode+=chr(65+modulo)
            number=(number-modulo)/26
        return lettercode[::-1]

    def _lettercode_to_number(self,lettercode):
        """
        >>> print _FileReader(None)._lettercode_to_number("C")
        3
        >>> print _FileReader(None)._lettercode_to_number("AA")
        27
        """
        number=0
        for letter in lettercode:
            if letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                number=number*26+(ord(letter.upper())-ord("A"))+1
        return number

    def _coordinates_to_rangename(self,x1,y1,x2,y2):
        """
        >>> print _FileReader(None)._coordinates_to_rangename(1,2,3,4)
        A2:C4
        """
        rangename="{}{}:{}{}".format(self._number_to_lettercode(x1),
                                     y1,
                                     self._number_to_lettercode(x2),
                                     y2)
        if x2<x1 or y2<y1:
            LOG.error("{}: {} isn't a sensible range name"
                      .format(self.__class__.__name__,rangename))
        else:
            return rangename

    def _rangename_to_coordinates(self,rangename):
        """
        >>> print _FileReader(None)._rangename_to_coordinates("A2:C4")
        (1, 2, 3, 4)
        """
        if ":" in rangename:
            regex_object=re.search("(\D+)(\d+):(\D+)(\d+)",rangename)
            a,b,c,d=regex_object.groups()
            return self._lettercode_to_number(a),int(b),self._lettercode_to_number(c),int(d)
        else:
            regex_object=re.search("(\D+)(\d+)",rangename)
            a,b=regex_object.groups()
            return self._lettercode_to_number(a),int(b)

    def _range_snip(self,rangename,sheetname=None):
        """
        Determines the maximum working dimensions of an Excel worksheet or Csv table,
        and returns a clipped Excel-style range which only goes up these limits
        >>> testfilename="Example layout 384.csv"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> r=_CsvReader(testfilepath)
        >>> print r._range_snip("A1:XFD1048576")
        A1:Y17
        """
        xMax,yMax=self._get_dimensions(sheetname)
        xMin,yMin=0,0
        x1,y1,x2,y2=self._rangename_to_coordinates(rangename)
        xN1,yN1=max(xMin,x1),max(yMin,y1) #Unnecessary really: this is always going to be A1
        xN2,yN2=min(xMax,x2),min(yMax,y2)
        return self._coordinates_to_rangename(xN1,yN1,xN2,yN2)

    def _reshape_single_dimension_lists(self,listarray):
        """
        Used by read_cell_range method in _CsvReader & _XlsxReader to flatten any lists
        that represent only a single row or single column

        >>> print _FileReader(None)._reshape_single_dimension_lists([[1,2,3,4]]) #single row
        [1, 2, 3, 4]
        >>> print _FileReader(None)._reshape_single_dimension_lists([[1],[2]]) #single column
        [1, 2]
        >>> print _FileReader(None)._reshape_single_dimension_lists([[1,2,3,4],[5,6,7,8]])
        [[1, 2, 3, 4], [5, 6, 7, 8]]
        """
        if len(listarray)==1:
            return listarray[0]
        elif len(listarray[0])!=1:
            return listarray
        else:
            return [row[0] for row in listarray]

    def check_cell_value(self,cellname,regex=None,sheetname=None,report=False):
        """
        >>> testfilename="Example layout 384.csv"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> r=_CsvReader(testfilepath)
        >>> print r.check_cell_value(cellname="A3",regex="(B)",sheetname=None)
        B
        >>> print r.check_cell_value(cellname="A3",regex="(X)",sheetname=None)
        False
        """
        try:
            cellvalue=self.read_cell_value(cellname,sheetname=sheetname)
        except:
            if report: LOG.error("can't read cellvalue in '{}'"
                                .format(cellname))
            self.is_OK=False
            return False
        
        if str(cellvalue)==str(regex):
            if report: LOG.info("cellvalue '{}' == '{}'"
                                .format(cellvalue,regex))
            return True
        if regex=="(.*)": #result can be anything, but not None
            if cellvalue is None:
                if report: LOG.error("cellvalue is None and regex was (.*)")
                self.is_OK=False
                return False
            else:
                return cellvalue
        if cellvalue is None:
            if report: LOG.error("cellvalue is None but regex = {}".
                                 format(regex))
            self.is_OK=False
            return False
        else:
            try:
                regex_object=re.search(regex,str(cellvalue))
            except Exception as e:
                if report:
                    LOG.error("unexpected error searching for {} in regex {}: {}"
                              .format(cellvalue,regex,e))
                self.is_OK=False
                return False
            if not regex_object:
                if report:
                    LOG.error("regex_object returns None (no match) for "
                              "cellvalue {} and regex {}"
                              .format(regex_object,cellvalue,regex))
                self.is_OK=False
                return False
            if not hasattr(regex_object,"groups"):
                if report:
                    LOG.error("regex_object {} has no groups for cellvalue {} "
                              "and regex {}"
                              .format(regex_object,cellvalue,regex))
                self.is_OK=False
                return False
            if regex_object.groups()==():
                if report:
                    LOG.error("regex_object {} returns groups () for cellvalue {} "
                              "and regex {}"
                              .format(regex_object,cellvalue,regex))
                self.is_OK=False
                return False
            else:
                return regex_object.groups()[0]

    def is_correct_format(self,sheetname=None,report=False):
        """
        Subclass must specify a class variable called 'checks' which is a list of tuples of the form
            (well_name, correct_regex_pattern, store_data_as)
        e.g.
        >>> class TempReader(_XlsxReader):
        ...     checks=[("D8","(0.3601)","reading_in_cell_D8")]
        >>> testfilename1="EX2a (YPD) [Basic384] t-1 (MarsExcelTableSingleTimepoint).xlsx"
        >>> testfilepath1=os.path.join(Locations().rootdirectory,"tests",testfilename1)
        >>> r=TempReader(testfilepath1)
        >>> print r.is_correct_format()
        False
        
        >>> testfilename2="EX2b (YPD) [Basic384] t+0 (MarsExcelTableMultipleTimepoint).xlsx"
        >>> testfilepath2=os.path.join(Locations().rootdirectory,"tests",testfilename2)
        >>> r=TempReader(testfilepath2)
        >>> print r.is_correct_format()
        True

        NB Excel-style well_name syntax is used, even for csv tables.
        """
        if hasattr(self,"is_OK"):
            #ALREADY LOOKS OK
            if self.is_OK==False:
                return False
        for cellname,regex,property in self.checks:
            a=self.check_cell_value(cellname,regex,sheetname=sheetname,report=report)
            if property and a is not False:
                self.shareddata[property]=a
            else:
                if report:
                    LOG.debug("check_cell_value returned {} for ({},{},{})"
                              .format(a,cellname,regex,property))
        if hasattr(self,"is_OK"):
            if self.is_OK==False:
                return False
        return True

    def _process_date_and_time(self,format="%d/%m/%Y %H:%M:%S"):
        if hasattr(self,"shareddata"):
            d=self.shareddata.get("datestarted",None)
            t=self.shareddata.get("timestarted",None)
            if d and t:
                self.shareddata["exp_datetime"]=time.mktime(time.strptime(d+" "+t,format))

    def get_is_OK(self):
        return getattr(self,"is_ok",True)

class _CsvReader(_FileReader):
    include_in_format_search=False
    checks=[]
    delimiter=","
    def read_basic(self):
        #For csv files, the reader has to load the whole file into memory to check any cells
        if not os.path.exists(self.filepath):
            LOG.error("_CsvReader: path {} doesn't exist"
                      .format(self.filepath))
            return
        try:
            fileob=open(self.filepath,"rU")
            reader=csv.reader(fileob,delimiter=self.delimiter)
            self.contents=[row for row in reader]
            while not self.contents[-1]:
                self.contents=self.contents[:-1]
            fileob.close()
        except Exception as error:
            #print error
            LOG.error("_CsvReader: unspecified read error for file {}: {}"
                      .format(self.filepath,error))
            self.is_OK=False
            return
        if self.contents==[]:
            LOG.error("_CsvReader: empty contents in file {}"
                      .format(self.filepath))
            self.is_OK=False

    def _get_sheet(self):
        return self.read_basic()

    def _get_dimensions(self,sheetname=None):
        if not hasattr(self,"contents"):
            self.read_basic()
        x=max([len(row) for row in self.contents])
        y=len(self.contents)
        return x,y

    def read_cell_value(self,cellname,sheetname=None):
        #print "READING CELL VALUE",cellname,sheetname,self.filepath
        if not hasattr(self,"contents"):
            self.read_basic()
        if not getattr(self,"contents",False):
            LOG.error("_CsvReader: failing to read value of cell {} in file {}"
                      .format(cellname,self.filepath))
            return None
        x,y=self._rangename_to_coordinates(cellname)
        cellvalue=self.contents[y-1][x-1]
        if cellvalue=="":
            return None
        return cellvalue

    def read_cell_range(self,cellrangename,sheetname=None):
        if not hasattr(self,"contents"):
            self.read_basic()
        cellrangename_snipped=self._range_snip(cellrangename,None)
        #automatically snips the range to match the sheet dimensions so it doesn't read too much
        x1,y1,x2,y2=self._rangename_to_coordinates(cellrangename_snipped)
        outputlist=[]
        for yI in range(y1-1,y2):
            row=self.contents[yI]
            rowlist=[]
            for xI in range(x1-1,x2):
                cellvalue=row[xI] if xI<len(row) else []
                rowlist.append(cellvalue)
            outputlist.append(rowlist)
        return self._reshape_single_dimension_lists(outputlist)

    def parse(self,sheetname=None):
        """
        >>> testfilename="EX4a (YPD) [Basic384] t-1 (DATParserWithoutTemp).csv"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> r=DATReaderWithoutTemp(testfilepath)
        >>> sd,rd = r.parse()
        >>> print sd["timepoints"]
        [0.0]
        >>> print len(rd)
        384
        >>> print rd[0]
        {'measurements': (1.1513,)}
        """
        headers=self.read_cell_range("A1:XFC1",sheetname)
        body=self.read_cell_range("A2:XFC1048576",sheetname)
        self.shareddata={"headers":headers}
        self.rowdata=[dict(zip(headers,row)) for row in body]
        if self.shareddata and self.rowdata:
            self.is_OK=True
        return self.shareddata,self.rowdata

class _TdfReader(_CsvReader):
    """
    Base class for tab delimited files
    """
    include_in_format_search=False
    delimiter="\t"
    checks=[]

class _DATReader(_TdfReader):
    include_in_format_search=False
    ranges=[("A8:XFD1048576","data")]
    filenamereader=ReadingFileNameReader

class _XlsxReader(_FileReader):
    """
    Uses xlrd module (previous versions used openpyxl but this was slow)
    """
    include_in_format_search=False
    checks=[("A1",None,None)]
    ranges=[("A1:XFD1048576","cellvalues")]

    def read_basic(self,report=False):
        """
        >>> testfilename="EX2b (YPD) [Basic384] t+0 (MarsExcelTableMultipleTimepoint).xlsx"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> r=_XlsxReader(testfilepath)
        >>> print r.workbook.__class__.__name__
        Book
        """
        #this (tries to) open just enough of the file for checks, without necessarily
        #reading the whole thing into memory
        try:
            self.workbook=xlrd.open_workbook(self.filepath)
        except:
            if report:
                LOG.debug("{}: Unable to open {} as Excel file"
                          .format(self.__class__.__name__,self.filepath))
            self.is_OK=False

    def _get_sheet(self,sheetname=None,report=False):
        """
        >>> testfilename="EX2b (YPD) [Basic384] t+0 (MarsExcelTableMultipleTimepoint).xlsx"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> r=_XlsxReader(testfilepath)
        >>> print r._get_sheet(None).name
        All Cycles
        """
        if not hasattr(self,"workbook"):
            self.read_basic(report=report)
        if sheetname is None:
            return self.workbook.sheet_by_index(0)
        else:
            return self.workbook.sheet_by_name(sheetname)

    def _get_dimensions(self,sheetname=None,report=False):
        """
        >>> testfilename="EX2b (YPD) [Basic384] t+0 (MarsExcelTableMultipleTimepoint).xlsx"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> r=_XlsxReader(testfilepath)
        >>> print r._get_dimensions("All Cycles")
        (113, 391)
        """
        sheet=self._get_sheet(sheetname,report=report)
        return sheet.ncols,sheet.nrows

    def read_cell_value(self,cellname,sheetname=None,report=False):
        """
        >>> testfilename="EX2b (YPD) [Basic384] t+0 (MarsExcelTableMultipleTimepoint).xlsx"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> r=_XlsxReader(testfilepath)
        >>> print r.read_cell_value("D8","All Cycles")
        0.3601
        """
        if not hasattr(self,"workbook"):
            self.read_basic(report=report)
        x,y=self._rangename_to_coordinates(cellname)
        x,y=x-1,y-1
        cellvalue=self._get_sheet(sheetname,report=report).cell(y,x).value
        if cellvalue=="":
            return None
        return cellvalue

    def read_cell_range(self,cellrangename,sheetname=None,report=False):
        """
        >>> testfilename="EX2b (YPD) [Basic384] t+0 (MarsExcelTableMultipleTimepoint).xlsx"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> r=_XlsxReader(testfilepath)
        >>> print r.read_cell_range("D7:D9","All Cycles")
        [0.0, 0.3601, 0.2703]
        >>> print r.read_cell_range("D7:F7","All Cycles")
        [0.0, 0.16666666666666666, 0.3333333333333333]
        >>> print r.read_cell_range("D7:F9") #sheetname got automatically
        [[0.0, 0.16666666666666666, 0.3333333333333333], [0.3601, 0.3637, 0.3685], [0.2703, 0.2727, 0.2739]]
        """
        if not hasattr(self,"workbook"):
            self.read_basic(report=report)
        #No type checking because it slows down an already slow process
        cellrangename_snipped=self._range_snip(cellrangename,sheetname)
        #automatically snips the range to match the sheet dimensions so it doesn't read too much
        sheet=self._get_sheet(sheetname,report=report)
        x1,y1,x2,y2=self._rangename_to_coordinates(cellrangename_snipped)
        outputlist=[]
        for row in range(y1,y2+1):
            rowlist=[]
            for col in range(x1,x2+1):
                cellvalue=sheet.cell(row-1,col-1).value
                rowlist.append(cellvalue)
            outputlist.append(rowlist)
        return self._reshape_single_dimension_lists(outputlist)

class _MarsExcelTable(_XlsxReader):
    include_in_format_search=False
    checks=[("A1","User: (.+)","platereaderusername"),
            ("A2","Test Name: (.+)","platereaderprogram"),
            ("A3","(Absorbance)",None),
            ("D1","Path: (.+)","platereaderddatapath"),
            ("D3","(Absorbance values are displayed as OD)",None),
            ("I2","Date: (.+)","datestarted"),
            ("K1","Test ID: (.+)","platereadertestID"),
            ("K2","Time: (.+)","timestarted")]
    filenamereader=ReadingFileNameReader

    def parse(self,sheetname=None):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            if self.rowdata==[]:
                self._process_date_and_time()
                #read in ranges
                dataranges={}
                for cellrangename,descriptor in self.ranges:
                    rangedata=self.read_cell_range(cellrangename,sheetname)
                    dataranges[descriptor]=rangedata
                #now create curve objects
                self.shareddata["n_curves"]=len(dataranges["data"])
                self.shareddata["timepoints"]=dataranges.get("timepoints",[0])
                self.shareddata["n_measures"]=len(self.shareddata["timepoints"])
                for i in range(self.shareddata["n_curves"]):
                    measurements=dataranges["data"][i]
                    welllabel="{}{}".format(dataranges["plate row letters"][i],
                                            int(dataranges["plate column numbers"][i]))
                    samplelabel=dataranges["plate sample labels"][i]
                    if "group labels" in dataranges:
                        grouplabel=dataranges["group labels"][i]
                    #fudge required for files with a single reading:
                    if type(measurements) in [float,int]:
                        measurements=[measurements]
                    self.rowdata.append({"welllabel":welllabel,
                                         "samplelabel":samplelabel,
                                         "measurements":measurements})
                    if "group labels" in dataranges:
                        self.rowdata[-1]["grouplabel"]=grouplabel
            return self.shareddata,self.rowdata

class _MarsExcelPlate(_XlsxReader):
    include_in_format_search=False
    checks=[("A3","User: (.+)","platereaderusername"),
            ("A4","Test Name: (.+)","platereaderprogram"),
            ("A5","(Absorbance)",None),
            ("D3","Path: (.+)","platereaderddatapath"),
            ("D5","(Absorbance values are displayed as OD)",None),
            ("B9","(Raw Data \(600\)).*",None),
            ("I4","Date: (.+)","datestarted"),
            ("K3","Test ID: (.+)","platereadertestID"),
            ("K4","Time: (.+)","timestarted")]
    filenamereader=ReadingFileNameReader

    def parse(self,sheetname=None):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            if self.rowdata==[]:
                self._process_date_and_time()
                #read in ranges
                dataranges={}
                for cellrangename,descriptor in self.ranges:
                    rangedata=self.read_cell_range(cellrangename,sheetname)
                    dataranges[descriptor]=rangedata
                #rearrange data (just join rows)
                dataranges["data"]=flatten(dataranges["data"])
                #now create curve objects
                self.shareddata["n_curves"]=len(dataranges["data"])
                self.shareddata["timepoints"]=dataranges.get("timepoints",[0])
                self.shareddata["n_measures"]=len(self.shareddata["timepoints"])
                assert len(dataranges["plate column numbers"])*len(dataranges["plate row letters"])==len(dataranges["data"])
                for i in range(self.shareddata["n_curves"]):
                    row=int(np.ceil( i / len(dataranges["plate column numbers"]) ))
                    col=(i%len(dataranges["plate column numbers"]))
                    measurements=dataranges["data"][i]
                    welllabel="{}{}".format(dataranges["plate row letters"][row],
                                           int(dataranges["plate column numbers"][col]))
                    #fudge required for files with a single reading:
                    if type(measurements) in [float,int]:
                        measurements=[measurements]
                    self.rowdata.append({"measurements":measurements,
                                         "welllabel":welllabel})
            return self.shareddata,self.rowdata

class DATReaderWithoutTemp(_DATReader):
    """
    >>> testfilename="EX4a (YPD) [Basic384] t-1 (DATParserWithoutTemp).csv"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
    >>> r=DATReaderWithoutTemp(testfilepath)
    >>> sd,rd = r.parse()
    >>> print sd["n_curves"]
    384
    >>> print sd["n_measures"]
    1
    """
    include_in_format_search=True
    checks=[("A1","Testname: (.+)","platereaderprogram"),
            ("A2","Date: (\d\d/\d\d/\d\d\d\d)  Time: \d\d:\d\d:\d\d","datestarted"),
            ("A2","Date: \d\d/\d\d/\d\d\d\d  Time: (\d\d:\d\d:\d\d)","timestarted"),
            ("A10","(A1)",None)]

    def parse(self,sheetname=None):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            #read in ranges
            x,y=self._get_dimensions()
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)
            #Transform blocks of data into rows
            if self.rowdata==[]:
                self._process_date_and_time()
                headerrows=7
                blockwidth,blockheight=x,(x/3)
                nblocks=(y-headerrows)/(blockheight+2)
                sectionrowstarts=range(0,y-headerrows,blockheight+2)
                #print sectionrowstarts
                cycles=[]
                timepoints=[]
                data=[]
                for blockstart in sectionrowstarts:
                    datablock=dataranges["data"][blockstart:blockstart+blockheight+2]
                    headers=[d[0] for d in datablock[:2]]
                    cycle=int(headers[0][7:])
                    cycles.append(cycle)
                    try:
                        timepoint=float((headers[1][10:]))/(60.0*60.0)
                        timepoints.append(timepoint)
                    except:
                        timepoint=None
                    if timepoint is None:
                        break
                    else:
                        #print cycle,timepoint,temperaturepoint
                        datablock=datablock[2:]
                        flatteneddatablock=flatten(datablock)
                        wellnames=flatteneddatablock[0::2]
                        def is_number(s):
                            try:
                                float(s)
                                return True
                            except ValueError:
                                return False
                        measurements=[float(m) if is_number(m) else 0.0 for m in flatteneddatablock[1::2]]
                        if all([m==3.5 for m in measurements]) or all([m==0.0 for m in measurements]):
                            #print "REDACTING LAST DATABLOCK"
                            timepoints.pop()
                        else:
                            data.append(measurements)
                self.shareddata["n_curves"]=(blockwidth/2)*blockheight
                self.shareddata["timepoints"]=timepoints
                self.shareddata["n_measures"]=len(self.shareddata["timepoints"])
                #Now flip the self.data so that rows become columns and vice versa
                self.rowdata=[{"measurements":m} for m in zip(*data)]
            return self.shareddata,self.rowdata

class DATReaderWithTemp(_DATReader):
    """
    >>> testfilename="EX4b (YPD) [Basic384] t+0 (DATParserWithTemp).DAT"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
    >>> r=DATReaderWithTemp(testfilepath)
    >>> sd,rd = r.parse()
    >>> print sd["n_curves"]
    384
    >>> print sd["n_measures"]
    35
    """
    include_in_format_search=True
    checks=[("A1","Testname: (.+)","platereaderprogram"),
            ("A2","Date: (\d\d/\d\d/\d\d\d\d)  Time: \d\d:\d\d:\d\d","datestarted"),
            ("A2","Date: \d\d/\d\d/\d\d\d\d  Time: (\d\d:\d\d:\d\d)","timestarted"),
            ("A10","T(.*)",None)]

    def parse(self,sheetname=None):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            #read in ranges
            x,y=self._get_dimensions()
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)
            #Transform blocks of data into rows
            if self.rowdata==[]:
                self._process_date_and_time()
                headerrows=7
                blockwidth,blockheight=x,(x/3)
                nblocks=(y-headerrows)/(blockheight+3)
                sectionrowstarts=range(0,y-headerrows,blockheight+3)
                #print sectionrowstarts
                cycles=[]
                timepoints=[]
                temperaturepoints=[]
                data=[]
                for blockstart in sectionrowstarts:
                    datablock=dataranges["data"][blockstart:blockstart+blockheight+3]
                    headers=[d[0] for d in datablock[:3]]
                    cycle=int(headers[0][7:])
                    cycles.append(cycle)
                    try:
                        timepoint=float((headers[1][10:]))/(60.0*60.0)
                        timepoints.append(timepoint)
                    except:
                        timepoint=None
                    try:
                        temperaturepoint=float((headers[2][7:]))
                        temperaturepoints.append(temperaturepoint)
                    except:
                        temperaturepoint=None
                    if timepoint is None and temperaturepoint is None:
                        break
                    else:
                        #print cycle,timepoint,temperaturepoint
                        datablock=datablock[3:]
                        flatteneddatablock=flatten(datablock)
                        wellnames=flatteneddatablock[0::2]
                        def is_number(s):
                            try:
                                float(s)
                                return True
                            except ValueError:
                                return False
                        #print [(m,type(m)) for m in flatteneddatablock[1::2]]
                        #print
                        measurements=[float(m) if is_number(m) else 0.0 for m in flatteneddatablock[1::2]]
                        if all([m==3.5 for m in measurements]) or all([m==0.0 for m in measurements]):
                            #print "REDACTING LAST DATABLOCK"
                            timepoints.pop()
                            temperaturepoints.pop()
                        else:
                            data.append(measurements)
                self.shareddata["n_curves"]=(blockwidth/2)*blockheight
                self.shareddata["timepoints"]=timepoints
                self.shareddata["temperaturepoints"]=temperaturepoints
                self.shareddata["n_measures"]=len(self.shareddata["timepoints"])
                #Now flip the self.data so that rows become columns and vice versa
                self.rowdata=[{"measurements":m} for m in zip(*data)]
            return self.shareddata,self.rowdata

class DATRecoveryFile(_CsvReader):
    """
    If something interrupts the platereader and prevents it from
    saving data, but you can still open the recovered test run
    in the MARS analysis suite, click the Table View tab,
    select 'All Cycles' from the drop down box, then click the
    'Export Table to ASCII' button on the tool bar.
    Once renamed appropriately, this file can be read using this
    file reader.
    """
    include_in_format_search=True
    checks=[("A1","User: (.+)","platereaderusername"),
            ("A2","Test name: (.*)","platereaderprogram"),
            ("A3","Absorbance",None),
            ("A5","Well Row",None),
            ("A7","A",None),
            ("B1","Path: (.*)","filepath"),
            ("B2","Date: (\d\d/\d\d/\d\d\d\d)","datestarted"),
            ("B5","Well Col",None),
            ("B7","1",None),
            ("C1","Test run no.: (\d*)","platereadertestID"),
            ("C2","Time: (\d\d:\d\d:\d\d)","timestarted")]
    ranges=[("D6:XFD6","timepoints"),
            ("A7:A1048576","plate row letters"),
            ("B7:B1048576","plate column numbers"),
            ("C7:C1048576","plate sample labels"),
            ("D7:XFD1048576","data")]
    filenamereader=ReadingFileNameReader

    def parse(self,sheetname=None):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            #read in ranges
            x,y=self._get_dimensions()
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)
            timepattern=re.compile("(\d+) h (\d*)( min)?")
            timepoints=[]
            for timestring in dataranges["timepoints"]:
                hr,mn,x=re.match(timepattern,timestring).groups()
                timevalue=((int(hr)*60)+int(mn or 0))/60.0
                timepoints.append(timevalue)

            self.shareddata["n_curves"]=len(dataranges["data"])
            self.shareddata["timepoints"]=timepoints
            self.shareddata["n_measures"]=len(timepoints)

            self.rowdata=[]
            for PL,PN,SN,MS in zip(dataranges["plate row letters"],
                                   dataranges["plate column numbers"],
                                   dataranges["plate sample labels"],
                                   dataranges["data"]):
                self.rowdata.append({"measurements":[float(f) for f in MS],
                                     "wellname":PL+PN,
                                     "samplename":SN})
            return self.shareddata,self.rowdata

class MarsExcelPlateSingleTimepoint(_MarsExcelPlate):
    include_in_format_search=True
    checks=_MarsExcelPlate.checks+[("A11","(A)",None)]
    ranges=[("A11:A1048576","plate row letters"),
            ("B10:XFD10","plate column numbers"),
            ("B11:AW1048576","data")]

class MarsExcelTableSingleTimepoint(_MarsExcelTable):
    include_in_format_search=True
    checks=_MarsExcelTable.checks+[("A7","(A)",None),
                                  ("D6","(Raw Data \(600\)).*",None)]
    ranges=[("A7:A1048576","plate row letters"),
            ("B7:B1048576","plate column numbers"),
            ("C7:C1048576","plate sample labels"),
            ("D7:D1048576","data")]

class MarsExcelTableShiftedSingleTimepoint(_MarsExcelTable):
    include_in_format_search=True
    checks=_MarsExcelTable.checks+[("A8","(A)",None),
                                  ("D7","(Raw Data \(600\)).*",None)]
    ranges=[("A8:A1048576","plate row letters"),
            ("B8:B1048576","plate column numbers"),
            ("C8:C1048576","plate sample labels"),
            ("D8:D1048576","data")]

class MarsExcelTableSingleTimepointWithGroups(_MarsExcelTable):
    include_in_format_search=True
    checks=_MarsExcelTable.checks+[("A7","(A)",None),
                                  ("D6","(Group)",None),
                                  ("E6","(Raw Data \(600\)).*",None)]
    ranges=[("A7:A1048576","plate row letters"),
            ("B7:B1048576","plate column numbers"),
            ("C7:C1048576","plate sample labels"),
            ("D7:D1048576","group labels"),
            ("E7:E1048576","data")]

class MarsExcelTableShiftedSingleTimepointWithGroups(_MarsExcelTable):
    include_in_format_search=True
    checks=_MarsExcelTable.checks+[("A8","(A)",None),
                                  ("D7","(Group)",None),
                                  ("E7","(Raw Data \(600\)).*",None)]
    ranges=[("A8:A1048576","plate row letters"),
            ("B8:B1048576","plate column numbers"),
            ("C8:C1048576","plate sample labels"),
            ("D8:D1048576","group labels"),
            ("E8:E1048576","data")]

class MarsExcelTableMultipleTimepoint(_MarsExcelTable):
    include_in_format_search=True
    checks=_MarsExcelTable.checks+[("A7",None,None),
                                  ("A8","(A)",None),
                                  ("D6","(Raw Data \(600\)).*",None),
                                  ("D7","(0)",None)]
    ranges=[("A8:A1048576","plate row letters"),
            ("B8:B1048576","plate column numbers"),
            ("C8:C1048576","plate sample labels"),
            ("D7:XFD7","timepoints"),
            ("D8:XFD1048576","data")]

class MarsExcelTableShiftedMultipleTimepoint(_MarsExcelTable):
    include_in_format_search=True
    checks=_MarsExcelTable.checks+[("A8",None,None),
                                  ("A9","(A)",None),
                                  ("D7","(Raw Data \(600\)).*",None),
                                  ("D8","(0)",None)]
    ranges=[("A9:A1048576","plate row letters"),
            ("B9:B1048576","plate column numbers"),
            ("C9:C1048576","plate sample labels"),
            ("D8:XFD8","timepoints"),
            ("D9:XFD1048576","data")]

class BioscreenOutput(_CsvReader):
    """
    >>> testfilename="EX3a (liquidYPD) [Basic100] (BioscreenOutput).csv"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
    >>> r=BioscreenOutput(testfilepath)
    >>> sd,rd = r.parse()
    >>> print sd["n_curves"]
    100
    >>> print sd["n_measures"]
    100
    """
    include_in_format_search=True
    checks=[("A1","(Time)",None),
            ("A2","00:00:(\d\d)",None),
            ("B1","Well (\d*)",None)]
    ranges=[("B1:XFD1","welllabels"),
            ("A2:A1048576","timepoints"),
            ("B2:XFD1048576","data")]
    filenamereader=ReadingFileNameReader

    def parse(self,sheetname=None):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            #read in ranges
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)
            #NB data in these files is flipped (rows<>cols), so flip it back:
            flippeddata=zip(*dataranges["data"])
            dataranges["data"]=flippeddata
            #NB convert timepoint strings into floats
            timepoints=dataranges["timepoints"]
            newtimepoints=[]
            for t_string in timepoints:
                hr,min,sec=[int(v) for v in t_string.split(":")]
                newtimepoints.append(hr+(min/60.0)+(sec/3600.0))
            dataranges["timepoints"]=newtimepoints
            #now create data
            self.shareddata["n_curves"]=len(dataranges["data"])
            self.shareddata["timepoints"]=timepoints=dataranges["timepoints"]
            #NB convert data strings into floats
            if type(dataranges["data"][0]) in [tuple,list]:
                data=[map(float,row) for row in dataranges["data"]]
            else:
                data=map(float,dataranges["data"])
            self.rowdata=[{"measurements":m,"welllabel":wn} for m,wn in zip(data,dataranges["welllabels"])]
            self.shareddata["n_measures"]=len(self.rowdata)
            return self.shareddata,self.rowdata
#
class StingerReader(_CsvReader):
    """
    >>> testfilename="Example stinger instructions.csv"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
    >>> s=StingerReader(testfilepath)
    >>> sd,rd = s.parse()
    >>> print len(rd)
    12
    """
    include_in_format_search=True
    checks=[("A1","SOURCEPLATEID",None),
            ("B1","SOURCEDENSITY",None),
            ("C1","SOURCECOLONYCOLUMN",None),
            ("D1","SOURCECOLONYROW",None),
            ("E1","TARGETPLATEID",None),
            ("F1","TARGETDENSITY",None),
            ("G1","TARGETCOLONYCOLUMN",None),
            ("H1","TARGETCOLONYROW",None)]
    ranges=[("A1:H1","headers"),
            ("A2:A1048576","sourceplateids"),
            ("B2:B1048576","sourceplatedensities"),
            ("C2:C1048576","sourceplatecolonycolumns"),
            ("D2:D1048576","sourceplatecolonyrows"),
            ("E2:E1048576","targetplateids"),
            ("F2:F1048576","targetplatedensities"),
            ("G2:G1048576","targetplatecolonycolumns"),
            ("H2:H1048576","targetplatecolonyrows")]

    def add_data(self,rowdata):
        if not hasattr(self,"rowdata"):
            self.rowdata=[]
        for r in rowdata:
            if type(r)==dict:
                self.rowdata.append(r)
            elif type(r)==list:
                #print r
                #print [c[1] for c in self.checks]
                r=dict(zip([c[1] for c in self.checks],r))
                #print r
                self.rowdata.append(r)
            elif hasattr(r,"_get_deep_headers"):
                DH=r._get_deep_headers()
                if "layoutstring" in DH: TPID=r["layoutstring"].value
                else: TPID=r["plateid"].value
                #could be a reading, well, or plateposition
                self.rowdata.append({"SOURCEPLATEID":TPID,
                                     "SOURCEDENSITY":r["capacity"].value,
                                     "SOURCECOLONYCOLUMN":r["wellcol"].value,
                                     "SOURCECOLONYROW":r["wellrowletter"]})

    def yield_next_target(self):
        from DBOS import Plate,Plates,PlateLayouts,PlateLayout
        if not getattr(self,"defaulttarget",None):
            self.defaulttarget=Plates()["96"]
        #assert type(self.defaulttarget) in [Plate,PlateLayout]
        counter=0
        while True:
            counter+=1
            if hasattr(self.defaulttarget,"yield_records"):
                TPID="{}_{:02d}".format(self.defaulttarget["plateid"].value,
                                        counter)
                for well in self.defaulttarget.yield_records():
                    yield {"TARGETPLATEID":TPID,
                           "TARGETDENSITY":self.defaulttarget["capacity"].value,
                           "TARGETCOLONYCOLUMN":well["wellcol"].value,
                           "TARGETCOLONYROW":well["wellrowletter"]}
                    
            elif hasattr(self.defaulttarget,"yield_records"):
                TPID="{}_{:02d}".format(self.defaulttarget["layoutstring"].value,
                                        counter)
                for plateposition in self.defaulttarget.yield_records():
                    yield {"TARGETPLATEID":TPID,
                           "TARGETDENSITY":self.defaulttarget["capacity"].value,
                           "TARGETCOLONYCOLUMN":plateposition["wellcol"].value,
                           "TARGETCOLONYROW":plateposition["wellrowletter"]}
            if counter>99:
                LOG.critical("NO MORE THAN 99 TARGET PLATES ALLOWED "
                             "IN THIS SCRIPT")
                sys.exit()

    def sort(self,key=lambda d:(d["SOURCEPLATEID"],
                                d["SOURCECOLONYROW"],
                                d["SOURCECOLONYCOLUMN"],
                                d.get("TARGETPLATEID",None),
                                d.get("TARGETCOLONYROW",None),
                                d.get("TARGETCOLONYCOLUMN",None))):
        if not hasattr(self,"rowdata"):
            sd,rd=self.parse()
            LOG.debug("parsing, got rowdata {}".format(rd))
        else:
            self.rowdata.sort(key=key)

    def write(self,newfiledesignation=None):
        self.sort()

        if newfiledesignation is None:
            newfiledesignation=self.filepath
        if not newfiledesignation.endswith(".csv"):
            newfiledesignation=newfiledesignation+".csv"
        if os.path.exists(newfiledesignation):
            if raw_input("OVERWRITE?").upper()[0] not in ["Y"]:
                return False
        #open a csvwriter
        fileob=open(newfiledesignation,"wb")
        writer=csv.writer(fileob,delimiter=',',quoting=csv.QUOTE_MINIMAL)
        #add rows
        headers=[t[1] for t in self.checks]
        writer.writerow(headers)
        #print headers
        targetgenerator=self.yield_next_target()
        for row in self.rowdata:
            if type(row)==dict:
                if "TARGETPLATEID" not in row:
                    row.update(**targetgenerator.next())
                row = [row.get(k,None) for k in headers]
                assert None not in row
            writer.writerow(row)
            #print row
        fileob.close()
        return True

    @classmethod
    def create(cls,rowdata,newfiledesignation,defaulttarget=None,write=True):
        if not newfiledesignation.endswith(".csv"):
            newfiledesignation=newfiledesignation+".csv"
        newreaderobject=cls(newfiledesignation,read=False)
        newreaderobject.defaulttarget=defaulttarget
        newreaderobject.add_data(rowdata)
        if write:
            newreaderobject.write()
        return newreaderobject

class GenotypeData(_CsvReader):
    """
    >>> testfilename="Example genotypes.csv"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
    >>> r=GenotypeData(testfilepath)
    >>> sd,rd = r.parse()
    >>> print sd.keys()
    ['markernames', 'chromosomes', 'geneticpositions']
    >>> print len(rd)
    288
    """
    include_in_format_search=False
    checks=[("A1","(.*)","internalprefix"), #anything, but not None
            ("A2",None,None),]
    ranges=[("A4:A1000000","strains"),
            ("B1:ZZZZ1","markernames"),
            ("B2:ZZZZ2","chromosomes"),
            ("B3:ZZZZ3","geneticpositions"),
            ("B4:ZZZZ1000000","data")]

    def parse(self):
        #print "PARSING",self.filepath
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)

            MN=dataranges["markernames"]
            CH=[int(c) for c in dataranges["chromosomes"]]
            def scrub_text(inputstring):
                if "." in inputstring:
                    T=float
                else:
                    T=int
                return T(''.join([c for c in inputstring if c.isdigit() or c=="."]))
            GP=[scrub_text(k) for k in dataranges["geneticpositions"]]
            ST=dataranges["strains"]

            self.shareddata={"markernames":MN,
                             "chromosomes":CH,
                             "geneticpositions":GP}

            self.rowdata=[]
            self.genotypelookup={}
            for i in range(len(dataranges["data"])):
                
                def scrub_genotype(inputstring):
                    if inputstring in ["-",""," ",None]:
                        return None
                    return inputstring
                GT=[scrub_genotype(g) for g in dataranges["data"][i]]
                if not any(GT):
                    GT=False
                self.rowdata.append({"index":i,
                                     "strain":ST[i],
                                     "genotypes":GT})
            self.make_genotypedict()
            return self.shareddata,self.rowdata

    def make_genotypedict(self):
        if not hasattr(self,"genotypedict"):
            self.genotypedict={row["strain"]:{"alleles":row["genotypes"],
                                              "markers":self.shareddata}
                               for row in self.rowdata}
        return self.genotypedict

    def __len__(self):
        return len(self.make_genotypedict())

    def create(self,phenotypedata,newfiledesignation="test"):
        #for now, accept phenotype data as a dict of form {samplename:[(heading,value),etc]}
        newfilepath="{} {}-{} {}.csv".format(newfiledesignation,
                                             self.samplestart,
                                             self.sampleend,
                                             self.crosscode)
        headers=[hv[0] for hv in phenotypedata.values()[0]]
        #open a csvwriter
        with open(newfilepath,"wb") as fileob:
            writer=csv.writer(fileob,delimiter=',',quoting=csv.QUOTE_MINIMAL)
            #add rows
            header1=headers+["ID"]+self.markernames
            writer.writerow(header1)
            header2=["" for h in headers]+[""]+self.chromosomes
            writer.writerow(header2)
            header3=["" for h in headers]+[""]+self.kilobases
            writer.writerow(header3)

            for i in range(len(self)):
                samplename=self.samplenames[i]
                entryfromphenotypedata=phenotypedata.get(samplename,None)
                if entryfromphenotypedata:
                    genotypes=self.genotypelookup[samplename]
                    if genotypes:
                        row=[hv[1] for hv in entryfromphenotypedata]+[samplename]+genotypes
                        writer.writerow(row)
            fileob.close()

class GFFReader(_CsvReader):
    delimiter="\t"
    include_in_format_search=False
    checks=[("A1","##gff-version (\d)","gffversion")]
    ranges=[("A1:XFD1048576","databox")]
    headers=[("chromosome",str),
             ("source",str),
             ("feature",str),
             ("start",int),
             ("end",int),
             ("score",float),
             ("strand",str),
             ("frame",str),
             ("attributes",str)]
    featureterminator="###"

    def splitattributes(self,attributestring):
        output={}
        for section in attributestring.split(";"):
            if section:
                k,v=section.split("=")
                output[k]=urllib2.unquote(v)
        return output

    def splitrow(self,rowlist):
        output={}
        for r,(h,ht) in zip(rowlist,self.headers):
            try:
                output[h]=ht(r)
            except:
                output[h]=None
        return output

    def parse(self):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)

            self.shareddata={"header":[hp[0] for hp in self.headers],
                             "attributes":[],
                             "nfeatures":0,
                             "chromosomes":[]}
            self.rowdata=[]
            for row in dataranges["databox"]:
                if row[0]==self.featureterminator:
                    break
                elif row[0][0]=="#":
                    continue
                else:
                    assert len(row)==9
                    rowdict=self.splitrow(row)
                    attdict=self.splitattributes(rowdict.get("attributes",""))
                    for k in attdict.keys():
                        if k not in self.shareddata["attributes"]:
                            self.shareddata["attributes"].append(k)
                    rowdict.update(attdict)
                    self.shareddata["nfeatures"]+=1
                    rowdict["rownumber"]=self.shareddata["nfeatures"]
                    if rowdict["chromosome"] not in self.shareddata["chromosomes"]:
                       self.shareddata["chromosomes"].append(rowdict["chromosome"])
                    self.rowdata.append(rowdict)
            return self.shareddata,self.rowdata

class StrainData(GenotypeData):
    include_in_format_search=True
    expectedheaders=["name","note","Alias","Source","PlateLayout",
                     "Ignore","Parent1","Parent2","Group","rQTLgroup",
                     "Background","MAT","GenotypeFile",
                     "ho-","HYG+","G418+","leu-","lys-","met-","ura-"]
    checks=[("A1","(name)",None),
            ("B1","(note)",None),
            ("C1","(Alias)",None),]
    ranges=[("A2:A1000000","strains"),
            ("A1:M1","headers"),
            ("N1:T1","auxotrophyheaders"),
            ("A2:M1000000","data"),
            ("N2:T1000000","auxotrophydata")]

    def parse(self):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            #read in ranges
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)
            headers=self.shareddata["headers"]=dataranges["headers"]
            data=self.shareddata["data"]=dataranges["data"]
            strains=self.shareddata["strains"]=dataranges["strains"]
            
            self.rowdata=[]
            self.genotypelookup={}
            self.genotypes={}
            for i in range(len(data)):
                datadict=dict(zip(headers,data[i]))
                ST=strains[i]
                datadict.update({"index":i,
                                 "strain":ST,
                                 "genotypes":self.genotypelookup.get(ST,[])})
                self.rowdata.append(datadict)
            return self.shareddata,self.rowdata

class CsvPlateLayoutReader(_CsvReader):
    """
    >>> testfilename="Example layout 384.csv"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
    >>> r=CsvPlateLayoutReader(testfilepath)
    >>> sd,rd = r.parse()
    >>> print sd.keys()
    ['internalprefix', 'rows', 'platesize', 'columns']
    >>> print len(rd)
    384
    """
    include_in_format_search=True
    checks=[("A1",None,"internalprefix"),
            ("A2","(A)",None),
            ("B1","(1)",None)]
    ranges=[("B1:AW1","plate column numbers"),
            ("A2:A33","plate row letters"),
            ("B2:AW33","samplenames")]

    def __init__(self,filepath,passerrorsto=None):
        if passerrorsto is not None:
            self.passerrorsto=passerrorsto
        self.filepath=filepath
        self.shareddata={}
        self.rowdata=[]
        self.read_basic()

    def _coerce_to_string(self,entry):
        if type(entry)==float:
            if int(entry)==float(entry):
                entry=int(entry)
        if type(entry) in [int,float]:
            entry=str(entry)
        return entry

    def _fix_samplename(self,samplename):
        samplename=self._coerce_to_string(samplename)
        if "internalprefix" in self.shareddata:
            if type(self.shareddata["internalprefix"])==str:
                if not samplename.startswith(self.shareddata["internalprefix"]):
                    samplename=self.shareddata["internalprefix"]+samplename
        return samplename

    def parse(self):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)
            cols=self.shareddata["columns"]=dataranges["plate column numbers"]
            rows=self.shareddata["rows"]=dataranges["plate row letters"]
            self.shareddata["platesize"]=len(cols)*len(rows)
            samplename2D=dataranges["samplenames"]
            for ri,r in enumerate(rows):
                for ci,c in enumerate(cols):
                    welllabel="{}{}".format(c,r)
                    samplename=samplename2D[ri][ci]
                    samplename=self._fix_samplename(samplename)
                    self.rowdata.append({"welllabel":welllabel,
                                         "samplename":samplename})
            return self.shareddata,self.rowdata

    @classmethod
    def create(cls,filepath,platelayout):
        """
        data should be a simple list of strain names
        plate size deduced from length of list
        """
        if os.path.exists(filepath):
            LOG.warning("{} already exists"
                        .format(filepath))
            return
        delimiter=","
        plate=platelayout["plate"]
        platepositions=list(platelayout.yield_records())
        colheaders=[""]+list(plate.yield_colnumbers())
        rowheaders=list(plate.yield_rowletters())
        rowlength=len(colheaders)-1
        data=[pp["strain"].value for pp in platepositions]
        try:
            fileob=open(filepath,"wb")
            writer=csv.writer(fileob,delimiter=delimiter)
            writer.writerow(colheaders)
            i=0
            for rowheader in rowheaders:
                writer.writerow([rowheader]+data[i:i+rowlength])
                i+=rowlength
            fileob.close()
            LOG.debug("saved {}"
                      .format(filepath))
            return filepath
        except Exception as error:
            LOG.error("unexpected write error for file {}: {}"
                      .format(filepath,error))
            self.is_OK=False
            return False

class XlsxPlateLayoutReader(_XlsxReader):
    """
    >>> testfilename="Example layout 384.xlsx"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
    >>> r=XlsxPlateLayoutReader(testfilepath)
    >>> sd,rd = r.parse()
    >>> print sd.keys()
    ['rows', 'platesize', 'columns']
    >>> print len(rd)
    384
    """
    include_in_format_search=True
    checks=[("A2","(A)",None),
            ("B1","(1)",None)]
    ranges=[("B1:AW1","plate column numbers"),
            ("A2:A33","plate row letters")]
    sheetnamelookup=[("Samplenames","strain"),
                     ("Groupnames","groupid"),
                     ("Backgrounds","background"),
                     ("Matingtypes","matingtype")]
    datarange="B2:AW33"

    def __init__(self,filepath,passerrorsto=None):
        if passerrorsto is not None:
            self.passerrorsto=passerrorsto
        self.filepath=filepath
        self.shareddata={}
        self.rowdata=[]
        self.read_basic()

    def _get_good_sheets(self):
        allsheets=self.workbook.sheet_names()
        goodsheets=[]
        for sheetname in allsheets:
            if self.is_correct_format(sheetname=sheetname,report=False):
                goodsheets.append(sheetname)
                LOG.debug("{}: incorporating sheet {} from {}"
                          .format(self.__class__.__name__,
                                  sheetname,self.filepath))
            else:
                LOG.debug("{}: not incorporating sheet {} from {}"
                          .format(self.__class__.__name__,
                                  sheetname,self.filepath))
        #Doing this again ensures self.shareddata["internalprefix"] is set right...
        self.is_correct_format(sheetname="Samplenames",report=False) 
        return goodsheets

    def _coerce_to_string(self,entry):
        if type(entry)==float:
            if int(entry)==float(entry):
                entry=int(entry)
        if type(entry) in [int,float]:
            entry=str(entry)
        return entry

    def _fix_samplename(self,samplename):
        samplename=self._coerce_to_string(samplename)
        if "internalprefix" in self.shareddata:
            if type(self.shareddata["internalprefix"])==str:
                if not samplename.startswith(self.shareddata["internalprefix"]):
                    samplename=self.shareddata["internalprefix"]+samplename
        return samplename

    def parse(self):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            sheetnames=self._get_good_sheets()
            dataranges={}
            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename,sheetnames[0])
            cols=self.shareddata["columns"]=[int(x) for x in dataranges["plate column numbers"]]
            rows=self.shareddata["rows"]=dataranges["plate row letters"]
            self.shareddata["platesize"]=len(cols)*len(rows)
            sheetdata={}
            for sheetname in sheetnames:
                if sheetname[-1]=="s":
                    dataname=sheetname[:-1].lower()
                else:
                    dataname=sheetname.lower()
                sheetdata[dataname]=self.read_cell_range(self.datarange,sheetname)

            for ri,r in enumerate(rows):
                for ci,c in enumerate(cols):
                    welllabel="{}{}".format(r,c)
                    otherdatatypes={}
                    for dataname in sheetdata:
                        entry=sheetdata[dataname][ri][ci]
                        if dataname=="samplename":
                            entry=self._fix_samplename(entry)
                        else:
                            entry=self._coerce_to_string(entry)
                        otherdatatypes[dataname]=entry
                    self.rowdata.append(dict({"welllabel":welllabel},**otherdatatypes))
            return self.shareddata,self.rowdata

    @classmethod
    def create(cls,filepath,platelayout):
        """
        """
        filepath=os.path.splitext(filepath)[0]+".xls"

        if os.path.exists(filepath):
            LOG.info("{} already exists".format(filepath))
            return
        plate=platelayout["plate"]
        platepositions=list(platelayout.yield_records())
        colheaders=list(plate.yield_colnumbers())
        rowheaders=list(plate.yield_rowletters())
        sheetnamelookupdict=dict(cls.sheetnamelookup)

        try:
            import xlwt
        except:
            LOG.error("COULD NOT IMPORT xlwt; module not found. Therefore could not create xls file."
                      "Therefore trying CsvPlateLayoutReader.create() instead.")
            filepath=os.path.splitext(filepath)[0]+".csv"
            return CsvPlateLayoutReader.create(filepath,platelayout)
        try:
            WB=xlwt.Workbook()

            for sheetname,query in cls.sheetnamelookup:
                thissheet=WB.add_sheet(sheetname)
                for i,ch in enumerate(colheaders):
                    thissheet.write(0,i+1,ch)
                for i,rl in enumerate(rowheaders):
                    thissheet.write(i+1,0,rl)                
                for pp in platepositions:
                    thissheet.write(pp["wellrow"].value,pp["wellcol"].value,pp[query].value)
            WB.save(filepath)
            LOG.info("saved {}"
                     .format(filepath))
            return filepath
        except:
            LOG.error("failed to create {}"
                      .format(filepath))
            return False

class rQTLinputReader(GenotypeData):
    include_in_format_search=True
    checks=[("A2",None,None),
            ("A3",None,None),
            ("A4","([\.^0-9]+)",None)]
    ranges=[("A1:XFD1","headerbox1"),
            ("A2:XFD2","headerbox2"),
            ("A3:XFD3","headerbox3"),
            ("A4:XFD1048576","databox")]
    filenamereader=rQTLFileNameReader

    def parse(self):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            if hasattr(self,"filenamereader"):
                filename=examine_path(self.filepath)["filename"]
                fnr=self.filenamereader(filename)
                if fnr.get_is_OK():
                    self.shareddata.update(fnr.properties)

            #read in ranges
            dataranges={}

            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename)
            
            toprow=dataranges["headerbox1"]
            secondrow=dataranges["headerbox2"]
            secondrow_nonblank=0
            for c in secondrow:
                if not c:
                    secondrow_nonblank+=1
                else:
                    break
            try:
                idcolumn=toprow.index("ID")
            except:
                idcolumn=None
            if idcolumn:
                assert idcolumn==secondrow_nonblank-1
            firstgenocol=secondrow_nonblank
            self.phenotypeheaders=self.shareddata["phenotypeheaders"]=dataranges["headerbox1"][:secondrow_nonblank]
            self.markernames=self.shareddata["markernames"]=dataranges["headerbox1"][firstgenocol:]
            self.chromosomes=self.shareddata["chromosomes"]=[int(c) for c in dataranges["headerbox2"][firstgenocol:]]
            self.kilobases=self.shareddata["kilobases"]=[int(k) for k in dataranges["headerbox3"][firstgenocol:]]
            self.alleles=self.shareddata["alleles"]=[]
            self.strains=[]
            if max(self.kilobases)<=9999:
                altformat="c{:02d}-{:03d}k"
            else:
                altformat="c{:02d}-{:07d}"
            self.markeraltnames=self.shareddata["markeraltnames"]=[altformat.format(self.chromosomes[gi],self.kilobases[gi]) for gi in range(len(self.markernames))]

            self.nreadings=0
            for row in dataranges["databox"]:
                self.nreadings+=1
                def tryconvert(v):
                    try:
                        return float(v)
                    except:
                        return str(v)
                phenotyperow=[tryconvert(v) for v in row[:secondrow_nonblank]]
                if not idcolumn:
                    if type(phenotyperow[-1])==str:
                        idcolumn=len(phenotyperow)
                if idcolumn:
                    strain=self.convert_sample_label(row[idcolumn])
                else:
                    strain=self.nreadings
                self.strains+=[strain]
                genotyperow=row[secondrow_nonblank:]
                genotyperow_nonblanks=[a for a in genotyperow if a not in ["-",""]]
                rowalleles="".join(sorted(set(genotyperow_nonblanks)))
                if rowalleles not in self.alleles:
                    self.alleles.append(rowalleles)
                self.rowdata.append({"phenotyperow":phenotyperow,
                                     "phenotypedict":dict(zip(self.phenotypeheaders,phenotyperow)),
                                     "strain":strain,
                                     "genotyperow":genotyperow,
                                     "genotypedict":dict(zip(self.markeraltnames,genotyperow))})
            #if FS, permutation blocks derived from strain names
            if not idcolumn:
                LOG.debug("No ID column so only one permutation block used")
            elif set(list([str(s)[:2] for s in self.strains]))==set(["FS"]):
                LOG.info("FS strains detected, so matching permutation blocks to tetrads")
                self.permutationblocks=[int(ceil(float(str(s)[2:])/4.0)) for s in self.strains]
            else:
                LOG.debug("Not FS strains so only one permutation block used")
                self.permutationblocks=[1]*len(self.strains)
        return self.shareddata,self.rowdata

    @classmethod
    def create(cls,shareddata,rowdata,filepath):
        """
        shareddata must be dict containing these headers:
            "markernames",
            "phenotypeheaders"
        and optionally (otherwise deduced from markernames):
            "chromosomes",
            "geneticpositions"
        rowdata must be a list of dictionaries, each with the headers:
            "phenotyperow"
            "strain",
            "genotyperow"
        """
        phenotypeheaders=shareddata.get("phenotypeheaders",[])
        markernames=shareddata.get("markernames",[])
        chromosomes=shareddata.get("chromosomes",[])
        geneticpositions=shareddata.get("geneticpositions",[])
        #
        with open(filepath,"wb") as fileob:
            writer=csv.writer(fileob,delimiter=',',quoting=csv.QUOTE_MINIMAL)
            #add rows
            row1=list(phenotypeheaders)+["ID"]+list(markernames)
            row2=[""]*(len(phenotypeheaders)+1)+list(chromosomes)
            row3=[""]*(len(phenotypeheaders)+1)+list(geneticpositions)
            writer.writerow(row1)
            writer.writerow(row2)
            writer.writerow(row3)
            for row in rowdata:
                newrow=list(row["phenotyperow"])+list([row["strain"]])+list(row.get("genotyperow",[]))
                writer.writerow(newrow)
            fileob.close()
            LOG.info("rQTLinputReader created {}"
                     .format(filepath))
            return True

    @classmethod
    def create_from_object(cls,ob,*args,**kwargs):
        """
        Can accept CombiReadings(), ControlledExperiment(), CombiFile()

        args are one or more PhenotypeCalculators, each one generating a
        column in the resulting rQTL file

        If kwarg averagereplicates is True, then this effect is applied last

        If kwarg skipnogenotypes is True, then any strains lacking
        genotype information will be left out of the rQTL file.
        """
        
        T=ob.__class__.__name__
        if T in ["ControlledExperiment","CombiFile"]:
            if not ob.timevalues():
                LOG.error("no timevalues for {}".format(ob))
                return False
            CF=ob["combifile"]
            SFN=CF.get_subfoldername()
            LOG.debug("got subfolder {}".format(SFN))
            if not ob["timespan"].is_sufficient(fortext="output_to_rQTL"):
                return False
            if not args:
                args=ob["treatment"].get_phenotypecalculators()
        elif T=="CombiReadings":
            SFN=""
            if not args:
                args=[PrintedMassCalc,PrintedMassControlledCalc]

        phenotypecalculators=[a(ob) for a in args]
        
        skipnoalleles=kwargs.setdefault("skipnoalleles",True)
        remove_ignore=kwargs.setdefault("remove_ignore",True)
        combine_replicates=kwargs.setdefault("combine_replicates",False)
        
        headertag=','.join(flatten([pc.get_external_headers() for pc in phenotypecalculators]))
        #
        filepaths=[]
        for rqtlgroup,recs in split_records_by_rQTLgroup(ob).items():
            if rqtlgroup:
                recs=screen_records(recs,**kwargs)
            if T in ["ControlledExperiment","CombiFile"]:
                if not recs:
                    LOG.error("no valid recs after screening for "
                              "ControlledExperiment {} rqtlgroup {}"
                              .format(ob.value,rqtlgroup))
                    continue
            kw2=kwargs.copy()
            kw2.setdefault("prefix","rQTL")
            kw2.setdefault("suffix","{} {}".format(headertag,rqtlgroup))
            kw2.setdefault("extension","csv")
            filepath=ob.get_graphicspath(experimentfolder=SFN,
                                         **kw2)
            PF="{plotfolder}/{userfolder}/{prefix}{graphicsnameroot}{suffix}.{extension}"
            copyto=ob.get_graphicspath(pathformatter=PF,
                                       plotfolder=Locations()["rqtlinput"],
                                       **kw2)
            if T in ["CombiReadings"]:
                if not recs:
                    LOG.error("no valid recs after screening for "
                              "CombiReadings rqtlgroup {}"
                              .format(rqtlgroup))
                    continue
                UD=os.path.split(Locations().get_userpath())[-1]
                filename=("rQTL CombiReadings {} {}.csv"
                          .format(UD,rqtlgroup))
                filepath=os.path.join(Locations().get_plotspath(),
                                      filename)
                copyto=os.path.join(Locations()["rqtl input"],
                                    filename)
            #Prepare data
            rowdata=[]
            shareddata={}
            allalleles=[]
            allvalidalleles=[]
            markers=False
            for r in recs:
                AL=r.alleles()
                if AL and not markers:
                    markers=r.markers()
                if AL is False:
                    AL=[]
                LOG.debug("Added {} alleles for {}"
                          .format(len(AL),r["strain"].value))
                allalleles.append(AL)
                if AL:
                    allvalidalleles.append(AL)
            #This section cuts out any markers that are blank for all the strains
            if allvalidalleles:
                mask=get_allnone_mask(allvalidalleles)
                #mask is list of every index that has None in every sublist
            if mask and markers:
                LOG.info("Masking markers with allnone_mask ({} indices removed)"
                         .format(len(mask)))
                maskedMN=mask_by_index(markers["markernames"],mask)
                maskedCH=mask_by_index(markers["chromosomes"],mask)
                maskedGP=mask_by_index(markers["geneticpositions"],mask)
            elif markers:
                LOG.debug("No marker masking required")
                maskedMN=markers["markernames"]
                maskedCH=markers["chromosomes"]
                maskedGP=markers["geneticpositions"]
            else:
                if not markers:
                    LOG.debug("No markers found for {}".format(ob.value))
                maskedMN,maskedCH,maskedGP=[],[],[]

            #now collect alleles (masked if necessary) for each strain
            alleledict={}
            for r,AL in zip(recs,allalleles):
                if AL:
                    key=r["strain"].value
                    if key not in alleledict:
                        if mask:
                            m=mask_by_index(AL,mask)
                        else:
                            m=AL
                        alleledict[key]=m

            """
            shareddata must be dict containing these headers:
                "markernames",
                "phenotypeheaders"
            and optionally (otherwise deduced from markernames):
                "chromosomes",
                "geneticpositions"
            rowdata must be a list of dictionaries, each with the headers:
                "phenotyperow"
                "strain",
                "genotyperow"
            """
            headers=flatten([pc.get_header_list() for pc
                             in phenotypecalculators])
            shareddata={"markernames":maskedMN,
                        "chromosomes":maskedCH,
                        "geneticpositions":maskedGP,
                        "phenotypeheaders":headers}
            
            rowdata=[]
            goahead=True
            for r in recs:
                name=r["strain"].value
                if remove_ignore and r["ignore"].value:
                    continue
                if skipnoalleles and name not in alleledict:
                    continue
                PL=[]
                for pc in phenotypecalculators:
                    try:
                        PL.append(pc.get_phenotype_list(r))
                    except Exception as e:
                        LOG.error("problem with get_phenotype_list for phenotypecalculator {} "
                                  "for record {} so abandoning creation of {}, because {} {}"
                                  .format(pc.__class__.__name__,r.value,filepath,e,get_traceback()))
                        goahead=False
                PR=flatten(PL)
                rowdata.append({"phenotyperow":PR,
                                "strain":r["strain"].value,
                                "genotyperow":alleledict.get(name,[])})

            if goahead:
                rowdata2=sorted(rowdata,key=lambda k:k["strain"])
                try:
                    cls.create(shareddata,rowdata2,filepath)
                    #LOG.info("created rQTLinput {}".format(filepath))
                    filepaths.append(filepath)
                    try:
                        copy_to(filepath,copyto)
                        LOG.info("created copy of rQTLinput {}"
                                 .format(copyto))
                    except Exception as e:
                        LOG.error("couldn't copy rQTLinput {} because {} {}"
                                  .format(copyto,e,get_traceback()))
                except Exception as e:
                    LOG.error("couldn't create rQTLinput {} because {} {}"
                              .format(filepath,e,get_traceback()))
        return filepaths
#
class rQTLoutputdigestReader(_XlsxReader):
    include_in_format_search=False
    checks=[("A1","(Worksheet)",None),
            ("A2","(README)",None),
            ("A3","(Overview)",None),
            ("A4","(QTL Intervals)",None)]
    ranges=[("A1:XFD1","headers"),
            ("A2:XFD1048576","databox")]
    sheetnamelookup=[("README","readme"),
                     ("Overview","overview"),
                     ("QTL Intervals","qtlintervals")]
    datarange="A2:N1048576"

    def parse(self):
        if not self.is_correct_format(report=False):
            LOG.error("{} is not in the correct format for {}"
                      .format(self.filepath,self.__class__.__name__))
        else:
            #read in ranges
            dataranges={}

            for cellrangename,descriptor in self.ranges:
                dataranges[descriptor]=self.read_cell_range(cellrangename,
                                                            sheetname="QTL Intervals")
            
            headers=dataranges["headers"]
            self.shareddata={"headers":headers}
            self.rowdata=[]
            
            self.nqtls=0
            for row in dataranges["databox"]:
                self.nqtls+=1
                def tryconvert(v):
                    try:
                        return float(v)
                    except:
                        return str(v)
                convertedrow=[tryconvert(v) for v in row]
                self.rowdata.append(dict(zip(headers,convertedrow)))
            self.shareddata["nqtls"]=self.nqtls
        return self.shareddata,self.rowdata


#DIRECTORYMONITOR #############################################################
class DirectoryMonitor(object):
    """
    >>> testfolderpath=os.path.join(Locations().rootdirectory,"tests")
    >>> dm=DirectoryMonitor(testfolderpath)
    >>> print len(dm)
    19
    """
    ignoreprefixes="~_["
    def __init__(self,directory=None,dig=False,include=None,exclude=[],report=True):
        """
        >>> testfolderpath=os.path.join(Locations().rootdirectory,"tests")
        >>> dm=DirectoryMonitor(testfolderpath)
        >>> print len(dm)
        19
        """
        self.scriptdirectory=self.get_script_directory()
        self.dig=dig
        self.include=include
        self.exclude=exclude
        self.report=report
        if directory is None:
            directory=self.choose_directory()
        self.directory=directory
        self.paths=sorted(self.includeexcludefiles(dig=dig,
                                                   include=include,
                                                   exclude=exclude))

    def __str__(self):
        return "DirectoryMonitor({})".format(self.directory)

    def __len__(self):
        """
        >>> testfolderpath=os.path.join(Locations().rootdirectory,"tests")
        >>> dm=DirectoryMonitor(testfolderpath)
        >>> print len(dm)
        19
        """
        return len(self.paths)

    def __iter__(self):
        """
        >>> testfolderpath=os.path.join(Locations().rootdirectory,"tests")
        >>> dm=DirectoryMonitor(testfolderpath)
        >>> print os.path.basename(list(dm.__iter__())[1])
        EX1b (YPD) [Basic384] t+0 (example 2).csv
        """
        for filepath in self.paths:
            yield filepath

    def __getitem__(self,query):
        """
        Different results depending on input type, e.g.
        
        >>> testfolderpath=os.path.join(Locations().rootdirectory,"tests")
        >>> dm=DirectoryMonitor(testfolderpath)
        >>> filename="EX1b (YPD) [Basic384] t+0 (example 2).csv"
        >>> print os.path.basename(dm[1])     #returns path with index 1
        EX1b (YPD) [Basic384] t+0 (example 2).csv
        >>> fullpath=os.path.join(testfolderpath,filename)
        >>> print dm[fullpath]  #returns index of path
        1
        >>> print os.path.basename(dm["EX1b"])  #returns first path containing "TEST1x"
        EX1b (YPD) [Basic384] t+0 (example 2).csv
        """
        if type(query)==int:
            return self.paths[query]
        elif type(query)==str:
            if query in self.paths:
                return self.paths.index(query)
            else:
                for path in self.paths:
                    if query in path:
                        return path

    def includeexcludefiles(self,dig=False,include=None,exclude=[".db"]):
        """
        Any file that begins with one of the characters in ignoreprefixes
        will be ignored (by default, ~, _ and [)
        Otherwise, particular extensions can be included or excluded
        """
        self.excluded_by_prefix=[]
        self.excluded=[]
        self.not_included=[]
        for path in self.yield_files(self.directory,dig=dig):
            filename=os.path.basename(path)
            if filename[0] in self.ignoreprefixes:
                self.excluded_by_prefix.append(path)
                if self.report:
                    LOG.debug("ignoring {} because first character in ignoreprefixes"
                              .format(filename))
                continue
            else:
                path=os.path.normpath(self.rename_bad_characters(path))
                filename=os.path.basename(path)
                extension=os.path.splitext(filename)[-1]
                if extension in exclude:
                    self.excluded.append(path)
                elif include is not None and extension not in include:
                    self.not_included.append(path)
                else:
                    yield self.pathsafe(path)
        if self.excluded_by_prefix:
            if self.report:
                LOG.info("{} files excluded based on ignoreprefixes"
                         .format(len(self.excluded_by_prefix)))
        if self.excluded:
            if self.report:
                LOG.info("{} files excluded because extension in {}"
                         .format(len(self.excluded),exclude))
        if self.not_included:
            if self.report:
                LOG.info("{} files not included because extension NOT in {}"
                         .format(len(self.not_included),include))

    def pathsafe(self,path):
        """
        should make paths safe as "/" is universal and works on windows as well as linux
        """
        return os.path.normpath(path)

    def rename_bad_characters(self,path):
        """
        Filenames might contain bad characters that confuse ActivePython, e.g. slanted quotemarks
        In the interactive window these are rendered as a '91' or '92' block character
        while copying and pasting from an NXclient window renders these as characters that cannot be
        encoded in the script by ActivePython when the script is saved
        I haven't really worked out how to best handle these yet
        """
        path=self.pathsafe(path)
        assert os.path.exists(path)
        root,filename=os.path.split(path)
        acceptable=list(" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,_+-=!^~(){}[]'@&#%$\\;")
        output=[]
        for i,character in enumerate(filename):
            if ord(character) in [145,146]:
                LOG.error("bad quote mark {} at index {}"
                          .format(character,i))
                character="'"
            elif character not in acceptable:
                LOG.error("unacceptable character {} at index {}"
                          .format(character,i))
                character="~"
            output.append(character)
        newfilename="".join(output)
        if filename!=newfilename:
            LOG.critical("YOU SHOULD rename {} (e.g. to {}) before proceeding"
                         .format(filename,newfilename))
            sys.exit()
            #or could ask, if line above is removed
            answer=raw_input("SHOULD I RENAME {} TO {}?"
                             .format(filename,newfilename))
            if answer in ["yY"]:
                LOG.warning("DBFileManager found dodgy path name {} and renamed it {} to be OK".format(filename,newfilename))
                os.rename(os.path.join(root,filename),
                          os.path.join(root,newfilename))
        return os.path.join(root,newfilename)

    def get_script_directory(self):
        """
        returns the directory from which the script is being run
        """
        return os.path.dirname(os.path.realpath(sys.argv[0]))

    def set_script_directory(self):
        """
        returns False if script directory is already current working directory
        """
        sd=self.get_script_directory()
        if sd==os.getcwd(): return False
        os.chdir(sd)
        return True

    def is_free_to_create(self,path):
        """
        returns False if path already exists
        >>> testfolderpath=os.path.join(Locations().rootdirectory,"tests")
        >>> dm=DirectoryMonitor(testfolderpath)
        >>> existingfilepath=dm[1]
        >>> print dm.is_free_to_create(existingfilepath)
        False
        >>> notexistingfilepath=os.path.join(testfolderpath,"tocreate.txt")
        >>> print dm.is_free_to_create(notexistingfilepath)
        True
        """
        return not os.path.exists(path)


    def yield_subdirectories(self,path,dig=False):
        """
        if dig=True than function walks through subdirectories of subdirectories etc
        otherwise remains in the specified directory
        """
        assert os.path.isdir(path)
        if dig:
            for root,dirs,files in os.walk(path,topdown=True):
                for name in dirs:
                    yield self.pathsafe(os.path.join(root,name))
        else:
            for subpath in os.listdir(path):
                if os.path.isdir(os.path.join(path,subpath)):
                    yield self.pathsafe(os.path.join(path,subpath))

    def yield_files(self,path,dig=False):
        """
        if dig=True than function walks through subdirectories of subdirectories etc
        otherwise remains in the specified directory
        """
        assert os.path.isdir(path)
        if dig:
            for root,dirs,files in os.walk(path,topdown=True):
                for name in files:
                    yield self.pathsafe(os.path.join(root,name))
        else:
            for subpath in os.listdir(path):
                if os.path.isfile(os.path.join(path,subpath)):
                    yield self.pathsafe(os.path.join(path,subpath))
                

    def rename_with_error(self,path,errormessage="DefaultError"):
        """
        If DBOS encounters a file it has trouble with, it renames the file with the
        error in square brackets at the start of the filename.
        Files are flagged this way for user attention and will be
        ignored by DBOS until fixed and renamed without the [error message]
        This change is logged.
        """
        error="[{}] ".format(errormessage)
        parts=os.path.split(path)
        newpath=os.path.join(parts[0],error+parts[1])
        os.rename(path,newpath)
        return newpath

    def move_sourcefile(self,path,destination=None):
        """
        Moves file at path to subfolder "destination"
        This change is logged.
        """
        if destination is None:
            destination=os.path.splitext(path)[0]
        if not self.free_to_create(path):
            LOG.warning("Unable to move sourcefile {} to {} as path is not free to create")
            return False
        newpath=os.path.join(destination,
                             os.path.split(path)[-1])
        if prepare_path(newpath):
            os.rename(path,newpath)
            LOG.info("DirectoryMonitor: moved {} to {}"
                     .format(path,newpath))
            return newpath
        return False

    def revert_sourcefile(self,path):
        """
        Undoes "move_sourcefile"
        NOT YET IMPLEMENTED
        """
        pass


#

#DBASE BASICS #################################################################
class DBase(object):
    """
    Wrapper for Pytables, handling files, modes, table objects, writing and reading
    and preventing problems caused by e.g. having multiple table objects open
    """
    fileob=None
    table=None
    autobackup=False

    def __init__(self,filepath):
        LOG.debug("instantiating new DBase object connected to {}"
                  .format(filepath))
        if not os.path.exists(filepath):
            LOG.info("will create new DBase file {}"
                     .format(filepath))
            prepare_path(os.path.dirname(filepath))
            populate_test_table=True
        
        self.filepath=filepath
        
        if DBase.autobackup:
            self.backup()
            
        self._open_all()
        
        if getattr(self,"populate_test_table",False):
            #This helps with doctest, by ensuring no errors on the first
            #doctest runthrough.
            DBTable.db=self
            dr=DBRecord(3, 4, 5.0)
            dr.store(check=False)

    def backup(self):
        DIR,FN=os.path.split(self.filepath)
        BN,EXT=os.path.splitext(FN)
        backupfilepath=os.path.join(DIR,BN+".backup")
        try:
            shutil.copy(self.filepath,backupfilepath)
            LOG.info("backed up dbase to {}"
                     .format(backupfilepath))
        except Exception as e:
            LOG.warning("couldn't backup dbase to {} because {}"
                        .format(backupfilepath,e))

    def __str__(self):
        return "DBase({}): <{}>".format(self.filepath,self.fileob)

    def __len__(self):
        return len(self.tablenames)

    def display_all(self):
        try:
            print self.fileob.listNodes("/") #pytables v2
        except AttributeError:
            print self.fileob.list_nodes("/") #pytables v3
        except Exception as e:
            LOG.critical("Unable to run PyTables listNodes (v2) "
                         "or list_nodes (v3) because {} {}"
                         .format(e,get_traceback()))

    def __iter__(self):
        for i in self.fileob:
            if type(i).__name__=="Table":
                self.table=i
                yield i
 
    def __getitem__(self,tab):
        """
        tab can be the tablepath as a string, or a DBTable subclass.
        In the latter case, if the table doesn't yet exist,
        __getitem__ will create it
        """
        if type(tab)==str:
            if tab!=self.table._v_pathname:
                try:
                    self.table=self.fileob.getNode(tab) #pytables v2
                except AttributeError:
                    self.table=self.fileob.get_node(tab) #pytables v3
                except Exception as e:
                    LOG.critical("Unable to run PyTables getNode (v2) "
                                 "or get_node (v3) because {} {}"
                                 .format(e,get_traceback()))
        elif issubclass(tab.__class__,DBTable):
            if tab.tablepath in self.fileob:
                try:
                    self.table=self.fileob.getNode(tab.tablepath) #pytables v2
                except AttributeError:
                    self.table=self.fileob.get_node(tab.tablepath) #pytables v3
                except Exception as e:
                    LOG.critical("Unable to run PyTables getNode (v2) "
                                 "or get_node (v3) because {} {}"
                                 .format(e,get_traceback()))
            else:
                self.create_table(tab)
        return self.table

    def create_table(self,dbtable_instance):
        tabpath=dbtable_instance.tablepath
        TABPTH,TABNM=os.path.split(tabpath)
        DESC=dbtable_instance.recordclass._get_description()
        TIT=dbtable_instance.__class__.__name__
        try:
            PTH=self.fileob._getOrCreatePath(TABPTH,True) #pytables v2
        except AttributeError:
            PTH=self.fileob._get_or_create_path(TABPTH,True) #pytables v3
        except Exception as e:
            LOG.critical("Unable to run PyTables _getOrCreatePath (v2) "
                         "or get_or_create_path (v3) because {} {}"
                         .format(e,get_traceback()))
        self.table=self.fileob.create_table(PTH,
                                            TABNM,
                                            description=DESC,
                                            title=TIT)

    def _open_all(self,mode='a'):
        self.fileob=tbs.open_file(self.filepath,mode)
        self.tablenames=[i._v_pathname for i in self]

    def change_mode(self,mode):
        if mode!=self.fileob.mode:
            self.fileob.close()
            self._open_all(mode)
            return mode
        return False

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        try:
            self.fileob.close()
        except:
            LOG.debug("failed to close DBase({}).fileob"
                      .format(self.filepath))
        self.fileob=None

    def __del__(self):
        self.__exit__(None,None,None)
        
    def delete(self):
        os.remove(self.filepath)

class DBAtom(object):
    """
    The superclass of all basic record units.

    >>> a=DBAtom() # Can instantiate an empty atom and fill it later...
    >>> print a.set_value(3) # ...like this.
    3

    >>> print DBAtom(4) # Or can instantiate the atom when you create it.
    4

    >>> print DBAtom.from_string('4')
    4

    >>> if a:
    ... 	print "a.__nonzero__()==True"
    a.__nonzero__()==True
    
    >>> print a.is_valid() # If a.value in [None,np.NaN]: a.is_valid()==False
    True

    >>> print str(a)
    3

    >>> print a._get_match_condition_unit() # This is the database condition that should return records with this DBAtom
    (dbatom==3)

    >>> print a._get_txt_header_unit()
    dbatom

    >>> print a._get_txt_row_unit()
    3

    >>> print a._get_display_header_unit() 
    dbatom

    >>> print a._get_display_row_unit() # Called by any DBRecord that contains this atom and wants to display itself.
    3

    """
    coltype=tbs.UInt8Col()
    invalid_values=[None,"-","",np.nan,float('nan')]
    strict=True
    #pretty="~{}~"
    def __init__(self,value=None,record=None,dbasenameroot=None):
        """
        >>> a=DBAtom() # Can instantiate an empty atom and fill it later...
        >>> print a.set_value(3) # ...like this.
        3

        >>> print DBAtom(4) # Or can instantiate the atom when you create it.
        4
        """
        if record is not None:
            self.record=self.passerrorsto=record
        if dbasenameroot is not None:
            self.dbasenameroot=dbasenameroot
        if value is not None:
            self.set_value(value)
        else:
            self.value=None

    def check_value(self,value):
        if value is None:
            return None
        if not self.is_valid(value):
            return None
        if isinstance(value,DBAtom):
            value=value.value
        if type(value) in [unicode,str,np.string_]:
            is_string=True
        else:
            is_string=False
        scn=self.__class__.__name__
        try:
            converted=np.array([value],dtype=self.coltype.dtype)[0]
        except:
            LOG.error("{} unable to convert {}({}) into {}"
                      .format(scn,type(value),value,self.coltype.dtype))
            converted=None
        try:
            if is_string:
                similar= str(value)==str(converted)
            else:
                similar= abs(converted-value)<=abs(0.0001*converted)
        except Exception as e:
            if converted is not None:
                LOG.error("{}: unable to calculate difference between"
                          " value {}({}) and converted {}({})"
                          "because {} {}"
                          .format(scn,type(value),value,
                                  type(converted),converted,
                                  e,get_traceback()))
            similar=None

        if self.strict:
            if converted is not None and similar==False:
                try:
                    difference=abs(converted-value)
                except:
                    difference="??"
                try:
                    differencemargin=abs(0.0001*converted)
                except:
                    differencemargin="??"
                
                LOG.error("{}: difference ({}) between value {}({})"
                          " and converted {}({}) is {} (greater than"
                          " value*0.0000001 {})"
                          .format(scn,difference,type(value),value,
                                  type(converted),converted,
                                  difference,differencemargin))
                return None
        if converted is not None:
            return converted
        else:
            return None
        

    def set_value(self,value=None):
        """
        Checks value and if it passes, sets self.value with it.
        >>> a=DBAtom() # Can instantiate an empty atom and fill it later...
        >>> print a.set_value(3) # ...like this.
        3
        """
        if value==0.0:
            self.value=value
            return self.value
        if not self.is_valid(value):
            value=self.nullvalue
            converted=None
        else:
            converted=self.check_value(value)
        if converted is not None:
            self.value=converted
            #If this is also a DBRecord,then changing the value of this needs
            #to update the default atom as well.
            if hasattr(self,"_set_default_atom"):
                self._set_default_atom(converted)
            #If this IS the default atom of a DBRecord, then this needs to update the
            #value of the DBRecord._from_txt_row
            rec=self.get_record() 
            if hasattr(rec,"defaultlookup"):
                if self.__class__.__name__.lower()==rec.defaultlookup:
                    rec.value=converted
        else:
            self.value=self.nullvalue
        return self.value

    def alter_value(self,altered_value):
        """
        Leaves self.value alone but creates a second altered_value variable.
        This doesn't affect actually change the atom or affect its match_condition
        until update_from_altered() is called.
        """
        if self.check_value(altered_value):
            self.altered_value=altered_value
        else:
            LOG.error("{}.alter() check value {}({}) failed check_value "
                      "so not entered as altered_value"
                      .format(self.__class__.__name__, type(value), value))
            
    @classmethod
    def from_string(cls,stringvalue):
        """
        >>> print DBAtom.from_string('4')
        4
        """
        assert type(stringvalue)==str
        if stringvalue=="-":
            return cls()
        return cls(np.array([stringvalue],dtype=cls.coltype.dtype)[0])

    def __nonzero__(self):
        """
        >>> a0=DBAtom()
        >>> a1=DBAtom(3)
        >>> if a0:
        ... 	print "a0.__nonzero__()==False"
        
        >>> if a1:
        ... 	print "Or a1.__nonzero__()==True"
        Or a1.__nonzero__()==True
        """
        return self.is_valid(self.value)

    def is_valid(self,value=None):
        """
        Returns false if value (or self.value if value not provided) is in cls.invalid_values

        >>> a0=DBAtom()
        >>> a1=DBAtom.from_string("-")
        >>> a2=DBAtom(0)
        >>> a3=DBAtom(3)
        >>> print a0.is_valid()
        False
        >>> print a1.is_valid()
        False
        >>> print a2.is_valid()
        True
        >>> print a3.is_valid()
        True
        """
        
        if value is None:
            value=getattr(self,"value",None)
        try:
            if np.isnan(value): return False
        except:
            pass
        return value not in self.invalid_values

    def __str__(self):
        """
        >>> a=DBAtom(3)
        >>> print str(a) #or just >>> print a
        3
        """
        return str(getattr(self,"value",None))

    def _get_condition(self,value=None,key=None,approximacy=0.00001):
        """
        >>> a0=DBAtom()
        >>> print a0._get_condition()
        (dbatom==None)

        >>> a1=DBAtom(3)
        >>> print a1._get_condition()
        (dbatom==3)
        >>> print a1._get_condition(5)
        (dbatom==5)
        >>> print a1._get_condition(value=5,key="notdbatom")
        (notdbatom==5)

        Allows value or key to be assigned, to aid use by e.g. Shortcut.__getitem__()
        NB Strings must be queried 

        NB There are also issues around float precision: e.g. if you create a float atom
        with the value 0.234, this could become 0.233999997377 in the database.
        Then when you query for "value==0.234" you don't get a hit.
        As a hack for this, DBAtoms with coltype=Float32Col return a range

        >>> print DBFloat32(6.78)._get_match_condition_unit()
        (dbfloat32>=6.77999020981) & (dbfloat32<=6.78001020981)

        https://pytables.github.io/usersguide/condition_syntax.html
        """
        if key is None:
            key=self.__class__.__name__.lower()
        if value is None:
            value=self.value
        if type(self.coltype)==tbs.StringCol:
            return '({}==b"{}")'.format(key,value)
        elif type(self.coltype) in [tbs.Float32Col,tbs.Float64Col]:
            return '({}>={}) & ({}<={})'.format(key,
                                                value-approximacy,
                                                key,
                                                value+approximacy)
        else:
            return "({}=={})".format(key,value)

    def _get_match_condition_unit(self):
        """
        This is the database condition that should return records with this DBAtom.
        Requires the atom to count as is_valid(),
        so 
        >>> a0=DBAtom()
        >>> print a0._get_match_condition_unit()
        None

        >>> a=DBAtom(3)
        >>> print a._get_match_condition_unit()
        (dbatom==3)
        """
        if self.is_valid():
            return self._get_condition()
        return None

    def _get_txt_header_unit(self,*args,**kwargs):
        """
        >>> a=DBAtom(3)
        >>> print a._get_txt_header_unit()
        dbatom
        """
        return self.__class__.__name__.lower()

    def _get_txt_row_unit(self,*args,**kwargs):
        """
        >>> a=DBAtom(3)
        >>> print a._get_txt_row_unit()
        3
        """
        if self.is_valid():
            return self.value
        return "-"

    def _get_display_header_unit(self,*args,**kwargs):
        """
        >>> a=DBAtom(3)
        >>> print a._get_display_header_unit()
        dbatom
        """
        defaultheader=self._get_txt_header_unit()
        colclip=getattr(self,"colclip",kwargs.get("colclip",20))
        if colclip<len(defaultheader):
            defaultheader=getattr(self,"shortheader",defaultheader)
        return defaultheader

    def _get_display_row_unit(self):
        """
        >>> a=DBAtom(3)
        >>> print a._get_display_row_unit()
        3
        """
        if self.is_valid():
            if hasattr(self,"pretty"):
                return self.pretty.format(self.value)
            else:
                return str(self.value)
        else:
            return "-"

    def _get_summary_row_unit(self):
        return self._get_display_row_unit()

    def get_record(self):
        if not hasattr(self,"record"):
            if not hasattr(self,"passerrorsto"):
                return False
            else:
                self.record=self.passerrorsto
        return self.record

    def calculate(self):
        return self.value

    def check_for_altered(self):
        if hasattr(self,"altered_value"):
            return self.altered_value
        return None

    def set_value_from_altered(self):
        if hasattr(self,"altered_value"):
            self.set_value(self.altered_value)
            delattr(self,"altered_value")
            return self.value
        else:
            return None

#
class DBBool(DBAtom):
    coltype=tbs.BoolCol()
    nullvalue=False

    def __nonzero__(self):
        if self.value:
            return True
        return False

class DBLetter(DBAtom):
    nullvalue=""
    coltype=tbs.StringCol(1)

class DBString(DBAtom):
    nullvalue=""
    coltype=tbs.StringCol(1024)

class DBShortString(DBString):
    coltype=tbs.StringCol(16)

class DBuInt8(DBAtom):
    """
    >>> a=DBuInt8(255)
    >>> print a.value
    255
    >>> print a._get_match_condition_unit()
    (dbuint8==255)
    """
    coltype=tbs.UInt8Col()
    nullvalue=0
    
class DBuInt16(DBAtom):
    """
    >>> a=DBuInt16(65535)
    >>> print a.value
    65535
    >>> print a._get_match_condition_unit()
    (dbuint16==65535)
    """
    coltype=tbs.UInt16Col()
    nullvalue=0

class DBuInt32(DBAtom):
    """
    >>> a=DBuInt32(4294967295)
    >>> print a.value
    4294967295
    >>> print a._get_match_condition_unit()
    (dbuint32==4294967295)
    """
    coltype=tbs.UInt32Col()
    nullvalue=0

class DBuInt64(DBAtom):
    """
    >>> a=DBuInt64(18446744073709551615)
    >>> print a.value
    18446744073709551615
    >>> print a._get_match_condition_unit()
    (dbuint64==18446744073709551615)
    """
    coltype=tbs.UInt64Col()
    nullvalue=0

class DBFloat32(DBAtom):
    """
    >>> a=DBFloat32(3.4028235e+38)
    >>> print a.value
    3.40282e+38
    >>> print a._get_match_condition_unit()
    (dbfloat32>=3.40282346639e+38) & (dbfloat32<=3.40282346639e+38)
    """
    coltype=tbs.Float32Col()
    nullvalue=np.nan
    strict=False

class DBFloat64(DBAtom):
    """
    >>> a=DBFloat64(1.79769313486e+308)
    >>> print a.value
    1.79769313486e+308
    >>> print a._get_match_condition_unit()
    (dbfloat64>=1.79769313486e+308) & (dbfloat64<=1.79769313486e+308)
    """
    coltype=tbs.Float64Col()
    nullvalue=np.nan
    strict=False

class DBDateTime(DBuInt32):
    """
    a floating point number representing number of seconds since the epoch
    """
    invalid_values=[None,"-","",np.nan,float('nan'),0,0.0]
    nullvalue=0
    def _get_summary_row_unit(self):
        if self.is_valid():
            return time.ctime(self.value) #time.ctime
        return "-"   

class DBNestedAtom(DBAtom):
    """
    http://pytables.org/svn/pytables/tags/std-2.2rc2/doc/text/nestedrecords.txt
    Intended to allow and simplify the inclusion of nested records (e.g. timecourse measurements)
    in DBRecords.

    >>> n0=DBNestedAtom()
    >>> print n0
    -

    >>> n1=DBNestedAtom([(1,2),(3,4),(5,6)])
    >>> print n1
    ( 1.0000, 2.0000) ( 3.0000, 4.0000) ( 5.0000, 6.0000)

    >>> print n0.is_valid()
    False

    >>> print n1.is_valid()
    True

    >>> print n1._get_match_condition_unit()
    None

    >>> print n1.value
    [[  1.   2.]
     [  3.   4.]
     [  5.   6.]
     ..., 
     [ nan  nan]
     [ nan  nan]
     [ nan  nan]]

    >>> print n1._get_trimmed()
    [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]

    >>> print n1._get_display_row_unit()
    ( 1.0000, 2.0000) ( 3.0000, 4.0000) ( 5.0000, 6.0000)

    >>> print n1._get_txt_row_unit()[:30]
    ;1.0,2.0;3.0,4.0;5.0,6.0;;;;;;


    >>> print n1[0]
    [ 1.  2.]

    >>> print n1[3.0]
    4.0

    """
    #coltypes=['(2,)Float32']
    #subnames=['timepoint', 'reading']
    length=576
    shape=(length,2)
    nullvalue=[(np.nan,np.nan)]
    coltype=tbs.Float32Col(shape=shape,dflt=nullvalue)

    def __init__(self,valuearray=None,record=None,dbasenameroot=None):
        """
        >>> n0=DBNestedAtom()
        >>> print n0
        -
        >>> n1=DBNestedAtom([(1,2),(3,4),(5,6)])
        >>> print n1
        ( 1.0000, 2.0000) ( 3.0000, 4.0000) ( 5.0000, 6.0000)
        """
        if record is not None:
            self.record=self.passerrorsto=record
        if dbasenameroot is not None:
            self.dbasenameroot=dbasenameroot
        if valuearray is not None:
            self.set_value(valuearray)
        else:
            self.value=None

    def set_value(self,valuearray=None):
        """
        >>> n0=DBNestedAtom()
        >>> print n0.set_value([(1,2),(3,4),(5,6)])
        True
        >>> print n0
        ( 1.0000, 2.0000) ( 3.0000, 4.0000) ( 5.0000, 6.0000)
        >>> print n0.set_value([])
        False
        >>> print n0
        -
        """
        if not self.is_valid(valuearray):
            self.value=None
            return False            
        elif type(valuearray)==str:
            valuearray=[pair.split(",") for pair in valuearray.split(";")]

        self.value=np.empty(self.shape)
        self.value[:]=np.NaN
        self.value[:len(valuearray)]=valuearray
        return True

    def is_valid(self,value=None):
        """
        >>> n1=DBNestedAtom([(1,2),(3,4),(5,6)])
        >>> print n1.is_valid()
        True
        """
        if value is None:
            value=getattr(self,"value",None)

        if value==[]:
            return False
        if type(value)==np.ndarray:
            if self._get_trimmed(value)==[]:
                return False
            else:
                return True
        if value in self.invalid_values:
            return False
        return True

    def _get_match_condition_unit(self):
        """
        PyTable limitation: multidimensional columns not yet supported in conditions,
        so by returning None, this Atom is excluded from whole record match_conditions

        >>> n1=DBNestedAtom([(1,2),(3,4),(5,6)])
        >>> print n1._get_match_condition_unit()
        None
        """
        return None

    def _get_trimmed(self,value=None):
        """
        returns only those rows that don't contain pure NaN
        """
        if not hasattr(self,"trimmed"):
            if value is None:
                value=self.value
            if value is None:
                return []
            self.trimmed=[(a,b) for a,b in value if not np.isnan(a) and not np.isnan(b)]
        return self.trimmed

    def _get_emptycellspacer(self,spacer=";"):
        if spacer=="\t":
            spacer=[""]
        emptycellcount=self.length-len(self._get_trimmed())
        return spacer*emptycellcount

    def _get_display_row_unit(self):
        """
        returns the array as zero-padded space-separated bracketed pairs that are visually easy
        to read. Fails if self.value==None.

        >>> n1=DBNestedAtom([(1,2),(3,4),(5,6)])
        >>> print n1._get_display_row_unit()
        ( 1.0000, 2.0000) ( 3.0000, 4.0000) ( 5.0000, 6.0000)
        """
        return " ".join(["({:>7.4f},{:>7.4f})"
                         .format(x,y) for x,y in self._get_trimmed()])

    def _get_display_header_unit(self,**kwargs):
        defaultheader=self.__class__.__name__.lower()
        colclip=getattr(self,"colclip",kwargs.get("colclip",20))
        if colclip<len(defaultheader):
            defaultheader=getattr(self,"shortheader",defaultheader)
        return defaultheader

    def _get_summary_row_unit(self):
        if self.is_valid():
            all=self._get_trimmed()
            firstpair,lastpair=all[0],all[-1]
            return "({:>7.4f},{:>7.4f})...({:>7.4f},{:>7.4f})".format(firstpair[0],
                                                                      firstpair[1],
                                                                      lastpair[0],
                                                                      lastpair[1])
        else:
            return "-"

    def _get_txt_header_unit(self,spacer=";",pad=True,timepoints=None):
        """
        >>> DBNestedAtom.length=4
        >>> a=DBNestedAtom([(0,1),(1,2)])
        >>> print a._get_txt_header_unit()
        dbnestedatom;,;,;;
        >>> DBNestedAtom.length=576
        """
        if timepoints is None:
            rec=self.get_record()
            try:
                timepoints=rec.timevalues()
            except:
                pass

        if self.is_valid():
            trimmed=self._get_trimmed()
            if timepoints is True:
                pairs=[str(y) for y,x in trimmed]
            elif type(timepoints)==list:
                pairs=[str(y) for y,x in timepoints]
            else:
                pairs=[",".format(y,x) for y,x in trimmed]
            out=spacer.join(pairs)
            if pad:
                return self.__class__.__name__.lower()+spacer+out+self._get_emptycellspacer()
            else:
                return self.__class__.__name__.lower()+spacer+out
        return "-"

    def _get_txt_row_unit(self,spacer="\t",pad=True,timepoints=None,index=None):
        """
        returns the array as semicolon-separated comma-separated pairs,
        e.g. 0,3;1,4;2,5;;;;;;;;;;;;;;
        This is versatile way of doing it, because you can import such
        a file into Excel in different ways by picking different delimiters.

        >>> n1=DBNestedAtom([(1,2),(3,4),(5,6)])
        >>> print n1._get_txt_row_unit()[:30]
        ;1.0,2.0;3.0,4.0;5.0,6.0;;;;;;
        """
        if self.is_valid():
            trimmed=self._get_trimmed()
            if timepoints is None:
                if index:
                    pairs=[str(pair[index])
                           for pair in trimmed]
                else:
                    pairs=["{},{}".format(y,x)
                           for y,x in trimmed]
            else:
                trimmeddict=dict(trimmed)
                if index==0:
                    pairs=[str(y)
                           if y in trimmed
                           else "" for y in timepoints]
                elif index==1:
                    pairs=[str(trimmed[y])
                           if y in trimmed
                           else "" for y in timepoints]
                else:
                    pairs=["{},{}"
                           .format(y,trimmed[y])
                           if y in trimmed
                           else "" for y in timepoints]
            out=";".join(pairs)
            if pad:
                return ";"+out+self._get_emptycellspacer()
            else:
                return ";"+out
        return "-"
#
    def __getitem__(self,query):
        """
        >>> n1=DBNestedAtom([(1,2),(3,4),(5,6)])
        >>> print n1[0]
        [ 1.  2.]
        >>> print n1[3.0]
        4.0
        """
        if self.value is None:
            LOG.error("{}: __getitem__ asked to get data but value=None"
                      .format(self.__class__.__name__))
            return None
        if type(query)==int:
            LOG.info("{}: __getitem__ getting data by index {} (an int)"
                     .format(self.__class__.__name__,query))
            return self.value[query]
        elif type(query)==float:
            rounder="{:.3f}"
            vd=dict([(rounder.format(y),x) for y,x in self.value])
            #Rather than just dict(self.value), this allows more approximate matching
            fquery=rounder.format(query)
            if fquery in vd:
                LOG.info("{}: __getitem__ getting data by timepoint {} (a float)"
                         .format(self.__class__.__name__,query))
                return vd[fquery]
            else:
                LOG.error("{}: __getitem__ asked to get data by timepoint"
                          " {} but this timepoint isn't available. "
                          "May implement retrieval from smoothed curve "
                          "in future."
                          .format(self.__class__.__name__,query))
                #May need to implement approximate matching of floats as well, by 
                return None

    def __str__(self):
        """
        >>> n0=DBNestedAtom()
        >>> n1=DBNestedAtom([(1,2),(3,4),(5,6)])
        >>> print str(n0)
        -
        >>> print n1
        ( 1.0000, 2.0000) ( 3.0000, 4.0000) ( 5.0000, 6.0000)
        """
        if self.is_valid():
            return self._get_display_row_unit()
        return "-"

    def __len__(self):
        return len(self._get_trimmed())

class DBSeries(DBNestedAtom):
    length=320
    shape=(length)
    nullvalue=np.NaN
    coltype=tbs.Float32Col(shape=shape,dflt=nullvalue)

    def set_value(self,valuearray=None):
        """
        >>> n0=DBSeries()
        >>> print n0.set_value([1,2,3,4,5,6])
        True
        >>> print n0
         1.0000,  2.0000,  3.0000,  4.0000,  5.0000,  6.0000
        >>> print n0.set_value([])
        True
        >>> print n0
        -
        """
        if valuearray is None and self.value is None:
            return False
        elif valuearray is None:
            valuearray=[]
        if type(valuearray)==str:
            valuearray=[float(v) for v in valuearray.split(",")]
        elif isinstance(valuearray,DBSeries):
            valuearray=self.value
        empty=np.array([np.NaN]*self.length)#[np.NaN]*(self.length-len(valuearray))
        empty[:len(valuearray)]=np.array(valuearray)
        self.value=empty
        return True

    def _get_trimmed(self,value=None):
        """
        returns only those rows that don't contain pure NaN
        """
        if value is None: value=self.value
        if value is None: return []
        return [v for v in self.value if not np.isnan(v)]

    def _get_display_row_unit(self):
        """
        returns the array as zero-padded space-separated bracketed pairs that are visually easy
        to read. Fails if self.value==None.

        >>> n1=DBSeries([1,2,3,4,5,6])
        >>> print n1._get_display_row_unit()
         1.0000,  2.0000,  3.0000,  4.0000,  5.0000,  6.0000
        """
        return ", ".join(["{:>7.4f}".format(x)
                          for x in self._get_trimmed()])

    def _get_summary_row_unit(self):
        if self.is_valid():
            all=self._get_trimmed()
            if len(all)>4:
                return "{:>7.4f},{:>7.4f}...{:>7.4f},{:>7.4f}".format(all[0],
                                                                      all[1],
                                                                      all[-2],
                                                                      all[-1])
            else:
                return ",".join(["{:>7.4f}".format(a) for a in all])
        else:
            return "-"

    def _get_txt_header_unit(self,spacer=";",timepoints=None,trim=True):
        """
        spacer: the character used to separate values
        timepoints: if specified, then header includes timepoint values between spacers
        trim: if True, returns only trimmed header
              if false, leaves gaps for nan values padding the header out to DBSeries.length
        
        >>> DBSeries.length=4
        >>> a=DBSeries([0,1,1,2])
        >>> print a._get_txt_header_unit()
        dbseries;;;;
        >>> DBSeries.length=320
        """
        if timepoints is None:
            rec=self.get_record()
            try:
                timepoints=rec.timevalues()
            except:
                pass

        originalspacer=spacer
        if self.is_valid():
            trimmed=self._get_trimmed()
            if timepoints:
                assert len(trimmed)==len(timepoints)
                vals=["{:.4f}".format(t) for t in timepoints]
            else:
                vals=["" for x in trimmed]
            if spacer=="\t":
                first=[self.__class__.__name__.lower()]
                spacer=[]
                out=vals
            else:
                first=self.__class__.__name__.lower()
                out=spacer.join(vals)
            if trim:
                return first+spacer+out
            else:
                return first+","+out+self._get_emptycellspacer(spacer=originalspacer)
        return "-"

    def _get_txt_row_unit(self,spacer=";",trim=True):
        """
        returns the array as <spacer>-separated values,
        e.g. ;0;1;2;3;4;5;6;;;;;;;;;;;;;;;
        
        spacer: the character used to separate values
        trim: if True, returns only trimmed header
              if False, leaves gaps for nan values padding the header out to DBSeries.length

        if pad=True then spacer added at front and end
        to align with padded txt_header_unit

        >>> n1=DBSeries([1,2,3,4,5,6])
        >>> print n1._get_txt_row_unit()[:30]
        ;1.0000;2.0000;3.0000;4.0000;5
        """
        originalspacer=spacer
        if self.is_valid():
            vals=["{:.4f}".format(x) for x in self._get_trimmed()]
            if spacer=="\t":
                out=vals
                spacer=[""]
            else:
                out=spacer.join(vals)
            if trim:
                return spacer+out
            else:
                return spacer+out+self._get_emptycellspacer(spacer=originalspacer)
        return "-"
#
    def __getitem__(self,query):
        """
        >>> n1=DBSeries([1,2,3,4,5,6])
        >>> print n1[0]
        1.0
        >>> print n1[3.00001]
        3.0
        """
        if self.value is None:
            LOG.error("{}: __getitem__ asked to get data but value=None"
                      .format(self.__class__.__name__))
            return None
        if type(query)==int:
            LOG.info("{}: __getitem__ getting data by index {} (an int)"
                     .format(self.__class__.__name__,query))
            return self.value[query]
        elif type(query)==float:
            closest_index=min(range(len(self.value)), key=lambda i: abs(self.value[i]-query))
            LOG.info("{}: __getitem__ getting closest float to query {}"
                     .format(self.__class__.__name__,query))
            return self.value[closest_index]

    def __iter__(self):
        for v in self.value:
            yield v

    def intersection_indices(self,otherseries,rounder="{:.4f}"):
        """
        returns the indices of 
        """
        if type(otherseries)==list:
            otherlist=otherseries
        else:
            otherlist=otherseries._get_trimmed()
        otherrounded=[rounder.format(v) for v in otherlist]
        
        selfindices=[i for i,tp in enumerate(self._get_trimmed()) if rounder.format(tp) in otherrounded]
        return selfindices

    def intersection(self,otherseries=None,indices=None,rounder="{:.4f}",as_dbseries=False):
        """
        """
        if indices is None:
            indices=self.intersection_indices(otherseries=otherseries,
                                              rounder=rounder)
        values=[self.value[i] for i in indices]
        if as_dbseries:
            return self.__class__(values)
        else:
            return values

#
class DBRecord(DBAtom):
    """

    ALL DBRECORDS CAN ACT AS DBATOMS
    
    A DBRecord subclass has a set of values defined by the slots class variable,
    which is a list of DBAtom subclasses, e.g.
        #class Substance(DBRecord):
            #slots=[Name,Cost,CostRatio,Volume,ConcentrationMolar,CASnumber]
    You can create such a record from a dictionary of kwargs,
    or a list of array of values in the correct order,
    or simply instantiate an empty record to populate later
    DBTable subclasses will return suitable DBRecord subclasses from queries etc
    or can insert new rows passed to them as suitable DBRecord subclasses.
    The idea here is to create a really natural set of classes that users
    can easily understand and manipulate, but which can effortlessly store themselves
    in databases, csv files etc in ways that the user doesn't have to worry about.


    Different ways a DBRecord might be created:

    1) As a temporary incomplete item for querying a related DBTable:
    __init__
    2) As a record retrieved from a DBTable in response to a query
    DBTable._query_generator() >>> __init__
    3) As a new set of info read in from a file (may require some fields to be calculated)
    __init__ ++++ calculate_all()
    4) As an incomplete record which can be triggered to complete itself by reading in a file
    __init__ ++++ read()
    5) As a component of another record, retrieved from the default value
    (and autocompleted from any in_memory_dictionary if possible?)
    __init__ ++++ complete_from_memory()

    >>> r0=DBRecord()
    >>> r1=DBRecord(3,4,5)
    >>> r2=DBRecord(DBAtom(3),DBuInt8(4),DBFloat32(5))
    >>> r3=DBRecord(dbatom=3,dbuint8=4,dbfloat32=5)

    >>> if r1 not in DBTable():
    ...     f=r1.store(check=True)

    >>> print str(r3) #or just print r3
    DBRecord(3, 4, 5.0)

    >>> r4=DBRecord(1,2,None)
    >>> print r4
    DBRecord(1, 2, -)
    >>> r4.store()
    True
    >>> print r4
    DBRecord(1, 2, -)
    >>> print [atm.is_valid() for nam,atm in r4.atoms]
    [True, True, False]
    >>> r5=DBTable().get(dbatom=1)
    >>> print r5
    DBRecord(1, 2, -)
    >>> print [atm.is_valid() for nam,atm in r5.atoms]
    [True, True, False]
    >>> r4.delete()
    True
    """
    nullvalue=""
    dbpath="DBrecords.db"
    tableclassstring="DBTable"
    slots=[DBAtom,DBuInt8,DBFloat32]
    defaultlookup="DBAtom"

    def __init__(self,*args,**kwargs):
        """
        >>> r0=DBRecord()
        >>> r1=DBRecord(3,4,5)
        >>> r2=DBRecord(DBAtom(3),DBuInt8(4),DBFloat32(5))
        >>> r3=DBRecord(dbatom=3,dbuint8=4,dbfloat32=5)
        """
        
        calculate_all        = kwargs.pop("calculate_all",False)
        read                 = kwargs.pop("read",False)
        complete             = kwargs.pop("complete",False)
        complete_from_memory = kwargs.pop("complete_from_memory",False)
        self.record          = kwargs.pop("record",self)
        self.dbasenameroot   = kwargs.pop("dbasenameroot",None)

        tableclass=globals()[self.__class__.tableclassstring]
        if getattr(tableclass,"_dbasenameroot",None):
            self.dbasenameroot=tableclass._dbasenameroot
        elif not self.dbasenameroot:
            CURRENTLOC=Locations().get_userpath()
            self.dbasenameroot=os.path.basename(CURRENTLOC)

        self.atoms=[]
        for scls in self.slots:
            self.atoms.append([scls.__name__.lower(),
                               scls(record=self.record,
                                    dbasenameroot=self.dbasenameroot)])
        self.value=None
        
        if args:
            if len(args)==1:
                v=self._set_default_atom(args[0])
            else:
                for k,v in zip([n for n,scls in self.atoms],args):
                    self.set_atom(k,v)
        if kwargs:
            for k,v in kwargs.items():
                self.set_atom(k,v)
        #
        if complete:
            tried=self.complete_from_memory()
            if not tried:
                self.complete()
        elif complete_from_memory:
            self.complete_from_memory()
        if calculate_all:
            self.calculate_all()
        if read:
            self.read()

    def is_stored(self):
        return self in self._get_table()

    def set_atom(self,name,value):
        """
        Value can be a value, or a whole DBAtom subclass
        """
        atomnames,atomclasses=zip(*self.atoms)
        #try:
        for a in "a":
            i=atomnames.index(name)
        #except Exception as e:
        #    LOG.error("{} can't find atom {} to set it to {}({}) "
        #              "because {} {}"
        #              .format(self.__class__.__name__,
        #                      name,type(value),value,
        #                      e,get_traceback()))
        #    return None
        if type(atomclasses[i])==type(value):
            self.atoms[i][1]=value
        else:
            self.atoms[i][1].set_value(value)
        if name==self.defaultlookup.lower():
            self.value=value
        return self.atoms[i][1].value

    def _set_default_atom(self,value):
        self.set_atom(self.defaultlookup.lower(),value)

    def __str__(self):
        """
        >>> r1=DBRecord(3,4,5)
        >>> print str(r1)
        DBRecord(3, 4, 5.0)
        """
        return "{}({})".format(self.__class__.__name__,
                               ", ".join([a._get_summary_row_unit()
                                          for n,a in self.atoms]))

    def scrutinize(self,printit=True):
        output=["{} ({})".format(self.value,self.dbasenameroot)+"_"*30]
        output+=["{}\t{}".format(an.ljust(22),str(av))
                 for an,av in self.atoms]
        outputstring=os.linesep.join(output)
        if printit:
            print outputstring
        else:
            return outputstring

    def __eq__(self,other):
        """
        >>> r1=DBRecord(3,4,5)
        >>> r2=DBRecord(dbatom=3,dbuint8=4,dbfloat32=5)
        >>> print r1==r2
        True
        """
        if other in [None,[],""]:
            return False
        return self._get_match_condition()==other._get_match_condition()

    def __hash__(self):
        return hash(self._get_match_condition())

    def __getitem__(self,query,report=False):
        """
        >>> r1=DBRecord(3,4,5)
        >>> print r1["dbatom"]
        3
        >>> print r1[1]
        4
        >>> print r1[DBFloat32()]
        5.0
        >>> print r1[DBFloat32]
        5.0
        """
        output=None
        if isinstance(query,type):
            query=query()
        if type(query)==int:
            output=self.atoms[query][1]
            if hasattr(output,"complete_from_memory"):
                output.complete_from_memory()
            return output
        if issubclass(query.__class__,DBAtom):
            query=query.__class__.__name__.lower()
        if type(query)==str:
            query=query.lower()
            if query in self.__dict__:
                return self.__dict__[query]
            elif query in dir(self):
                return getattr(self,query)()
            else:
                dh=self._get_deep_headers()
                if query in dh:
                    return self._follow_atompath(dh[query])
                else:
                    if report:
                        LOG.debug("unknown record atom {}. Try {}"
                                  .format(query,dh.keys()))

    def __setitem__(self,key,value):
        """
        """
        return self.set_atom(key,value)

    def keys(self):
        """
        """
        return zip(*self.atoms)[0]
    headers=keys

    def keys_extended(self):
        basickeys=list(self.keys())
        methodkeys=[k for k in self.__dict__.keys() if k[0]!="_"]
        deepkeys=flatten([atm.keys_extended()
                          for nm,atm in self.atoms
                          if hasattr(atm,"keys_extended")])
        for xk in deepkeys+methodkeys:
            if xk not in basickeys:
                basickeys.append(xk)
        return tuple(basickeys)

    def _get_deep_headers(self):
        """
        Returns dict of all atoms and atoms of atoms etc along with their atompaths
        """
        scn=self.__class__.__name__.lower()
        if not hasattr(self,"deep_headers"):
            self.deep_headers={}
            add_now=[]
            add_later=[]
            for name,atom in self.atoms:
                if hasattr(atom,"_get_deep_headers"):
                    add_later.append((name,atom))
                else:
                    add_now.append((name,atom))
            for name,atom in add_now:
                if name not in self.deep_headers:
                    self.deep_headers[name]="{}.{}".format(scn,name)
            for name,atom in add_later:
                if name not in self.deep_headers:
                    self.deep_headers[name]="{}.{}".format(scn,name)
                dh=atom._get_deep_headers()
                if type(dh)==dict:
                    for k,h in dh.items():
                        if k not in self.deep_headers:
                            self.deep_headers[k]="{}.{}".format(scn,h)
        return self.deep_headers

    def _follow_atompath(self,atompath):
        """
        
        """
        frags=atompath.split(".")
        assert frags[0]==self.__class__.__name__.lower()
        atompath=frags[1:]
        next_level=self._get_dictionary()[atompath[0]]
        if hasattr(next_level,"complete_from_memory"):
            next_level.complete_from_memory()
        if len(atompath)==1:
            return next_level
        else:
            return next_level._follow_atompath(".".join(atompath))  

    def copy_atoms_from(self,temp):
        self.atoms=temp.atoms[:]
        for name,atm in self.atoms:
            atm.record=atm.passerrorsto=self
        temp.dbasenameroot=self.dbasenameroot
        if hasattr(temp,"fails"): self.fails=temp.fails
        if hasattr(temp,"warnings"): self.warnings=temp.warnings
        if hasattr(temp,"aoks"): self.aoks=temp.aoks
        return self

    def copy_in_other_folder(self,targetdbasenameroot):
        cop=self.__class__()
        cop.dbasenameroot=targetdbasenameroot
        cop.atoms=[]
        for name,atm in self.atoms:
            copatm=atm.__class__(atm.value,
                                 record=cop,
                                 dbasenameroot=targetdbasenameroot)
            cop.atoms.append([name,copatm])
        if hasattr(self,"fails"): cop.fails=self.fails
        if hasattr(self,"warnings"): cop.warnings=self.warnings
        if hasattr(self,"aoks"): cop.aoks=self.aoks
        return cop

    def complete(self):
        """
        searches database for, and returns, a complete version of an incomplete DBRecord
        """
        temp=self._get_table().get(self._get_match_condition(),warn=False)
        if temp is None:
            return False
        self.copy_atoms_from(temp)
        return self

    def complete_from_memory(self):
        """
        
        """
        tab=self._get_table()
        if hasattr(tab,"in_memory_dictionary"):
            d=tab.in_memory_dictionary()
            if self.value in d:
                output=d[self.value]
                self.copy_atoms_from(output)
                return True
        return False

    def calculate_all(self,butnot=[]):
        """
        #>>> print
        
        """
        new=None
        for name,atm in self.atoms:
            if hasattr(atm,"calculate"):
                if name.lower() not in butnot:
                    new=atm.calculate()

    def _get_dictionary(self):
        """
        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_dictionary().keys()
        ['dbuint8', 'dbfloat32', 'dbatom']
        """
        return dict(self.atoms)

    def _get_delimited(self,delimiter="\t",pretty=False):
        """
        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_delimited(">")
        3>4>5.0
        """
        if pretty:
            return delimiter.join([atm._get_pretty() for name,atm in self.atoms])
        else:
            return delimiter.join([str(atm) for name,atm in self.atoms])

    @classmethod
    def _get_description(cls):
        """
        returns a dictionary of atoms, with names & positions deduced from self.slots
        This can be fed to a PyTable table constructor.

        >>> print DBRecord._get_description() #classmethod
        {'dbuint8': UInt8Col(shape=(), dflt=0, pos=1), 'dbfloat32': Float32Col(shape=(), dflt=0.0, pos=2), 'dbatom': UInt8Col(shape=(), dflt=0, pos=0)}
        """
        outputdict={}
        for i,scls in enumerate(cls.slots):
            newcolclass=copy.copy(scls.coltype)
            newcolclass._v_pos=i
            outputdict[scls.__name__.lower()]=newcolclass
        return outputdict

    def _get_match_condition(self):
        """
        Creates an &-joined PyTables query string that matches the object exactly in all atoms
        that return a valid _get_match_condition(),e.g.
        
        >>> r1=DBRecord(3,4,5.0)
        >>> print r1._get_match_condition()
        (dbatom==3) & (dbuint8==4) & (dbfloat32>=4.99999) & (dbfloat32<=5.00001)
        """
        output=[]
        for name,atm in self.atoms:
            match_condition=atm._get_match_condition_unit()
            if match_condition:
                output.append(match_condition)
        return " & ".join(output)

    def _get_default_match_condition(self,query):
        """
        Used by DBTable._query_default_condition(), used when trying e.g. DBtable.get(3)
        
        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_default_match_condition(3) #This condition would return r1 if stored
        (dbatom==3)
        >>> print r1._get_default_match_condition(4) #This condition would return None
        (dbatom==4)
        """
        return self._get_dictionary()[self.defaultlookup.lower()]._get_condition(value=query)

    def _get_query_from_kwargs(self,**kwargs):
        """
        kwargs consist of name:value pairs, but name or value could be a DBAtom
        
        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_query_from_kwargs(dbuint8=4)
        (dbuint8==4)
        
        #>>> print r1._get_query_from_kwargs(DBuInt8()=4)
        #(dbuint8==4)
        """
        output=[]
        dictionary=self._get_dictionary()
        for key,value in kwargs.items():
            if issubclass(key.__class__,DBAtom):
                key=key.__class__.__name__.lower()
            if issubclass(value.__class__,DBAtom):
                value=value.value            
            match_condition=dictionary[key]._get_condition(value=value)
            if match_condition:
                output.append(match_condition)
        return " & ".join(output)

    def _get_table(self):
        """
        Have to create a new instance each time or you get conflict problems.

        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_table().__class__.__name__
        DBTable
        """
        tableclass=globals()[self.__class__.tableclassstring]
        return tableclass(self.dbasenameroot)
#
    def _get_display_headers(self):
        """
        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_display_headers()
        ['dbatom', 'dbuint8', 'dbfloat32']
        """
        return [atm._get_display_header_unit() for name,atm in self.atoms]

    def _get_display_row(self):
        """
        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_display_row()
        ['3', '4', '5.0']
        """
        return [atm._get_display_row_unit() for name,atm in self.atoms]

    def _get_summary_row(self):
        return [atm._get_summary_row_unit() for name,atm in self.atoms]

    def _get_txt_headers(self,*args,**kwargs):
        """
        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_txt_headers()
        ['dbatom', 'dbuint8', 'dbfloat32']
        """
        output=[]
        for name,atm in self.atoms:
            header_unit=atm._get_txt_header_unit(*args,**kwargs)
            if type(header_unit)==list:
                output+=header_unit
            else:
                output.append(header_unit)
        return output

    def _get_txt_row(self,*args,**kwargs):
        """
        >>> r1=DBRecord(3,4,5)
        >>> print r1._get_txt_row()
        [3, 4, 5.0]
        """
        output=[]
        for name,atm in self.atoms:
            row_unit=atm._get_txt_row_unit(*args,**kwargs)
            if type(row_unit)==list:
                output+=row_unit
            else:
                output.append(row_unit)
        return output
#
    def store(self,check=True):
        """
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
        ____________________________
        Displayed 1/1 DBTable(Software Test)

        >>> r1=DBRecord(9,8,7)
        >>> r1.store(check=True)
        True

        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           9        8        7.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> r1.delete()
        True
        """
        dbt=self._get_table()
        if dbt.store_record_object(self,check=check):
            LOG.info("stored {} in table {}".format(self,
                                                    dbt.__class__.__name__))
            return True
        return False

    def delete(self,autodeletesubrecords=True,
               subsidiaryrecords=[],report=True):
        """
        >>> r1=DBRecord(9,8,7)
        >>> r1.store(check=True)
        True

        >>> print DBTable("Software Test")
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           9        8        7.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> r1.delete()
        True
        >>> print DBTable("Software Test")
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
        ____________________________
        Displayed 1/1 DBTable(Software Test)

        """
        if hasattr(self,"_delete_also"):
            self._delete_also()
        dbt=self._get_table()
        if hasattr(dbt,"in_memory_dict"):
            if self.value in dbt.in_memory_dict:
                del dbt.in_memory_dict[self.value]
        l=list(dbt._query_index_generator(self._get_match_condition()))
        if not l:
            LOG.warning("{} not found in {} so can't delete"
                        .format(self.__str__(),
                                dbt.__class__.__name__))
            return False
        if len(dbt)==1:
            dbt.clear()
        else:
            #dbt.switch_to("a")
            for index in l[::-1]:
                dbt.table.remove_row(index)
                if report:
                    LOG.info("{} ({}) has deleted itself from "
                             "index {} of {} ({})"
                             .format(self.__str__(),
                                     self.dbasenameroot,
                                     index,
                                     dbt.__class__.__name__,
                                     dbt.dbasenameroot))
        if autodeletesubrecords:
            if hasattr(self,"yield_records"):
                if not subsidiaryrecords:
                    subsidiaryrecords=self.yield_records()
                    if subsidiaryrecords is None:
                        subsidiaryrecords=[]
        if subsidiaryrecords:
            for subrec in subsidiaryrecords:
                subrec.delete(autodeletesubrecords=False,report=False)

        return True

    def count(self):
        return self._get_table().count(self)

    def get(self):
        return self._get_table().get(self)
#
    @classmethod
    def _from_txt_row(cls,rowlist):
        """
        >>> print DBRecord._from_txt_row(['3', '4', '5.0']) #@classmethod
        DBRecord(3, 4, 5.0)
        """
        ob=cls(*[scls.from_string(s)
                 for scls,s in zip(cls.slots,rowlist)])
        return cls(*[scls.from_string(s)
                     for scls,s in zip(cls.slots,rowlist)])

#Update methods
    def update_atoms(self,*args,**kwargs):
        """
        Updates the DBRecord object in place, AND, if stored, its corresponding database entry

        >>> r1=DBRecord(9,8,7)
        >>> r1.store(check=True)
        True
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           9        8        7.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> print r1.update_atoms(dbuint8=11)
        True

        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           9       11        7.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> r1.update_atoms(DBuInt8(13),DBFloat32(9.0))
        True

        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           9       13        9.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> r1.delete()
        True
        """
        stored=self.is_stored()
        tab=self._get_table()
        if not stored:
            for atm in args:
                k=atm.__class__.__name__.lower()
                self.set_atom(k,atm.value)
            for k,v in kwargs.items():
                if hasattr(v,"value"):
                    v=v.value
                #gets correct atom and calls it to set new value
                self.set_atom(k,v) 
            return True
        else:
            dbt=self._get_table()
            if kwargs.pop("check",True):
                if not self in dbt:
                    LOG.error("{}: update_atoms() failed as {} not in {}"
                              .format(self.__class__.__name__,
                                      self,
                                      dbt.__class__.__name__))
                    return False
            original_match_condition=self._get_match_condition()
            for row in dbt.table.where(original_match_condition):
                for i,atm in enumerate(args):
                    if not hasattr(atm,"value"):
                        atm=self.slots[i](atm)
                    k=atm.__class__.__name__.lower()
                    if atm.is_valid():
                        row[k] = atm.value
                        self.set_atom(k,atm.value)
                    else:
                        row[k] = atm.nullvalue
                        self.set_atom(k,atm.nullvalue)
                for k,v in kwargs.items():
                    if not hasattr(v,"value"):
                        atmdict=self._get_dictionary()
                        assert k.lower() in atmdict
                        v=atmdict[k].__class__(v)
                    if v.value is None:
                        row[k] = v.nullvalue
                    else:
                        row[k] = v.value
                    #gets correct atom and calls it to set new value
                    self.set_atom(k,v.value)
                row.update()
            dbt.table.flush()
            return True

    def update_altered(self):
        """
        >>> r1=DBRecord(1,2,3)
        >>> r1.store(check=True)
        True
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           1        2        3.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> r1["dbatom"].alter_value(8)
        >>> r1["dbfloat32"].alter_value(5.5)
        >>> print r1                 #Not changed...
        DBRecord(1, 2, 3.0)
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           1        2        3.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> r1a=r1.update_altered()      #NOW changed...
        >>> print r1
        DBRecord(8, 2, 5.5)
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           8        2        5.5    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> r1.delete()
        True
        """
        kwargs={}
        for name,atm in self.atoms:
            changed=atm.check_for_altered()
            if changed is not None:
                kwargs[name]=changed
        #print kwargs
        self.update_atoms(**kwargs)
        return self

class DBTable(object):
    """
    Friendly wrapper for PyTables

    >>> dbt=DBTable()
    >>> for row in dbt:
    ...     print row
    DBRecord(3, 4, 5.0)

    >>> print DBTable()
    ____________________________
     dbatom  dbuint8  dbfloat32 
    ----------------------------
       3        4        5.0    
    ____________________________
    Displayed 1/1 DBTable(Software Test)


    #This then automatically closes up the DBTable object (calls __exit__) after
    #the 'with' clause ends. However, __del__ method should also tidy things up.

    You can display the contents of any DBTable subclass very easily, e.g.
    #>>>Substances().display_image()

    You can query DBTable subclasses using dictionary syntax and a DBRecord instance,
    and get back a complete DBRecord if one exists, e.g.
    #>>>dbrecord_example=Substance(Name="MMS",Cost=345.00,CostRatio=3.00,Volume=10.0,ConcentrationMolar=20.0,CASnumber="12-234-456")
    #>>>dbrecord_example.store()
    #>>>dbrecord_query=Substance(name="MMS")
    #>>>dbrecord_complete=Substances()[dbrecord_query]
    or
    #>>>dbrecord_complete=Substances()["(name==b'MMS')"]
    Or you can query the table using the get() method and any flags you like, e.g.
    #>>>Substances().get(name="MMS",cost=345)
    or with PyTables' more versatile string query syntax, e.g.
    #>>>Substances().get("(name==b'MMS') & (cost<400)")
    ...all of which return objects of the appropriate type.
    
    You can also use __contains__ syntax to see if a record is stored in the DBTable, e.g.
    #>>>print dbrecord_temp in Substances()
    or even
    #>>>print "(name==b'MMS')" in Substances()

    and you can perform this check automatically when storing a record, by including the check-True
    flag in the store method, e.g.
    #>>>dbrecord_example2=Substance(name="HU 4",cost=223.00,costRatio=4.00,volume=20.0,concentrationmolar=10.0,casnumber="34-456-678")
    #>>>dbrecord_example2.store(check=True)
    #>>>dbrecord_example.store(check=True)
    """
    _shared_state={}
    tablepath="/test_group/test_table"
    recordclass=DBRecord

    def __init__(self,dbasenameroot=None,populate=True):
        """
        Check if table already exists, and if not, create it.

        >>> print DBTable().tablepath
        /test_group/test_table
        """
        if not dbasenameroot:
            if getattr(self.__class__,"_dbasenameroot",None):
                dbasenameroot=self.__class__._dbasenameroot
            else:
                dbasenameroot=Locations.currentuserfolder
        self.__dict__ = self._shared_state.setdefault(dbasenameroot,{})
        self.dbasenameroot=dbasenameroot
        if not hasattr(self,"tablepath"):
            self.tablepath="/"+self.__class__.__name__.lower()
        self.title=self.__class__.__name__
        #
        self.claim_table()

        if populate:
            if self.table.nrows==0:
                self.populate()

    def keys(self):
        return self.recordclass(dbasenameroot=self.dbasenameroot).keys()

    def keys_extended(self):
        return self.recordclass(dbasenameroot=self.dbasenameroot).keys_extended()

    def database(self):
        return Locations().get_dbase(self.dbasenameroot).filename

    def claim_table(self):
        #will create the table if it doesn't exist
        self.table=Locations().get_dbase(self.dbasenameroot)[self]
        return self.table

#store functions
    def populate(self):
        pass

    def store_record_object(self,record_object,check=True):
        """
        THIS IS CAUSING TROUBLE WHEN CHECK==TRUE
        
        >>> r1=DBRecord(3,4,5)
        >>> DBTable().store_record_object(r1,check=True)
        False
        >>> r2=DBRecord(5,6,7)
        >>> DBTable().store_record_object(r2,check=True)
        True
        >>> r2.delete()
        True
        """
        self.claim_table()
        if check:
            if self.query_by_record_object(record_object):
                LOG.warning("{}: not entering {} as already in table "
                            "and check=True"
                            .format(self.__class__.__name__,
                                    record_object._get_match_condition()))
                return False
        tabrow=self.table.row
        for n,scls in record_object.atoms:
            if scls.value is not None:
                tabrow[n]=scls.value
        tabrow.append()
        self.table.flush()
        if hasattr(self,"in_memory_dict"):
            self.in_memory_dict[record_object.value]=record_object
        return True

    def store_many_record_objects(self,iterable,check=True):
        """
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
        ____________________________
        Displayed 1/1 DBTable(Software Test)

        >>> recs=[DBRecord(1,2,3),DBRecord(2,3,4),DBRecord(3,4,5)]
        >>> DBTable().store_many_record_objects(recs,check=True)
        2
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           1        2        3.0    
           2        3        4.0    
        ____________________________
        Displayed 3/3 DBTable(Software Test)

        >>> recs[0].delete()
        True
        >>> recs[1].delete()
        True
        """
        #CHECKING
        self.claim_table()
        if check:
            checked_and_passed=[]
            for rec in iterable:
                if not self.query_by_record_object(rec):
                    checked_and_passed.append(rec)
        else:
            checked_and_passed=iterable
        #STORING
        for rec in checked_and_passed:
            tabrow=self.table.row
            for n,scls in rec.atoms:
                if scls.value is not None:
                    val=scls.value
                    if type(val)==np.string_:
                        val=str(val)
                    try:
                        tabrow[n]=val
                    except Exception as e:
                        LOG.critical("unable to store value {} ({}) in "
                                     "tabrow[{}] because e"
                                     .format(val,type(val),n,e))
                        sys.exit()
            tabrow.append()
        LOG.debug("stored {} {}".format(len(checked_and_passed),
                                        self.__class__.__name__))
        self.table.flush()
        return len(checked_and_passed)

    def store_dictionary(self,dictionary,check=True):
        """
        >>> DBTable().store_dictionary({"dbatom":5,"dbuint8":6,"dbfloat32":7},check=True)
        True
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           5        6        7.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> r2=DBRecord(5,6)
        >>> print r2 in DBTable()
        True
        >>> print r2.delete()
        True
        """
        temp=self.recordclass(dbasenameroot=self.dbasenameroot,
                              **dictionary)
        return self.store_record_object(temp,check)

    def store(self,*args,**kwargs):
        """
        stores either a DBRecord, a series of record values, or kwargs & values
        By default check=True, so a new record will only be added if not already in the table

        >>> r1=DBRecord(3,4,5)
        >>> DBTable().store(r1,check=True)
        False
        >>> DBTable().store(dbatom=5,dbuint8=6,dbfloat32=7,check=True)
        True
        
        #>>> DBTable().store(5,6,7,check=True) #NOT YET IMPLEMENTED
        #False
        
        >>> print DBRecord(5,6,7).delete()
        True
        """
        if "check" in kwargs:
            check=kwargs["check"]
            del kwargs["check"]
        else:
            check=True
        #
        if len(args)==1:
            if issubclass(args[0].__class__,DBRecord):
                return self.store_record_object(args[0],check=check)
        if kwargs:
            return self.store_dictionary(kwargs,check=check)
#private query functions
    def _query_generator(self,querystring):
        """
        e.g.
        '(volume > 15) & (costratio <= 3.0)'
        Returns objects of type defined by self.recordclass
        """
        self.claim_table()
        if getattr(self,"table",None):
            for result in self.table.where(querystring):
                resultlist=result[:]
                rec=self.recordclass(*resultlist,
                                     dbasenameroot=self.dbasenameroot)
                yield rec

    def _query_index_generator(self,querystring):
        """
        Returns indices of matching rows. Used by DBRecord.delete() to find the indices to delete.
        """
        self.claim_table()
        for result in self.table.get_where_list(querystring):
            yield result

    def _yield_values_matching_kwarg(self,**kwarg):
        assert len(kwarg)==1
        key,val=kwarg.items()[0]
        for entry in self.get_values_of_atom(key):
            if entry.startswith(val):
                yield entry

    def query_startingwith(self,**kwargs):
        """
        keywords must be column headers
        if values are strings then will return all CombiFiles
        If multiple kwargs then only intersection of queries will
        be returned
        """
        results_set=set()
        for k,v in kwargs.items():
            results_list=[]
            if type(v)==list:
                results_set2=set()
                for lv in v:
                    r=self.query_startingwith(**{k:lv})
                    results_set2 |= set(r)
                return list(results_set2)
            elif type(v)==str:
                for MS in self._yield_values_matching_kwarg(**{k:v}):
                    for actual_entry in self.query_by_dictionary({k:MS}):
                        if actual_entry not in results_list:
                            results_list.append(actual_entry)
                if not results_set:
                    results_set=set(results_list)
                elif results_list and results_set:
                    results_set &= set(results_list)
        return list(results_set)

    def _is_condition_string(self,query_string):
        """
        Used by DBTable.query() to determine whether a single string argument is a condition string
        or a record_default query. Checks by simply seeing if any of the atom names are in
        query_string.
        >>> DBTable()._is_condition_string("8")
        False
        >>> DBTable()._is_condition_string("(dbatom==8)")
        True
        """
        for name,atm in self.recordclass(dbasenameroot=self.dbasenameroot).atoms:
            if name in query_string:
                return True
        return False
#specific query_methods. All assume correct input and output a list of recordclass objects (or [])
    def query_by_row_index(self,*row_indices):
        """
        >>> print DBTable().query_by_row_index(0)[0]
        DBRecord(3, 4, 5.0)
        """
        self.claim_table()
        output=[]
        for n in row_indices:
            output.append(self.recordclass(*self.table[n],
                                           dbasenameroot=self.dbasenameroot))
        return output

    def query_by_condition_string(self,condition_string):
        """
        See
        https://pytables.github.io/usersguide/condition_syntax.html
        >>> print DBTable().query_by_condition_string("(dbatom==3)")[0]
        DBRecord(3, 4, 5.0)
        """
        return list(self._query_generator(condition_string))

    def query_by_record_default(self,value_to_check_in_record_default):
        """
        See... https://pytables.github.io/usersguide/condition_syntax.html
        >>> print DBTable().query_by_record_default(3)[0]
        DBRecord(3, 4, 5.0)
        """
        if hasattr(self,"in_memory_dictionary"):
            d = self.in_memory_dictionary()
            if value_to_check_in_record_default:
                if value_to_check_in_record_default not in d:
                    return []
                else:
                    return [d[value_to_check_in_record_default]]
        RC=self.recordclass(dbasenameroot=self.dbasenameroot)
        CS=RC._get_default_match_condition(value_to_check_in_record_default)
        return self.query_by_condition_string(CS)

    def query_by_record_object(self,record_object):
        """
        >>> r1=DBRecord(3,4)
        >>> print DBTable().query_by_record_object(r1)[0]
        DBRecord(3, 4, 5.0)
        """
        condition_string=record_object._get_match_condition()
        return self.query_by_condition_string(condition_string)

    def query_by_kwargs(self,**kwargs):
        return self.query_by_dictionary(kwargs)

    def query_by_dictionary(self,dictionary):
        """
        >>> print DBTable().query_by_dictionary({"dbatom":3,"dbuint8":4})[0]
        DBRecord(3, 4, 5.0)
        """
        record_object=self.recordclass(dbasenameroot=self.dbasenameroot,
                                       **dictionary)
        return self.query_by_record_object(record_object)

#general query methods:
    def get(self,*args,**kwargs):
        """
        Smartly determines which query function to call
        returns a single rowobject, or list of rowobjects,
        matching either a string query, e.g.
        
        >>> print DBTable().get("(dbatom<4) & (dbuint8>3)")
        DBRecord(3, 4, 5.0)

        >>> print DBTable().get(DBRecord(3,4))
        DBRecord(3, 4, 5.0)

        >>> print DBTable().get(dbatom=3)
        DBRecord(3, 4, 5.0)

        >>> print DBTable().get(dbatom=DBAtom(3))
        DBRecord(3, 4, 5.0)

        >>> print DBTable().get(0) # Returns the record by row number
        DBRecord(3, 4, 5.0)

        >>> print DBTable().get(3.0) # Tries to return a match to the record default
        DBRecord(3, 4, 5.0)
        """
        warn=kwargs.pop("warn",True)
        expectmultiple=True
        results=[]
        if len(args)>0 and all([type(a)==int for a in args]):
            results=self.query_by_row_index(*args)
        elif len(args)==1:
            if type(args[0])==str:
                if self._is_condition_string(args[0]):
                    if warn:
                        LOG.warning("{}: NB querying using condition string "
                                    "is not advised: Records containing float "
                                    "atoms may be missed due to float precision "
                                    "issues"
                                    .format(self.__class__.__name__))
                    results=self.query_by_condition_string(args[0])
                else:
                    results=self.query_by_record_default(args[0])
            elif type(args[0])==self.recordclass:
                results=self.query_by_record_object(args[0])
            elif type(args[0])==int:
                results=self.query_by_row_index(args[0])
            else:
                results=self.query_by_record_default(args[0])
    
        elif kwargs:
            results=self.query_by_dictionary(kwargs)
        #Now convert single list to single or [] to None, & report warnings
        lenr=len(results)
        if lenr==1:
            results=results[0]
        elif lenr==0:
            results=None
            extra=""
        elif not expectmultiple:
            extra = ". Consider running DBTable method 'strip_duplicates()'?"
        else:
            extra = ""
        if lenr!=1:
            if len(args)==1:
                LOG.debug("query ({}) returns {} results"
                          .format(str(args[0]),lenr)+extra)
            else:
                LOG.debug("query (args={},kwargs={}) returns {} results"
                          .format(args,kwargs,lenr)+extra)
        return results

    def count(self,*args,**kwargs):
        results=self.get(*args,**kwargs)
        if type(results)==list:
            return len(results)
        elif results is None:
            return 0
        else:
            return 1

    def __contains__(self,arg):
        """
        >>> r1=DBRecord(3,4)
        >>> print r1 in DBTable()
        True

        >>> print DBRecord(8,9) in DBTable()
        False
        """
        queryresult=self.query_by_record_object(arg)
        if not queryresult: return False
        else: return True

    def __getitem__(self,query):
        """
        >>> r1=DBRecord(3,4)
        >>> print DBTable()[r1]
        DBRecord(3, 4, 5.0)
        
        >>> print DBTable()[0] # Returns the record by row number
        DBRecord(3, 4, 5.0)

        >>> print DBTable()[3.0] # Tries to return a match to the record default
        DBRecord(3, 4, 5.0)

        >>> print DBTable()["dbatom==2"]
        None
        """
        return self.get(query)

    def __iter__(self):
        """
        >>> for rec in DBTable():
        ...     print rec
        DBRecord(3, 4, 5.0)
        """
        self.claim_table()
        for rec in self.table.iterrows():
            resultslist=rec[:]
            rec=self.recordclass(*resultslist,
                                 dbasenameroot=self.dbasenameroot)
            yield rec

    def get_values_of_atom(self,atomname):
        """
        >>> r2=DBRecord(5,6,5)
        >>> r2.store()
        True
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           5        6        5.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> DBTable().get_values_of_atom("dbuint8")
        {4: 1, 6: 1}
        >>> DBTable().get_values_of_atom("dbfloat32")
        {5.0: 2}
        >>> r2.delete()
        True
        """
        #atm=self.recordclass()["atomname"]
        self.claim_table()
        counter={}
        for row in self.table:
            value=row[atomname]
            if value not in counter:
                counter[value]=1
            else:
                counter[value]+=1
        return counter        

    def get_as_dict(self,atomname=None):
        if atomname is None:
            atomname=self.recordclass.defaultlookup
        output={}
        for record in self:
            if atomname not in output:
                output[atomname]=[record]
            else:
                output[atomname].append(record)
        return output

#general maintenance functions
    def copytodb(self,dbnameroot="All",copysubrecords=True):
        assert dbnameroot!=self.dbasenameroot
        print "SOURCE TABLE\n",self
        allrecs=list(self)
        targetTable=self.__class__(dbnameroot)
        print "TARGET TABLE\n",targetTable
        targetTable.store_many_record_objects(allrecs)
        RC=self.recordclass()
        RC.dbasenameroot=self.dbasenameroot
        if copysubrecords:
            if hasattr(RC,"get_subrecordtable"):
                subrecordtable=RC.get_subrecordtable()
                print "SOURCE SUBTABLE\n",subrecordtable
                allsubrecs=[]
                for rec in allrecs:
                    allsubrecs+=list(rec.yield_records())
                if allsubrecs:
                    targetSubTable=subrecordtable.__class__(dbnameroot)
                    print "TARGET SUBTABLE\n",targetSubTable
                    targetSubTable.store_many_record_objects(allsubrecs)

#
    def strip_duplicates(self):
        """
        Wanring: can be very slow with large tables.
        
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
        ____________________________
        Displayed 1/1 DBTable(Software Test)

        >>> print DBTable().strip_duplicates()
        False

        >>> newr = DBRecord(3,4,5)
        >>> print newr.store(check=False)
        True

        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           3        4        5.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> print DBTable().strip_duplicates()
        True

        >>> newrecs = [DBRecord(3,4,5),DBRecord(4,5,6),DBRecord(7,8,9)]
        >>> print DBTable().store_many_record_objects(newrecs,check=False)
        3

        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           3        4        5.0    
           4        5        6.0    
           7        8        9.0    
        ____________________________
        Displayed 4/4 DBTable(Software Test)
        
        >>> print DBTable().strip_duplicates()
        True

        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           4        5        6.0    
           7        8        9.0    
        ____________________________
        Displayed 3/3 DBTable(Software Test)

        >>> newrecs[1].delete()
        True
        >>> newrecs[2].delete()
        True
        """
        rows_to_delete=[]
        hashes_checked=[]

        self.claim_table()
        for i,r in enumerate(self.table.iterrows()):
            if str(r[:]) in hashes_checked:
                rows_to_delete.append(i)
                LOG.warning("{}: deleting duplicate {} (row {})"
                            .format(self.__class__.__name__,str(r[:]),i))
            else:
                hashes_checked.append(str(r[:]))
        for index in rows_to_delete[::-1]:
            self.table.remove_row(index)
        return rows_to_delete!=[]

    def clear(self,ask=False):
        """
        Deletes the current table.
        >>> DBTable().clear()
        >>> print len(DBTable())
        0

        >>> r1=DBRecord(3,4,5)
        >>> r1.store()
        True
        """
        if ask:
            if not raw_input["Are you sure you want to delete the contents of table {}"][0] in ["y","Y"]:
                print "NOT PERFORMING clear()"
                return
        self.claim_table()
        self.table._f_remove()
#display functions
    def __len__(self):
        """
        >>> print len(DBTable())
        1
        """
        self.claim_table()
        return self.table.nrows

    def display(self,colclip=None,rowclip=179,maxrows=25,printit=True):
        """
        Prints or returns (depending on 'printit' arg) a friendly view of the table
        with items centred in columns that are smartly sized to fit the contents.
        You can override the column width determination by lowering 'colclip',
        or assign individual 'colclip' values by giving the 'colclip' arg a list of ints.
        You can also limit the number of rows displayed with the 'maxrows' arg, and the
        maximum length of each row that will be displayed with the 'rowclip' arg.

        >>> DBTable().display(printit=True)
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
        ____________________________
        Displayed 1/1 DBTable(Software Test)

        >>> DBTable().display(colclip=3,printit=True)
        ____________
        dbatdbuidbfl
        ------------
          3   4  5.0
        ____________
        Displayed 1/1 DBTable(Software Test)

        >>> DBTable().display(rowclip=14,printit=True)
        ______________
         dbatom  dbuin
        --------------
           3        4 
        ______________
        Displayed 1/1 DBTable(Software Test)

        """
        rows=[]
        dimensions=[]
        self.claim_table()
        lenself=len(self)
        if lenself==0:
            headers=self.recordclass(dbasenameroot=self.dbasenameroot)._get_display_headers()
        for i,rec in enumerate(self):
            if i==0:
                headers=rec._get_display_headers()
                dimensions.append([len(h) for h in headers])
                if colclip is None:
                    colclips=[getattr(atm,"colclip",20)
                              for atm in self.recordclass.slots]
                elif type(colclip)==int:
                    colclips=[colclip]*len(headers)
                else:
                    colclips=list(colclip)
            rowdata=rec._get_summary_row()
            if i<maxrows:
                rows.append(rowdata)
                dimensions.append([len(r) for r in rowdata])
            else:
                break
        widths=[min(colclips[i],max(col))
                for i,col in enumerate(zip(*dimensions))]
        padblocks=["{"+":^{}".format(width+2)+"}"
                   for width in widths]
        #
        output=[]
        stringify = lambda lst:"".join([pad.format(element)[:colclips[i]+1]
                                        for i,(pad,element)
                                        in enumerate(zip(padblocks,lst))]
                                        )[:rowclip]
        stringifiedheaders=stringify(headers)
        output.append("_"*len(stringifiedheaders))
        output.append(stringifiedheaders)
        output.append("-"*len(stringifiedheaders))
        for r in rows:
            output.append(stringify(r))
        output.append("_"*len(stringifiedheaders))
        output.append("Displayed {}/{} {}({})"
                      .format(min(lenself,maxrows),
                              lenself,
                              self.__class__.__name__,
                              self.dbasenameroot))
        stringoutput="\n".join(output)
        if printit:
            print stringoutput
        else:
            return stringoutput

    def da(self):
        """
        Display all
        """
        self.display(maxrows=len(self))

    def __str__(self):
        """
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
        ____________________________
        Displayed 1/1 DBTable(Software Test)

        """
        printed=self.display(printit=False)
        return printed

    def output_to_txt(self,filename=None,overwrite="ask"):
        """
        >>> testfilename="temp.tab"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> outfilepath=DBTable().output_to_txt(testfilepath)
        >>> print os.path.basename(outfilepath)
        temp.tab
        >>> print os.path.exists(testfilepath)
        True
        
        #>>> os.remove(testfilepath)
        """
        delimiter="\t"
        tablename=self.__class__.__name__
        if filename is None:
            filename="{}({}).tab".format(tablename,self.dbasenameroot)
            filedir=Locations().get_dbasedir(self.dbasenameroot)
            filename=os.path.join(filedir,filename)
            print filename
        if os.path.exists(filename):
            if overwrite=="ask":
                answer=raw_input("{} already exists. Overwrite it?"
                                 .format(filename))
                if not answer.lower().startswith("y"):
                    return
            elif not overwrite:
                return
        with open(filename,"wb") as fileob:
            writer=csv.writer(fileob,delimiter=delimiter,
                              quoting=csv.QUOTE_MINIMAL)
            for i,rec in enumerate(self):
                if i==0:
                    writer.writerow(rec._get_txt_headers())
                writer.writerow(rec._get_txt_row())
        return filename
#
    def input_from_txt(self,filepath=None,check=True):
        """
        Problem in this function when checking and storing multiple records,
        probably caused by conflicts in switching between read and write modes
        for DBTable.fileob? To avoid this, all checking is done in one step, and
        all storing in the next.

        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
        ____________________________
        Displayed 1/1 DBTable(Software Test)

        >>> testfilename="temp.tab"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> outfilepath=DBTable().input_from_txt(testfilepath,check=False)
        >>> print os.path.basename(outfilepath)
        temp.tab

        >>> os.remove(testfilepath)
        >>> print DBTable()
        ____________________________
         dbatom  dbuint8  dbfloat32 
        ----------------------------
           3        4        5.0    
           3        4        5.0    
        ____________________________
        Displayed 2/2 DBTable(Software Test)

        >>> DBTable().strip_duplicates()
        True
        """
        if filepath is None:
            tablename=self.__class__.__name__
            filename="{}({}).tab".format(tablename,self.dbasenameroot)
            filedir=Locations().get_dbasedir(self.dbasenameroot)
            filepath=os.path.join(filedir,filename)

        if os.path.exists(filepath):
            #First read in records
            recs=[]
            with open(filepath,"rb") as inputfileob:
                reader=csv.reader(inputfileob,delimiter="\t")
                for i,row in enumerate(reader):
                    if i==0:
                        headers=row
                    else:
                        rec=self.recordclass._from_txt_row(row)
                        recs.append(rec)
            #print [str(r) for r in recs]
            self.store_many_record_objects(recs,check=check)
            return filepath
        else:
            LOG.error("{}.input_from_txt() failed because path {} does not exist".format(self.__class__.__name__,filepath))

class DBSharedTable(DBTable):
    _dbasenameroot=shareddbasenameroot
#

#DERIVED ATOMS ################################################################
class InMemory(object):
    """
    Any DBTable subclass that also inherits this class will, after population,
    self-store a dictionary of records accessible by default value, and will
    retrieve records from this dictionary, rather than from a database, if queried
    using just a default value. This prevents the need for recurring database reads.
    """
    def in_memory_dictionary(self):
        """
        >>> print Plates().in_memory_dictionary().keys()
        ['1536', 'B100', '384', '96']
        """
        if getattr(self,"in_memory_dict",{}):
            return self.in_memory_dict
        return self.create_in_memory_dictionary()

    def create_in_memory_dictionary(self):
        self.in_memory_dict=dict([(rec.value,rec) for rec in self])
        return self.in_memory_dict

class ErrorRecord(DBString):
    coltype=tbs.StringCol(1000)
    splitter=" | "
    def record_error(self,error):
        if self.value is None:
            self.value=error
        else:
            self.value+=splitter+error

    def __nonzero__(self):
        if self.value:
            return True
        return False

    def get_flagdict(self):
        """
        >>> er=ErrorRecord("FS101,FS102=missing;A12=contaminated")
        >>> print er.get_flagdict()
        {'FS102': 'missing', 'FS101': 'missing', 'A12': 'contaminated'}
        """
        flagdict={}
        try:
            splitterseparated=self.value.split(self.splitter)
            for splt in splitterseparated:
                semicolonseparated=splt.split(";")
                for cs in semicolonseparated:
                    equalseparated=cs.split("=")
                    commaseparated=equalseparated[0].split(",")
                    for flagged in commaseparated:
                        flagdict[flagged]=equalseparated[-1]
        except:
            pass
        return flagdict

    def Xcalculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            if type(rec)==File:
                fnr=rec.get_filenamereader()
                self.set_value(fnr.properties.get("flags",None))
                #print "CALCULATED",self.value
        return self.value

    def __add__(self,other):
        allerrors=[]
        if self.is_valid():
            allerrors.append(self.value)
        othererror=getattr(other,"value",other)
        if othererror:
            allerrors.append(othererror)
        return ErrorRecord(self.splitter.join(allerrors))

class Name(DBAtom):
    coltype=tbs.StringCol(100)
#

#PLATES #######################################################################
class PlateID(DBString):
    coltype=tbs.StringCol(5)
    strict=False
class Capacity(DBuInt16): pass
class PlateX(DBFloat32): pass
class PlateY(DBFloat32): pass
class PlateC(DBuInt8): pass
class PlateR(DBuInt8): pass
class PlateDx(DBFloat32): pass
class PlateDy(DBFloat32): pass
class PlateSx(DBFloat32): pass
class PlateSy(DBFloat32): pass
class PlateA1x(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            X=rec["platex"].value
            C=rec["platec"].value
            Dx=rec["platedx"].value
            Sx=rec["platesx"].value
            if Sx is None: Sx = 0
            self.set_value(rec.calculate_a1xy(X,C,Dx,Sx))
        return self.value

class PlateA1y(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            Y=rec["platey"].value
            R=rec["plater"].value
            Dy=rec["platedy"].value
            Sy=rec["platesy"].value
            if Sy is None: Sy = 0

            self.set_value(rec.calculate_a1xy(Y,R,Dy,Sy))
        return self.value

#
class Plate(DBRecord,GraphicGenerator):
    tableclassstring="Plates"
    slots=[PlateID,Capacity,PlateX,PlateY,PlateC,PlateR,PlateDx,
           PlateDy,PlateSx,PlateSy,PlateA1x,PlateA1y]
    defaultlookup="plateid"
    coltype=tbs.StringCol(5)
    strict=False
    subrecordtables={}
    titleformat="{prefix}{plateid} format plate ({platec}c x {plater}r){suffix}"
    subfoldernameformat='_Layout views'
    graphicsnamerootformat=titleformat
    pathformatter=os.path.join(Locations()["layouts"],subfoldernameformat,
                               "{graphicsnameroot}.{extension}")

    def get_subrecordtable(self):
        if self.dbasenameroot not in self.__class__.subrecordtables:
            rec=Wells(self.dbasenameroot)
            self.subrecordtables[self.dbasenameroot]=rec
        return self.subrecordtables[self.dbasenameroot]

    def get_subrecordtype(self):
        return Well

    def __len__(self):
        return int(self["platec"].value) * int(self["plater"].value)

    def calculate_a1xy(self,XY,CR,DxDy,SxSy):
        return (XY/2) - ( ((CR-1)/2.) * DxDy ) -SxSy

    def yield_records(self):
        if not hasattr(self,"records"):
            tab=self.get_subrecordtable()
            self.records=tab.get(plate=self["plateid"].value)
        for result in self.records or []:
            yield result

    def yield_colnumbers(self):
        for i in range(1,self["platec"].value+1):
            yield i

    def yield_rowletters(self):
        WL=Well()
        for i in range(1,self["plater"].value+1):
            yield WL.calculate_wellrowletter(i)

    def get_coords(self):
        """
        It's slow to pull together a list of well coords (for plots)
        so only do it once
        """
        if not hasattr(self,"coords"):
            self.coords=[(well["wellx"].value,well["welly"].value)
                         for well in self.yield_records()]
        return self.coords

    def draw(self,**kwargs):
        return PlateView(coords=self.get_coords(),
                         labels=[cr["wellname"].value for cr in self.yield_records()],
                         backgroundcolor='white',
                         labelfontcolor='black',
                         labelfontsize=8,
                         title=self.value,
                         savepath=None,
                         show=True)

class Plates(DBSharedTable,InMemory):
    _shared_state={}
    tablepath="/plates"
    recordclass=Plate
    plateinfo=[("96",{"X":127.76,"Y":85.48,"C":12,"R":8,
                      "Dx":9.0,"Dy":9.0,"Sx":0.0,"Sy":0.0}),
               ("384",{"X":127.76,"Y":85.48,"C":24,"R":16,
                       "Dx":4.5,"Dy":4.5,"Sx":0.0,"Sy":0.0}),
               ("1536",{"X":127.76,"Y":85.48,"C":48,"R":32,
                        "Dx":2.25,"Dy":2.25,"Sx":0.0,"Sy":0.0}),
               ("B100",{"X":91.0,"Y":75.0,"C":10,"R":10,
                        "Dx":70/9.,"Dy":-35/(3*(3**0.5)),
                        "Sx":35/18.,"Sy":0.0})]
    expectedrows=4

    def populate(self):
        #print "POPULATING PLATES"
        self.clear()
        tostore=[]
        for pn,pd in self.plateinfo:
            p=Plate(plateid=pn,
                    capacity=pd["C"]*pd["R"],
                    platex=pd["X"],
                    platey=pd["Y"],
                    platec=pd["C"],
                    plater=pd["R"],
                    platedx=pd["Dx"],
                    platedy=pd["Dy"],
                    platesx=pd.get("Sx"),
                    platesy=pd.get("Sy"),
                    platea1x=None,
                    platea1y=None)
            p.calculate_all()           
            tostore.append(p)
        self.store_many_record_objects(tostore,check=True)
#

#WELLS ########################################################################
class WellID(DBString):
    coltype=tbs.StringCol(10)
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            wn=rec["wellname"].calculate()
            p=rec["plate"].value
            
            self.set_value(rec.calculate_wellid(p,wn))
        return self.value

class WellIndex(DBuInt16):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            r=rec["wellrow"].value
            c=rec["wellcol"].value
            C=rec["plate"]["platec"].value
            #if not r or not c or not C:
            #    return False

            self.set_value(rec.calculate_wellindex(r,c,C))
        return self.value

class WellName(DBString):
    coltype=tbs.StringCol(4)
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            if rec["plate"].value=="B100":
                wi=rec["wellindex"].calculate()
                self.set_value("{:03d}".format(wi+1))
            else:
                #if not r or not c:
                #    return False
                r=rec["wellrow"].value
                c=rec["wellcol"].value

                self.set_value(rec.calculate_wellname(r,c))
        return self.value

class WellRow(DBuInt8):
    def as_letter(self):
        rec=self.get_record()
        if rec is False: return False
        return rec.calculate_wellrowletter(self.value)

class WellCol(DBuInt8): pass
class DistanceFromEdge(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            x=rec["wellx"].calculate()
            y=rec["welly"].calculate()
            xN=rec["wellxn"].calculate()
            yN=rec["wellyn"].calculate()

            #if not x or not y or not xN or not yN:
            #    return False

            self.set_value(rec.calculate_dE(x,y,xN,yN))
        return self.value

class DistanceFromCenter(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            xC=rec["wellxc"].calculate()
            yC=rec["wellyc"].calculate()

            #if not xC or not yC:
            #    return False

            self.set_value(rec.calculate_dC(xC,yC))
        return self.value

class IsBorder(DBBool):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            r=rec["wellrow"].value
            c=rec["wellcol"].value
            R=rec["plate"]["plater"].value
            C=rec["plate"]["platec"].value

            #if not r or not c or not R or not C:
            #    return False

            self.set_value(rec.calculate_isborder(r,c,R,C))
        return self.value

class WellX(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            A1x=rec["plate"]["platea1x"].calculate()
            r=rec["wellrow"].value
            c=rec["wellcol"].value
            Dx=rec["plate"]["platedx"].value

            #if not c or not X or not C or not Dx or not r:
            #    return False
            Sx=rec["plate"]["platesx"].value
            if Sx is None: Sx=0.0
            shift = Sx*2 if r%2==0 else 0

            self.set_value(rec.calculate_x(A1x,c,Dx,shift))
        return self.value

class WellY(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            A1y=rec["plate"]["platea1y"].calculate()
            r=rec["wellrow"].value
            Dy=rec["plate"]["platedy"].value

            #if not r or not Y or not R or not Dy:
            #    return False
            Sy=rec["plate"]["platesy"].value
            if Sy is None: Sy=0.0

            self.set_value(rec.calculate_y(A1y,r,Dy,Sy))
        return self.value

class WellXN(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            x=rec["wellx"].calculate()
            X=rec["plate"]["platex"].value

            #if not x or not X:
            #    return False

            self.set_value(rec.calculate_xN(x,X))
        return self.value

class WellYN(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            y=rec["welly"].calculate()
            Y=rec["plate"]["platey"].value

            #if not y or not Y:
            #    return False

            self.set_value(rec.calculate_yN(y,Y))
        return self.value

class WellXC(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            x=rec["wellx"].calculate()
            X=rec["plate"]["platex"].value

            #if not x or not X:
            #    return False

            self.set_value(rec.calculate_xC(x,X))
        return self.value

class WellYC(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            y=rec["welly"].calculate()
            Y=rec["plate"]["platey"].value

            #if not y or not Y:
            #    return False

            self.set_value(rec.calculate_yC(y,Y))
        return self.value

class Source96(DBString):
    coltype=tbs.StringCol(3)
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            if rec["plate"].value not in ["96","384","1536"]: return False
            X=rec["plate"]["platex"].value
            Dx=rec["plate"]["platedx"].value
            r=rec["wellrow"].value
            c=rec["wellcol"].value
            R=rec["plate"]["plater"].value
            C=rec["plate"]["platec"].value
            if int(R)*int(C) <=96: return False
            #if not r or not c or not R or not C or not sR or not sC:
            #    return False
            self.set_value(rec.calculate_source(r,c,R,C,8,12))
        return self.value

class Pin96(WellID):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            if rec["plate"].value not in ["96","384","1536"]:
                return False

            r=rec["wellrow"].value
            c=rec["wellcol"].value
            R=rec["plate"]["plater"].value
            C=rec["plate"]["platec"].value
            if int(R)*int(C) <=96: return False

            #if not r or not c or not R or not C or not sR or not sC:
            #    return False

            self.set_value(rec.calculate_pin(r,c,R,C,8,12,"96"))
        return self.value

class Source384 (DBString):
    coltype=tbs.StringCol(3)
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            if rec["plate"].value not in ["96","384","1536"]:
                return False

            X=rec["plate"]["platex"].value
            Dx=rec["plate"]["platedx"].value
            r=rec["wellrow"].value
            c=rec["wellcol"].value
            R=rec["plate"]["plater"].value
            C=rec["plate"]["platec"].value
            if int(R)*int(C) <=384: return False

            #if not r or not c or not R or not C or not sR or not sC:
            #    return False

            self.set_value(rec.calculate_source(r,c,R,C,16,24))
        return self.value

class Pin384 (WellID):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            if rec["plate"].value not in ["96","384","1536"]:
                return False

            r=rec["wellrow"].value
            c=rec["wellcol"].value
            R=rec["plate"]["plater"].value
            C=rec["plate"]["platec"].value
            if int(R)*int(C) <=384: return False

            #if not r or not c or not R or not C or not sR or not sC:
            #    return False

            self.set_value(rec.calculate_pin(r,c,R,C,24,16,"384"))
        return self.value

#
class Well(DBRecord):
    """
    Could instead inherit from WellID instead of DBAtom?
    Switch defaultlookup string to an atom?

    >>> w=Well(plate="96",wellrow=2,wellcol=3)
    >>> print w
    Well(-, 96, -, -, 2, 3, -, -, -, -, -, -, -, -, -, -, -, -, -)
    >>> print w["plate"]
    Plate(96, 96, 127.76, 85.48, 12, 8, 9.0, 9.0, 0.0, 0.0, 14.38, 11.24)
    """
    tableclassstring="Wells"
    slots=[WellID,Plate,WellIndex,WellName,WellRow,WellCol,
           DistanceFromEdge,DistanceFromCenter,IsBorder,
           WellX,WellY,WellXN,WellYN,WellXC,WellYC,
           Source96,Pin96,Source384,Pin384]
    defaultlookup="wellid"
    coltype=tbs.StringCol(10)
    strict=True

    def calculate_wellindex(self,r,c,C):
        return ((r-1) *C) + c -1

    def calculate_wellrowletter(self,r):
        """
        """
        assert r>=0
        symbols="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        base=len(symbols)
        digits = []
        while r:
            digits.append(symbols[(r % base)-1])
            r -= 1
            r /= base
        return ''.join(digits[::-1])

    def wellrowletter(self):
        return self.calculate_wellrowletter(self["wellrow"].value)

    def calculate_wellname(self,r,c):
        return self.calculate_wellrowletter(r)+str(c)

    def calculate_wellid(self,p,wn):
        return "{}_{}".format(p,wn)

    def calculate_isborder(self,r,c,R,C):
        return r in [1,R] or c in [1,C]

    def calculate_x(self,A1x,c,Dx,Sx=0):
        x = A1x + ((c-1) * Dx )
        return Sx+x

    def calculate_y(self,A1y,r,Dy,Sy=0):
        y = A1y + ((r-1) * Dy )
        return Sy+y

    def calculate_xN(self,x,X):
        return X-x

    def calculate_yN(self,y,Y):
        return Y-y

    def calculate_xC(self,x,X):
        return x-(X/2.0)

    def calculate_yC(self,y,Y):
        return y-(Y/2.0)

    def calculate_dE(self,x,y,xN,yN):
        return min(x,y,xN,yN)

    def calculate_dC(self,xC,yC):
        return ((xC)**2+(yC)**2)**0.5

    def pinindex(self):
        r,c=self["wellrow"].value,self["wellcol"].value
        R,C=self["plater"].value,self["platec"].value
        return self.calculate_pinindex(r,c,R,C,8,12)

    def calculate_pinindex(self,r,c,R,C,sR,sC):
        #print r,c,R,C,sR,sC
        #pr = ( (r-1) / (R/sR) ) +1
        #pc = ( (c-1) / (C/sC) ) +1
        #return ((pr-1) *sC) + pc -1
        PR = (r-1) / (C/sC) +1
        PC = (c-1) / (R/sR) +1
        return ((PR-1) *sC) + PC -1

    def calculate_pin(self,r,c,R,C,sR,sC,p):
        return self.calculate_wellid(p,self.calculate_pinname(r,c,R,C,sR,sC))

    def calculate_pinname(self,r,c,R,C,sR,sC):
        PR = (r-1) / (C/sC)
        PC = (c-1) / (R/sR)
        return self.calculate_wellname(PR+1,PC+1)

    def calculate_source(self,r,c,R,C,sR,sC):
        ySou= (r-1) % (C/sC)
        xSou= (c-1) % (R/sR)
        return "S{:02d}".format((ySou*(C/sC)) + xSou + 1)
#
    def yield_neighbours(self,distancelimit=200,shelllimit=1):
        """
        Yields them in order of distance: nearest first. Can limit by distance or shell.
        """
        plate=self["plate"]
        plater=plate["plater"].value
        platec=plate["platec"].value
        wellr=int(self["wellrow"].value)
        wellc=int(self["wellcol"].value)
        allwells=[[round(well.distance_to(self),2),
                   int(well["wellrow"].value),
                   int(well["wellcol"].value),well]
                  for well in plate.yield_records()]
        allwells.sort()
        for d,r,c,w in allwells[1:]:
            if d>distancelimit:
                break
            elif abs(wellr-r)>shelllimit:
                break#
            elif abs(wellc-c)>shelllimit:
                break
            yield w

    def distance_to(self,other):
        Dx=self["wellx"].value-other["wellx"].value
        Dy=self["welly"].value-other["welly"].value
        return ((Dx)**2+(Dy)**2)**0.5        

#
class Wells(DBSharedTable,InMemory):
    """
    print len(Wells(viewfilter=Well(plate="384")))
    384

    Wells(viewfilter="distancefromcenter>50.0") #fails, so NYI, see DBTable.__iter__
    """
    _shared_state={}
    tablepath="/wells"
    recordclass=Well

    def populate(self):
        self.clear()
        tostore=[]
        for p in Plates():
            for r in range(1,p["plater"].value+1):
                for c in range(1,p["platec"].value+1):
                    w=Well(plate=p,wellrow=r,wellcol=c)
                    w.passerrorsto=self
                    w.calculate_all()
                    tostore.append(w)
        self.store_many_record_objects(tostore,check=False) # checking all is very slow
        return tostore


#

#FILES ########################################################################
class FileID(DBString):
    coltype=tbs.StringCol(10)
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            self.set_value("{}{}{}"
                           .format(rec["user"].calculate() or "",
                                   rec["experimentnumber"].calculate() or "",
                                   rec["fileletter"].calculate()) or "")
        return self.value

class Filepath(DBString):
    coltype=tbs.StringCol(512)
    colclip=9

    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            if rec.__class__.__name__=="PlateLayout":
                LS=rec["layoutstring"]
                if LS.is_valid():
                    filepath=PlateLayout.look_for_layout_file(LS.value)
                    if filepath:
                        self.set_value(os.path.basename(filepath))
        return self.value

    def get_fullpath(self):
        if self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            
            if rec.__class__.__name__=="PlateLayout":
                return os.path.join(Locations()["layouts"],
                                    self.value)
            else:
                subfolder=Locations().get_userpath(rec.dbasenameroot)
                return os.path.join(subfolder,self.value)
        return None

    def exists(self):
        if self.is_valid():
            return os.path.exists(self.get_fullpath())
        else:
            return False

    def norm(self):
        if self.is_valid():
            return os.path.normpath(self.get_fullpath())
        else:
            return None

class User(DBString):
    coltype=tbs.StringCol(5)
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            self.set_value(fnr.properties.get("user",None))
        return self.value

class ExperimentNumber(DBuInt8):
    coltype=tbs.UInt8Col()
    shortheader="ex#"
    colclip=4
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            self.set_value(fnr.properties.get("experimentnumber",None))
        return self.value

class ExperimentID(DBString):
    coltype=tbs.StringCol(20)
    shortheader="exid"
    colclip=5
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            self.set_value("{}{}".format(rec["user"].calculate() or "",
                                         rec["experimentnumber"].calculate()
                                         or ""))
        return self.value
   
class FileLetter(DBString):
    coltype=tbs.StringCol(20)
    shortheader="fL"
    colclip=3
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            self.set_value(fnr.properties.get("fileletter",None))
        return self.value

class Treatment(DBString):
    coltype=tbs.StringCol(40)
    controls=Locations().get_config_dict()["controls"]
    calculators=Locations().get_config_dict()["phenotypecalculators"]

    def calculate(self):
        """
        Treatment atom can be used in Reading records as well as File records,
        but can't then be calculated, so checks for get_filenamereader method
        """
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            if hasattr(rec,"get_filenamereader"):
                fnr=rec.get_filenamereader()
                self.set_value(fnr.properties.get("treatment",None))
        return self.value

    def is_control(self):
        return str(self.value).strip() in self.controls

    def get_phenotypecalculators(self):
        """
        Consults the config.txt PhenotypeCalculators section
        If no match to any regex header in that, will default to
        those listed in '!default'
        """
        def convert_calculatornames_into_calculators(lst):
            output=[]
            for s in lst:
                if s in globals():
                    output.append(globals()[s])
            return output
        
        if not self.calculators:
            LOG.error("Can't find phenotypecalculators in config.txt")
            return [MaximumChangeCalc]
        specialkeys={k:convert_calculatornames_into_calculators(v)
                     for k,v in self.calculators.items()
                     if k.startswith("!")}
        otherkeys={k:convert_calculatornames_into_calculators(v)
                   for k,v in self.calculators.items()
                   if k not in specialkeys}
        for k,v in otherkeys.items():
            if re.match(k,self.value):
                LOG.info("Matched treatment {} to phenotypecalculators "
                         "for {} = {}".format(self.value,k,
                                              str([c.__name__ for c in v])))
                return v
        LOG.info("Haven't found special phenotypecalculators for treatment {}"
                 " in config.txt, so using !default = {}"
                 .format(self.value,str([c.__name__
                                         for c
                                         in specialkeys["!default"]])))
        return specialkeys["!default"]

class ExperimentTimeStamp(DBDateTime):
    shortheader="exTS"
    colclip=6

class Note(DBString):
    coltype=tbs.StringCol(100)
    colclip=5
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            self.set_value(fnr.properties.get("note",None))
        return self.value

class TimeOffset(DBFloat32):
    nullvalue=-100.0
    invalid_values=[None,"-","",np.nan,float('nan'),nullvalue]
    shortheader="timOff"
    colclip=6
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            timeoffset=fnr.properties.get("timeoffset",self.nullvalue)
            self.set_value(timeoffset)
        return self.value

class EmptyReading(DBBool):
    shortheader="emptyR"
    colclip=3
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            self.set_value(fnr.properties.get("emptyreading",False))
        return self.value

class Reorient(DBBool):
    shortheader="R"
    colclip=3
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            self.set_value(fnr.properties.get("reorient",None))
        return self.value

class IsSurvivor(DBBool):
    shortheader="isS"
    colclip=3
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            self.set_value(fnr.properties.get("issurvivor",False))
        return self.value

class SurvivorStart(DBuInt8):
    shortheader="sS"
    colclip=3
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            fnr=rec.get_filenamereader()
            self.set_value(fnr.properties.get("survivorstart",None))
        return self.value

class FileReader(DBString):
    shortheader="fRd"
    coltype=tbs.StringCol(100)
    colclip=3

class NCurves(DBuInt16):
    invalid_values=[None,"-","",np.nan,float('nan'),0,0.0]
    
class TimeSeries(DBSeries):
    timevalues=DBSeries._get_trimmed
    allowed_difference=0.01
    colclip=10

    def __eq__(self,other):
        timepointstack=[self.timevalues(),other.timevalues()]
        pairedup=map(lambda *row:[elem or 0 for elem in row], *timepointstack)
        #print pairedup
        stdevs=[np.std(col) for col in pairedup]
        #print stdevs
        sumstddev=sum(stdevs)
        #print sumstddev
        return sumstddev <= self.allowed_difference

class TimeSpan(DBFloat32):
    invalid_values=[None,"-","",np.nan,float('nan'),0,0.0]
    shortheader="tSpn"
    colclip=5
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            TV=rec["timevalues"]
            if TV:
                self.set_value(max(TV)-min(TV))
        return self.value

    def is_sufficient(self,fortext="unspecificed operation"):
        if self.is_valid():
            if self.value>0.2:
                return True
        LOG.info("timespan {} for {} insufficient for {}"
                 .format(self.value,self.get_record().value,fortext))
        return False

class NMeasures(DBuInt16):
    invalid_values=[None,"-","",np.nan,float('nan'),0,0.0]
    shortheader="nMe"
    colclip=3
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            n=len(rec["timeseries"].timevalues())
            self.set_value(n)
        return self.value

class TempSeries(TimeSeries):
    tempvalues=DBSeries._get_trimmed

class Size(DBuInt32):
    invalid_values=[None,"-","",np.nan,float('nan'),0,0.0]
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            filepath=rec["filepath"].get_fullpath()
            if filepath:
                if os.path.exists(filepath):
                    self.set_value(os.path.getsize(filepath))
        return self.value

class Genotyped(DBBool): pass

class DateModified(DBDateTime):
    shortheader="dateM"
    colclip=7
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            filepath=rec["filepath"].get_fullpath()
            if filepath:
                if os.path.exists(filepath):
                    self.set_value(os.path.getmtime(filepath))
        return self.value
#
class LayoutString(DBString):
    coltype=tbs.StringCol(100)
    strict=True

    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            if "filepath" in rec._get_deep_headers():
                if rec["filepath"].is_valid():
                    FP=rec["filepath"].get_fullpath()
                    LS=os.path.splitext(os.path.basename(FP))[0]
                    self.set_value(LS)
                    rec.value=LS
        return self.value

class PlateLayout(DBRecord,GraphicGenerator):
    """
    
    """
    tableclassstring="PlateLayouts"
    slots=[LayoutString,Filepath,Plate,Size,Genotyped,DateModified,ErrorRecord]
    defaultlookup="LayoutString"
    coltype=tbs.StringCol(100)
    colclip=15
    strict=True
    subrecordtables={}
    standard="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890.,'-_;:~+ "
    readers={".xls":XlsxPlateLayoutReader,
             ".xlsx":XlsxPlateLayoutReader,
             ".csv":CsvPlateLayoutReader}
    blankvalues=['b',"-","",None]
    titleformat="{prefix}{layoutstring} ({plate}){suffix}"
    subfoldernameformat='_Layout views'
    graphicsnamerootformat="{layoutstring} ({plate})"
    pathformatter=os.path.join(Locations()["layouts"],
                               subfoldernameformat,
                               "{prefix}{graphicsnameroot}{suffix}.{extension}")
    dbasenameroot=""

    def get_subrecordtable(self):
        if self.dbasenameroot not in self.__class__.subrecordtables:
            rec=PlatePositions(self.dbasenameroot)
            self.subrecordtables[self.dbasenameroot]=rec
        return self.subrecordtables[self.dbasenameroot]

    def get_subrecordtype(self):
        return PlatePosition

    @classmethod
    def preprocess(cls,layoutstring):
        """
        """
        original=layoutstring
        if type(layoutstring) not in [str,unicode]:
            LOG.critical("has been passed a non-string: {} ({})"
                         .format(layoutstring,type(layoutstring)))
            sys.exit()
        unacceptable_characters=set(layoutstring)-set(cls.standard)
        if unacceptable_characters:
            LOG.critical("has been passed layoutstring {} with unacceptable character(s) {}".format(layoutstring,unacceptable_characters))
            sys.exit()
        if layoutstring[0]=="'":
            layoutstring=layoutstring[1:]
        if layoutstring[-1]=="'":
            layoutstring=layoutstring[:-1]
        fullpath=cls.look_for_layout_file(layoutstring)
        if not fullpath:
            PL=cls(layoutstring=layoutstring,
                   complete=True,
                   read=True)
        else:
            filename=os.path.basename(fullpath)
            PL=cls(layoutstring=os.path.splitext(filename)[0],
                   filepath=filename,
                   complete=True,
                   read=True)
        return PL

    @classmethod
    def look_for_layout_file(cls,basename):
        """
        Look in Layouts folder only
        Try extensions if necessary
        """
        extension=os.path.splitext(basename)[-1]
        if not extension:
            triedpath=cls.look_for_layout_file(basename+".xlsx")
            if not triedpath:
                triedpath=cls.look_for_layout_file(basename+".csv")
            if triedpath:
                return triedpath
        else:
            fullpath=os.path.join(Locations()["layouts"],basename)
            if not os.path.exists(fullpath):
                LOG.critical("'{}' not found"
                             .format(fullpath))
                return False
            return fullpath

    def file_exists(self):
        return self["filepath"].is_valid()

    def is_genotyped(self):
        not_genotyped=[]
        genotyped=[]
        for pp in self.yield_records():
            if pp["rqtlgroup"].is_valid():
                genotyped.append(pp)
            else:
                not_genotyped.append(pp)
        return len(genotyped)>len(not_genotyped)

    def read(self,store=True):
        """
        >>> testfilename="Example layout 384.xlsx"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> pl=PlateLayout(filepath=testfilepath)
        >>> platepositions=pl.read(store=False)
        >>> print len(list(pl.yield_records()))
        384
        >>> print platepositions[0]
        PlatePosition(Example layout 384_384_A1, 0, Example layout 384, 384_A1, s1, False, 1)
        """
        self.calculate_all()
        if hasattr(self,"records"):
            return True
        if self.has_been_read():
            return True

        filepath=self["filepath"].get_fullpath()
        layoutstring=self["layoutstring"].value
        readerclass=self.readers[os.path.splitext(filepath)[-1]]
        r=readerclass(filepath)
        try:
            shareddata,rowdata=r.parse()
        except Exception as e:
            LOG.error("couldn't parse {} because {} {}".format(filepath,e,get_traceback()))
            return
        plate=Plates().get(capacity=len(rowdata))
        if plate is None:
            LOG.error("{} rows in file {} which doesn't match any plate"
                      .format(len(rowdata),filepath))
            return

        self.samplenames,self.groupnames=[],[]
        self.records=[]
        for well,r in zip(plate.yield_records(),rowdata):
            self.samplenames.append(r["samplename"])
            self.groupnames.append(r.get("groupname",None))
            st=Strain(str(r.get("samplename",None)))
            blnk=st.is_blank()
            pp=PlatePosition(platepositionid="{}_{}"
                             .format(layoutstring,well["wellid"]),
                             plateindex=well["wellindex"].value,
                             platelayout=self["layoutstring"].value,
                             well=well,
                             strain=st,
                             isblank=blnk,
                             groupid=str(r.get("groupname",None)) )
            self.records.append(pp)
        if len(self.records)!=plate["capacity"].value:
            LOG.error("Incorrect number of plate positions for PlateLayout "
                      "{} ({} not {} as expected)"
                      .format(str(self),
                              len(self.records),
                              plate["capacity"].value))
            return
            
        self.update_atoms(plate=plate,
                          size=os.path.getsize(filepath),
                          genotyped=self.is_genotyped(),
                          datemodified=os.path.getmtime(filepath))
        if store:
            PlatePositions().store_many_record_objects(self.records,
                                                       check=True)
            if self not in PlateLayouts():
                self.store(check=False)
        return self.records

    def save(self,filepath=None):
        if filepath is None:
            if not self["filepath"].is_valid():
                LOG.error("can't save as no valid filepath")
                return False
            else:
                filepath=self["filepath"].get_fullpath()
        if not filepath.startswith(Locations()["layouts"]):
            filepath=os.path.join(Locations()["layouts"],filepath)
        filename,extension=os.path.splitext(filepath)
        if extension in [".xlsx",".xls",""]:
            extension=".xlsx"
            filepath=filename+extension
        rdr=self.readers[extension]
        rdroutput=rdr.create(filepath,self)
        return rdroutput

    def store_fully(self):
        """
        Stores the PlateLayout object in the PlateLayouts table,
        & stores all platepositions in self.platepositions
        & stores csv or xlsx file if they don't already exist
        (e.g. if PlateLayout was generated by break_down function).
        """
        if self.is_stored():
            LOG.warning("already stored {}".format(self))
            self.save()
            return False
        if not getattr(self,"platepositions",[]):
            LOG.error("no platepositions for {}".format(self))
            return False
        if not self["filepath"].is_valid():
            originalfilepath=os.path.join(Locations()["layouts"],
                                          self["layoutstring"].value)
            alteredfilepath=self.save(originalfilepath)
            LOG.debug("alteredfilepath {}".format(alteredfilepath))
            self["filepath"].set_value(alteredfilepath)
            self["layoutstring"].set_value(os.path.split(alteredfilepath)[-1])
            self["size"].calculate()
            self["datemodified"].calculate()
        for pp in self.platepositions:
            pp["platelayout"].set_value(self.value)
        PlatePositions().store_many_record_objects(self.platepositions,
                                                   check=True)
        self.store(check=True)
        self.save()

    def has_changed(self):
        """
        checks filepath and sees if path still exists
        and if so whether self["size"] or self["datemodifed"] are as expected.
        """
        filepath=self["filepath"].get_fullpath()

        if not os.path.exists(str(filepath)):
            return False

        if self["size"].value==None:
            return True
        previoussize=int(self["size"].value)
        currentsize=int(os.path.getsize(filepath))
        if previoussize!=currentsize:
            LOG.debug("{} has different size, {} not {}"
                      .format(filepath,currentsize,previoussize))
            return True
        previousdate=int(self["datemodified"].value)
        currentdate=int(os.path.getmtime(filepath))
        if previousdate!=currentdate:
            LOG.debug("{} has different datemodified, {} not {}"
                      .format(filepath,currentdate,previousdate))
            return True
        return False

    def has_been_read(self):
        if not hasattr(self,"alreadyread"):
            query=self.get_subrecordtype()(platelayout=self.value)
            self.alreadyread=query in self.get_subrecordtable()
        return self.alreadyread

    def yield_records(self,**kwargs):
        """
        >>> testfilename="Example layout 384.xlsx"
        >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)
        >>> pl=PlateLayout(filepath=testfilepath)
        >>> platepositions=pl.read(store=False)
        >>> print list(pl.yield_records())[0]
        PlatePosition(Example layout 384_384_A1, 0, Example layout 384, 384_A1, s1, False, 1)
        """
        if not hasattr(self,"records"):
            tab=self.get_subrecordtable()
            self.records=tab.get(platelayout=self.value,
                                 **kwargs)
        for result in self.records or []:
            yield result

    def is_readable(self):
        if self.value in PlateLayouts():
            return True
        return self.read(store=False)

    def get_coords(self):
        """
        It's slow to pull together a list of well coords (for plots)
        so only do it once
        """
        if not hasattr(self,"coords"):
            self.coords=self["plate"].get_coords()
        return self.coords

    def nstrains(self):
        if not hasattr(self,"_nstrains"):
            self._nstrains=len(Counter([rec["strain"]
                                        for rec in self.yield_records()]))
        return self._nstrains

    @classmethod
    def create(cls,*args,**kwargs):
        self=cls()
        self.platepositions=[]
        kwargs.setdefault("relabel","strain")
        kwargs.setdefault("rearrange",True)
        kwargs.setdefault("plate",Plates()["384"])
        kwargs.setdefault("save",True)
        for nm,atm in self.atoms:
            if nm in kwargs:
                self[nm]=kwargs[nm]

        initialplatepositions=[]
        for a in args:
            if type(a)==list:
                initialplatepositions+=a
            elif type(a).__name__=="generator":
                initialplatepositions+=list(a)
            elif type(a).__name__=="PlatePosition":
                initialplatepositions+=[a]
            elif type(a).__name__=="PlateLayout":
                initialplatepositions+=list(a.yield_records())

        if kwargs["rearrange"]:
            paired=zip(kwargs["plate"].yield_records(),initialplatepositions)
            for targetwell,initialplateposition in paired:
                NPP=PlatePosition(platepositionid=self["layoutstring"],
                                  plateindex=targetwell["wellindex"],
                                  platelayout=self,
                                  well=targetwell,
                                  strain=str(initialplateposition[kwargs["relabel"]].value),
                                  isblank=initialplateposition["isblank"],
                                  groupid=initialplateposition["groupid"])
                self.platepositions.append(NPP)
        else:
            self.platepositions=initialplatepositions

        if kwargs["save"]:
            self.store_fully()
        return self

    def draw(self,**kwargs):
        return LayoutView(self,**kwargs)

    def display(self,label="strain",delimiter="\t",printit=True):
        platepositions=self.yield_records()
        colheaders=[""]+list(self["plate"].yield_colnumbers())
        rowheaders=list(self["plate"].yield_rowletters())
        rowlength=len(colheaders)-1
        data=[pp[label].value for pp in platepositions]
        output=[delimiter.join([str(ch) for ch in colheaders])]

        i=0
        for rowheader in rowheaders:
            output.append(delimiter.join([rowheader]+data[i:i+rowlength]))
            i+=rowlength
        output="\n".join(output)
        if printit:
            print output
        else:
            return output

    def make_from(self,*sourceplatelayouts,**kwargs):
        """
        creates a Stinger retargeting csv file, formatted like this:
        SOURCEPLATEID,	SOURCEDENSITY,	SOURCECOLONYCOLUMN,	SOURCECOLONYROW,TARGETPLATEID,	TARGETDENSITY,	TARGETCOLONYCOLUMN,	TARGETCOLONYROW,
        Plate_1     	1536	        21              	B           	Plate_2     	96          	2       	        E

        """
        usesinglesource=kwargs.get("usesinglesource",True)
        pl=self._get_table()
        layoutobs=[]
        layoutstrs=[]
        for s in sourceplatelayouts:
            #print ">",s
            if type(s)==str:
                layoutstrs.append(s)
                layoutobs.append(pl.get(s))
            elif type(s).__name__=="PlateLayout":
                layoutstrs.append(s.value)
                layoutobs.append(s)
            else:
                LOG.error("UNIDENTIFIED TYPE {}({})"
                          .format(type(s),s))
        
        #create dictionary of all strains with source locations
        sourceplatepositions=[]
        for l in layoutobs:
            sourceplatepositions+=list(l.yield_records(store=False))
        d={}
        for pp in sourceplatepositions: 
            if pp["strain"].value not in d:
                d[pp["strain"].value]=[pp]
            else:
                d[pp["strain"].value]+=[pp]
        
        rowdata=[]
        used={}
        for pos in self.yield_records(store=False):
            
            strainid=pos["strain"].value
            if strainid not in used:
                used[strainid]=0
            else:
                used[strainid]+=1
            sources=d.get(strainid,None)
            if not sources:
                continue
            if usesinglesource:
                pickindex=0
            else:
                #if multiple sources, cycles through them
                pickindex=used[strainid]%len(sources) 
            pick=sources[pickindex]
            rowdata.append([pick["layoutstring"].value, #SOURCEPLATEID
                            pick["capacity"].value, #SOURCEDENSITY
                            pick["wellcol"].value, #SOURCECOLONYCOLUMN
                            pick["wellrow"].as_letter(), #SOURCECOLONYROW
                            self["layoutstring"].value, #TARGETPLATEID
                            self["capacity"].value, #TARGETDENSITY
                            pos["wellcol"].value, #TARGETCOLONYCOLUMN
                            pos["wellrow"].as_letter()]) #TARGETCOLONYROW

        rowdata.sort(key=lambda row: (row[0],row[3],row[2]))
        filepath="{} from {}.csv".format(os.path.splitext(self.value)[0],
                                         ", ".join([os.path.splitext(s)[0]
                                                    for s in layoutstrs]))
        LOG.info("CREATING STINGER FILE {}".format(filepath))
        StingerReader.create(rowdata,filepath)

    @classmethod
    def load_from_stinger_file(cls,stingerfilepath):
        """
        Returns a new platelayout object, with platepositions, from a
        Stinger retargeting .csv file.
        Asks whether you want to store it and its positions.
        Can be checked for equivalence to another or to one already stored.
        """
        stingerfile=StingerReader(stingerfilepath)
        fullplatename=os.path.splitext(os.path.split(stingerfilepath)[-1])[0]
        sd,rd=stingerfile.parse()
        platelayoutnames=list(set([r["TARGETPLATEID"] for r in rd]))
        assert len(platelayoutnames)==1
        platelayoutname=platelayoutnames[0]
        LOG.debug("loading stinger file {} {}"
                  .format(fullplatename,platelayoutname))
        already_exists=PlateLayout(platelayoutname) in PlateLayouts()
        #first create new empty PlateLayout object
        output=cls()
        platepositions=[]
        #now create platepositions and store in platepositions
        for i,row in enumerate(rd):
            sourceplate=Plates().get(capacity=row["SOURCEDENSITY"])
            sourcewell=Wells().get(wellname="{}{}"
                                   .format(row["SOURCECOLONYROW"],
                                           row["SOURCECOLONYCOLUMN"]),
                                   plate=sourceplate)
            sourceplateposition=PlatePositions().get(platelayout=row["SOURCEPLATEID"],
                                                     well=sourcewell)
            sourcestrain=sourceplateposition["strain"]

            ncurves=row["TARGETDENSITY"]
            targetplate=Plates().get(capacity=ncurves)
            targetwell=Wells().get(wellname="{}{}"
                                   .format(row["TARGETCOLONYROW"],
                                           row["TARGETCOLONYCOLUMN"]),
                                   plate=targetplate)
            targetppid="{}_{}_{}".format(platelayoutname,
                                         targetplate["plateid"],
                                         targetwell["wellname"].value)
            assert row["TARGETPLATEID"]==platelayoutname
            TP=PlatePosition(platepositionid=targetppid,
                             plateindex=targetwell["wellindex"],
                             platelayout=platelayoutname,
                             well=targetwell,
                             strain=sourcestrain,
                             isblank=sourcestrain.is_blank())
            platepositions.append(TP)

        platepositions.sort(key=lambda ob:ob["plateindex"].value)

        if already_exists:
            #check for correctness
            error=0
            for pp in platepositions:
                if pp not in PlatePositions():
                    error=1
            if error:
                LOG.error("plateposition missing from PlatePositions()")
            else:
                output=globals()[cls.tableclassstring]().get(platelayoutname)
                output.platepositions=platepositions
                LOG.info("Stinger file {} produces platelayout {}"
                         .format(stingerfilepath,output))
                return output
        else:
            LOG.info("Stinger file {} produces new unknown platelayout"
                     .format(stingerfilepath))
            output=cls(layoutstring=platelayoutname,
                       ncurves=ncurves)
            output.platepositions=platepositions
            return output

    def break_down(self,targetsize,store=False,extension=".xlsx",
                   draw=False,save=False):
        """
        Breaks down an array into smaller arrays, creating platelayout objects for each.
        """
        currentsize=self["capacity"].value
        targetplate=Plates().get(capacity=targetsize)
        targetwells=targetplate.yield_records()
        layoutname=self.value
        layoutroot=os.path.splitext(layoutname)[0]
        nplates=currentsize/targetsize
        pinnames,pinindices,platepositions,targetnames=[],[],[],[]
        for i,pp in enumerate(self.yield_records()):
            r,c=pp["wellrow"].value,pp["wellcol"].value
            R,C=pp["plater"].value,pp["platec"].value
            sR,sC=targetplate["plater"].value,targetplate["platec"].value
            platepositions.append(pp)
            #pinindex= int(i/nplates)
            pinindex = pp["well"].calculate_pinindex(r,c,R,C,sR,sC)
            pinindices.append(pinindex)
            
            pinname=pp["well"].calculate_pinname(r,c,R,C,sR,sC)
            pinnames.append(pinname)
            targetname=pp["well"].calculate_source(r,c,R,C,sR,sC)
            targetnamefull="{}_{}_{}{}".format(layoutroot,
                                               targetsize,
                                               targetname,
                                               extension)
            targetnames.append(targetnamefull)
        
        targetdict={}
        targetnameset=sorted(set(targetnames))
        assert len(targetnameset)==nplates
        for targetname in targetnameset:
            targetdict[targetname]=PlateLayout(layoutstring=targetname,
                                               plate=targetplate)
            targetdict[targetname].platepositions=[]
        #
        for pn,plin,pp,tn in zip(pinnames,pinindices,
                                 platepositions,targetnames):
            newwell="{}_{}".format(targetsize,pn)
            ppid="{}_{}".format(tn,newwell)
            strn=pp["strain"].value
            isbk=pp["isblank"].value
            grpid=pp["groupid"].value
            npp=PlatePosition(platepositionid=ppid,
                              plateindex=plin,
                              platelayout=targetdict[tn].value,
                              well=newwell,
                              strain=strn,
                              isblank=isbk,
                              groupid=grpid)
            targetdict[tn].platepositions.append(npp)

        for target in targetdict.values():
            if draw:
                target.draw(save=save)
            if store:
                target.store_fully()
        return targetdict

    def build_up(cls,sourceplates):
        pass

class PlateLayouts(DBSharedTable,InMemory):
    """
    
    """
    _shared_state={}
    tablepath="/platelayouts"
    recordclass=PlateLayout

    def update(self,**kwargs):
        """
        Any new files are added. Any changed files are reread.
        """
        dm=DirectoryMonitor(Locations()["layouts"],include=[".xlsx",".csv"])
        found_paths=[os.path.normpath(p) for p in dm]

        stored_files=[f for f in self]
        stored_dict=dict([(f["filepath"].get_fullpath(),f)
                          for f in stored_files if f["filepath"].is_valid()])
        stored_paths=stored_dict.keys()

        new_paths=[p for p in found_paths if p not in stored_paths]
        missing_paths=[p for p in stored_paths if p not in found_paths]
        changed_paths=[f["filepath"].get_fullpath()
                       for f in stored_files if f.has_changed()]

        if missing_paths:
            LOG.info("REMOVING MISSING PLATELAYOUTS")
            for path in missing_paths:
                pl=PlateLayout(filepath=os.path.basename(path))
                LOG.info("about to delete {}".format(pl))
                pl.delete()

        if changed_paths:
            LOG.info("REMOVING CHANGED PLATELAYOUTS")
            for path in changed_paths:
                pl=PlateLayout(filepath=os.path.basename(path))
                pl.calculate_all()
                LOG.info("about to delete {}".format(pl))
                pl.delete()

        if new_paths+changed_paths:
            LOG.info("ADDING NEW & CHANGED PLATELAYOUTS")
            for path in new_paths+changed_paths:
                pl=PlateLayout(filepath=os.path.basename(path))
                try:
                    pl.read(store=True)
                except:
                    LOG.error("couldn't read platelayout {}"
                              .format(os.path.normpath(path)))

        #PlatePositions().update()
        return self

    def total(self):
        return sum([p["capacity"].value for p in self])

#
class IsControl(DBBool):
    treatments=["YPD","COM"]
    shortheader="isC"
    colclip=4

class AllProcessed(DBBool):
    shortheader="allP"
    colclip=5
    
#

#PHENOTYPE CALCULATORS ########################################################
class PhenotypeCalculator(object):
    allowed=["Reading","CombiReading","ControlledReading"]

    @classmethod
    def all(cls,*readobjects):
        for CL in cls.__subclasses__():
            cl=CL(readobjects[0])
            print CL.__name__,cl.get_header_list(),cl.get_phenotype_list(readobjects[-1])

    def __init__(self,experimentobject=None):
        for k,v in self.__class__.__dict__.items():
            if not type(v).__name__=="function":
                self.__dict__[k]=v
        if experimentobject:
            self.experimentobject=experimentobject

    def find_timefocus(self):
        try:
            self.timefocus=self.experimentobject["timefocus"].value
            self.plusminus=self.experimentobject["plusminus"].value
            self.maxtime=max(self.experimentobject.timevalues())
        except:
            self.timefocus=None
            self.plusminus=None
            self.maxtime=None

    def get_header_list(self):
        if not hasattr(self,"headers"):
            self.find_timefocus()
            self.headers=[self.internalheaderformat.format(**self.__dict__)]
        return self.headers

    def get_external_headers(self):
        if not hasattr(self,"external"):
            self.find_timefocus()
            self.external=[self.externalheadercode.format(**self.__dict__)]
        return self.external

class MaximumChangeCalc(PhenotypeCalculator):
    internalheaderformat="MaximumChange"
    externalheadercode="MxCh"

    def get_phenotype_list(self,record):
        """
        readingobject could be a reading, combireading or controlledreading
        """
        assert record.__class__.__name__ in self.allowed
        return [record["maximumchange"]]

class AverageWithoutAgarCalc(PhenotypeCalculator):
    internalheaderformat="AverageWithoutAgar({timefocus:.1f}hrs+-{plusminus})"
    externalheadercode="AvWoAg({timefocus:.1f}hrs+-{plusminus})"

    def get_phenotype_list(self,record):
        """
        readingobject could be a reading, combireading or controlledreading
        """
        assert record.__class__.__name__ in self.allowed
        av,nreadings=record.average_about_time(timepoint=self.timefocus,
                                               plus_minus=self.plusminus,
                                               report=False)
        return [av]

class TreatmentRatioCalc(PhenotypeCalculator):
    allowed=["ControlledReading"]
    internalheaderformat="TreatmentRatio({timefocus:.1f}hrs+-{plusminus})"
    externalheadercode="TR({timefocus:.1f}hrs+-{plusminus})"

    def get_phenotype_list(self,record):
        """
        readingobject must be a controlledreading
        """
        assert record.__class__.__name__ in self.allowed
        return [record["ratio"].value]

class LagCalc(PhenotypeCalculator):
    allowed=["CombiReading","ControlledReading"]
    internalheaderformat="Lag(hrs)"
    externalheadercode="Lag"

    def get_phenotype_list(self,record):
        assert record.__class__.__name__ in self.allowed
        output=record.get_lag()
        try:
            output=[float(output)]
        except Exception as e:
            output=[0]
        return output

class MaxSlopeCalc(PhenotypeCalculator):
    allowed=["CombiReading","ControlledReading"]
    internalheaderformat="MaxSlope(change OD/hr)"
    externalheadercode="MxSl"
    def get_header_list(self):
        if not hasattr(self,"headers"):
            self.headers=[self.internalheaderformat]
        return self.headers

    def get_phenotype_list(self,record):
        assert record.__class__.__name__ in self.allowed
        try:
            output=record.get_maxslope()
            output=[float(output)]
        except Exception as e:
            output=[0]
        return output

class MaxSlopeTimeCalc(PhenotypeCalculator):
    allowed=["CombiReading","ControlledReading"]
    internalheaderformat="MaxSlopeTime(hr)"
    externalheadercode="MxSlTm"
    def get_header_list(self):
        if not hasattr(self,"headers"):
            self.headers=[self.internalheaderformat]
        return self.headers

    def get_phenotype_list(self,record):
        assert record.__class__.__name__ in self.allowed
        try:
            record.get_inflection()
            output=[record.inflectionT]
        except Exception as e:
            output=[0]
        return output

class DifferentialTimeCalc(PhenotypeCalculator):
    allowed=["CombiReading","ControlledReading"]
    timefocus1=20.0
    timefocus2=47.0
    internalheaderformat="DifferentialTimeCalc({timefocus2:.1f}-{timefocus1:.1f}hrs (+-{plusminus:.1f}hrs))"
    externalheadercode="DT({timefocus2:.1f}-{timefocus1:.1f}hrs (+-{plusminus:.1f}hrs))"

    def find_timefocus(self,report=False):
        """
        Assume 47 hours and 25 hours timepoints both present and return difference
        """
        self.timefocus1=20.0
        self.timefocus2=47.0
        self.plusminus=self.experimentobject["plusminus"].value
        CF=self.experimentobject["combifile"]
        if report:
            TV=CF.timevalues()
            timeindices1=CF.pick_timeindices(timepoint=self.timefocus1,
                                             plus_minus=self.plusminus,
                                             report=False,
                                             generatefresh=True)
            timevalues1=[TV[i] for i in timeindices1]
            timeindices2=CF.pick_timeindices(timepoint=self.timefocus2,
                                             plus_minus=self.plusminus,
                                             report=False,
                                             generatefresh=True)
            timevalues2=[TV[i] for i in timeindices2]
            LOG.info("DifferentialTimeCalc getting mean({})-mean({})"
                     .format(','.join(["{:.1f}".format(t) for t in timevalues2]),
                             ','.join(["{:.1f}".format(t) for t in timevalues1])))

    def get_phenotype_list(self,record):
        """
        readingobject could be a reading, combireading or controlledreading
        """
        assert record.__class__.__name__ in self.allowed
        av1,nreadings1=record.average_about_time(timepoint=self.timefocus1,
                                                 plus_minus=self.plusminus,
                                                 report=False,
                                                 generatefresh=True)
        av2,nreadings2=record.average_about_time(timepoint=self.timefocus2,
                                                 plus_minus=self.plusminus,
                                                 report=False,
                                                 generatefresh=True)
        return [av2-av1]

class PrintedMassCalc(PhenotypeCalculator):
    internalheaderformat="PrintedMass"
    externalheadercode="PrMs"
    """printedmass from each reading"""

    def get_phenotype_list(self,record):
        """
        readingobject could be a reading, combireading or controlledreading
        """
        assert record.__class__.__name__ in self.allowed
        PM=float(record["platedmass"].value)
        return [PM]

class PrintedMassControlledCalc(PhenotypeCalculator):
    internalheaderformat="PrintedMassControlled"
    externalheadercode="PrMsCont"
    """
    subtracts the maximumchange recorded in the reading to take into account
    the following:
    A colony that tends to grow large but still has low platedmasses
    e.g. PM-MC = 0.001-3.0 = -2.999
    is more informative than
    a colony that tends to stay small and gives low platedmasses
    e.g. PM-MC = 0.001-0.5 = -0.499
    Whereas a colony that tends to grow large and gives big platedmasses
    e.g. PM-MC = 1.0-3.0 = -2.0
    is less informative than
    a colony that tends to stay small and still gives big platedmasses
    e.g. PM-MC = 1.0-0.5 = 0.5
    """
    def get_phenotype_list(self,record):
        """
        readingobject could be a reading, combireading or controlledreading
        """
        assert record.__class__.__name__ in self.allowed
        MC=float(record["maximumchange"])
        PM=float(record["platedmass"].value)
        return [PM-MC]

class ShrinkageCalc(PhenotypeCalculator):
    internalheaderformat="Shrinkage"
    externalheadercode="Shrnk"
    """
    Calculates any drop in readings from the initial value (printed mass)
    to the minimumwithoutagar value
    """
    def get_phenotype_list(self,record):
        assert record.__class__.__name__ in self.allowed
        try:
            PM=float(record["platedmass"].value)
            MWA=float(record["minimumwithoutagar"])
            return [PM-MWA]
        except:
            return [0]

class HalfPeakTimeCalc(PhenotypeCalculator):
    internalheaderformat="HalfPeakTime (hr)"
    externalheadercode="HlfPkTm"
    """
    The time at which the normalized measurements
    reach half their maximum value.
    """
    def get_phenotype_list(self,record):
        assert record.__class__.__name__ in self.allowed
        try:
            record.get_inflection()
            return [record["halfpeaktime"]]
        except:
            return [0]
#

#COMBIFILES ###################################################################
class CombiFileID(DBString):
    coltype=tbs.StringCol(20)
    regex=re.compile("^(?P<user>\D*)"
                     "(?P<experimentnumber>\d*)"
                     "(?P<fileletters>\D*)$")

    @classmethod
    def create_from_files(cls,*files,**_combidict):
        if _combidict:
            CD=_combidict
        else:
            CD=combidict(*files)
        if "fileletter" not in CD:
            LOG.error("No fileletters found for files {}"
                      .format(str([str(f) for f in files])))
            return None
        filelets=''.join(sorted(CD["fileletter"]))

        expids=CD["experimentid"]
        if len(expids)!=1:
            LOG.error("Different experimentids: {}".format(expids))
            return None
        expid=expids[0]

        trtmnts=CD["treatment"]
        if not len(trtmnts)==1:
            LOG.error("Multiple treatments ({}) for {}{}"
                      .format(trtmnts, expid, filelets))
            return None
        trtmnt=trtmnts[0]

        cfid="{}{}".format(expid,filelets)
        return cls(cfid)

class CombiFile(DBRecord,GraphicGenerator):
    tableclassstring="CombiFiles"
    slots=[CombiFileID,ExperimentID,PlateLayout,
           Treatment,IsSurvivor,
           NCurves,NMeasures,
           TimeSpan,TimeSeries,TempSeries,
           IsControl,AllProcessed,ErrorRecord]  

    defaultlookup="combifileid"
    coltype=tbs.StringCol(20)
    strict=True
    subrecordtables={}
    titleformat="{prefix}{combifileid} {platelayout} ({treatment}){suffix}"
    subfoldernameformat="{combifileid} '{platelayout}' ({note}) {treatment}"
    graphicsnamerootformat="{combifileid} {platelayout} ({treatment})"

    @classmethod
    def create_from_files(cls,*files,**combidct):
        save=combidct.pop("save",True)
        read=combidct.pop("read",True)
        if combidct:
            CD=combidct
        else:
            CD=combidict(*files)
        cfid=CombiFileID.create_from_files(*files,**CD)
        timestamp=min(CD.get("experimenttimestamp",[0]))
        if cfid:
            cf=cls(combifileid=cfid.value,
                   experimentid=CD["experimentid"][0],
                   platelayout=CD["platelayout"][0],
                   treatment=CD["treatment"][0],
                   issurvivor=CD["issurvivor"][0])
            cf.timestamp=timestamp
            cf.sourcefiles=files
            if save:
                self.save(read)
            elif read:
                cf.read(store=False)
            return cf

    def save(self,read=True):
        if self not in self._get_table():
            self.store(check=False)
            for f in self.yield_sourcefiles():
                f.update_atoms(combifile=self["combifileid"].value)
            if read:
                self.read(store=True)

    def get_subrecordtable(self):
        if self.dbasenameroot not in self.__class__.subrecordtables:
            rec=CombiReadings(self.dbasenameroot)
            self.subrecordtables[self.dbasenameroot]=rec
        return self.subrecordtables[self.dbasenameroot]

    def get_subrecordtype(self):
        return CombiReading

    def user(self):
        matches=[m.groupdict()
                 for m in CombiFileID.regex.finditer(self["combifileid"].value
                                                     )][0]
        if type(matches["user"])==str:
            return matches["user"]
        else:
            return None

    def timevalues(self):
        return self["timeseries"]._get_trimmed()
    xvalues=timevalues
    def get_coords(self):
        """
        It's slow to pull together a list of well coords (for plots)
        so only do it once
        """
        if not hasattr(self,"coords"):
            self.coords=self["plate"].get_coords()
        return self.coords

    def pick_timeindices(self,timepoint=16,plus_minus=0.5,report=True,
                         generatefresh=False):
        """
        To allow for files with subtly different timepoints to be compared,
        this function returns a tuple of n indices matching the timepoints
        plus and minus [plus_minus] inclusive.
        e.g.
        if time values =[0, 1.5, 3.0, 4.5, 6.0]
        pick_timeindices(3.0,1.5) returns (1,2,3)
        """
        if generatefresh or not hasattr(self,"lasttimeindices"):
            TV=self.timevalues()
            nearesttimepoint=TV[closest_index(TV,timepoint)]
            if float(nearesttimepoint)!=float(timepoint):
                if report:
                    LOG.warning("in {}, nearest timepoint to {} is {} "
                                "so using that"
                                .format(self.value,timepoint,nearesttimepoint))
                timepoint=nearesttimepoint
            timerange=(timepoint-plus_minus,timepoint+plus_minus)
            timepoints=[t for t in TV if timerange[0]<=t<=timerange[1]]
            if report:
                LOG.warning("in {}, only averaging from timepoints {}"
                            .format(self.value,timepoints))
            self.lasttimeindices=[TV.index(t) for t in timepoints]
        return self.lasttimeindices

    def tempvalues(self):
        return self["tempseries"]._get_trimmed()

    def maximumchange(self):
        return max([cr["maximumchange"] for cr in self.yield_records()])

    def controlledexperiment(self):
        return ControlledExperiments().get(self.value)

    def note(self,clip=20):
        allnotes=[]
        for sf in self.yield_sourcefiles():
            if sf is None:
                return ""
            nt=sf["note"].value
            if nt is not None:
                if nt not in allnotes:
                    allnotes.append(nt)
        return "; ".join(allnotes)[:clip]

    def timestamp(self):
        return max([cf["experimenttimestamp"].value
                    for cf in self.yield_sourcefiles()])

    def __contains__(self,fileID):
        if type(fileID)==str:
            return fileID in list(self._yield_sourcefileids())
        else:
            LOG.error("non-string input is Not Yet Implemented")

    def _yield_sourcefileids(self):
        matches=[m.groupdict()
                 for m in CombiFileID.regex.finditer(self["combifileid"].value
                                                     )][0]
        assert matches["user"]+matches["experimentnumber"]==self["experimentid"].value
        for fileletter in matches["fileletters"]:
            yield self["experimentid"].value+fileletter

    def yield_sourcefiles(self):
        if not hasattr(self,"sourcefiles"):
            if self.is_valid():
                fls=Files(self.dbasenameroot)
                self.sourcefiles=[]
                for fileid in self._yield_sourcefileids():
                    self.sourcefiles.append(fls.get(fileid))
        for sf in self.sourcefiles:
            yield sf
#
    def fix_timeoffsets(self,sourcefiles):
        """
        Why did I create this again?
        """
        if not sourcefiles:
            return sourcefiles
        if sourcefiles[0]["emptyreading"].value:
            startindex=1
        else:
            startindex=0

        for i,sf in enumerate(sourcefiles):
            if i==startindex:
                if sf["timeoffset"].value!=0.0:
                    sf.update_atoms(timeoffset=0.0)
                zerosecond=sf["experimenttimestamp"].value
            elif i>startindex:
                if not sf["emptyreading"].value:
                    if not sf["timeoffset"].is_valid():
                        ets=sf["experimenttimestamp"].value
                        change=ets-zerosecond
                        changeinhours=change/3600.0
                        rounded=round(changeinhours,2)
                        sf.update_atoms(timeoffset=rounded)
        return sourcefiles
        
    def read(self,store=True,overwrite=False):
        if self.has_been_read() and overwrite is False:
            LOG.debug("{} for {} already stored"
                      .format(self.get_subrecordtable().__class__.__name__,
                              self.value))
            return

        #cf=self.get_table()
        new_combireadings=[]
        sourcefiles=list(self.yield_sourcefiles())
        sourcefiles=self.fix_timeoffsets(sourcefiles)
        generators=[f.yield_records() for f in sourcefiles]
        sourcefileerrorrecords=[f["errorrecord"].value
                                for f in sourcefiles
                                if f["errorrecord"].is_valid()]
        sourcefileerrorrecords=ErrorRecord.splitter.join(sorted(set(sourcefileerrorrecords)))
        parallelreadings=izip(*generators)
        self.records=[]
        newtimepoints=[]
        newtemps=[]
        for sourcefile in sourcefiles:
                tms=sourcefile["timeseries"]
                if tms.is_valid():
                    newtimepoints+=tms._get_trimmed()
                tss=sourcefile["tempseries"]
                if tss.is_valid():
                    newtemps+=tss._get_trimmed()
        if len(newtimepoints)>2:
            tmspn=newtimepoints[-1]-newtimepoints[0]
        else:
            tmspn=None
        iscontr=False
        for readset in parallelreadings:
            pp=readset[0]["plateposition"]
            readinggroup=readset[0]["readinggroup"].value
            treatment=readset[0]["treatment"].value
            if treatment in IsControl.treatments:
                iscontr=True
            experimentid=readset[0]["experimentid"].value

            newmeasures=[]
            emptymeasures=[]
            errorrecords=[]
            for r in readset:
                em=r["emptymeasure"]
                if em.is_valid():
                    emptymeasures.append(em.value)
                mn=r["minimum"].value
                mss=r["measurements"]
                if mss.is_valid():
                    #dezero timeseries
                    newmeasures+=[m+mn for m in mss._get_trimmed()]
                er=r["errorrecord"].value
                if er not in errorrecords:
                    errorrecords.append(er)
            errorrecords=ErrorRecord.splitter.join(errorrecords)

            newmin=min(newmeasures)
            newzeroedmeasures=[m-newmin for m in newmeasures] #rezero timeseries
            recordtype=self.get_subrecordtype()
            output=recordtype(readingid="{}_{}"
                              .format(self.value,pp["well"].value),
                              combifile=self,
                              plateposition=pp,
                              well=pp["well"],
                              strain=pp["strain"],
                              isblank=pp["isblank"],
                              isborder=pp["isborder"],
                              readinggroup=readinggroup,
                              treatment=treatment,
                              emptymeasure=emptymeasures[0]
                              if emptymeasures else None,
                              platedmass=newmeasures[0]-emptymeasures[0]
                              if len(emptymeasures)==1 else None,
                              minimum=newmin,
                              measurements=newzeroedmeasures,
                              errorrecord=errorrecords)
            self.records.append(output)

        if store:
            self.update_atoms(ncurves=len(self.records),
                              nmeasures=len(newtimepoints),
                              timespan=tmspn,
                              timeseries=TimeSeries(newtimepoints),
                              tempseries=TempSeries(newtemps),
                              iscontrol=iscontr,
                              allprocessed=False,
                              errorrecord=sourcefileerrorrecords)
            self.get_subrecordtable().store_many_record_objects(self.records)
            LOG.info("created {} {} for {}"
                     .format(len(self.records),
                             self.get_subrecordtable().__class__.__name__,
                             self))
        return self.records
#
    def has_been_read(self):
        if not hasattr(self,"alreadyread"):
            query=self.get_subrecordtype()(combifile=self.value)
            self.alreadyread=query in self.get_subrecordtable()
        return self.alreadyread

    def yield_records(self,include_blanks=True):
        if not hasattr(self,"records"):
            tab=self.get_subrecordtable()
            self.records=tab.get(combifile=self["combifileid"].value)
        for result in self.records or []:
            if include_blanks is True:
                yield result
            else:
                if not result.is_blank():
                    yield result

    def sorted_readings(self):
        return sorted(self.yield_records(include_blanks=False))

    def timepoints_match(self,other):
        return self["timeseries"].value==other["timeseries"].value

    def is_control(self):
        return self["treatment"].is_control()

    def Xflag(self,query,warning=None,overwrite=False):
        """
        autodetects if query is a strain or a wellname, then applies warning
        to the errorrecord column of all matching readings
        """
        if warning is None:
            warning="unspecified warning"
        if query in Wells().get_values_of_atom("wellname"):
            querytype="well"
            if "_" not in query:
                query="{}_{}".format(self["capacity"],query)
        elif query in Strains():
            querytype="strain"
        else:
            LOG.error("{}.flag cannot identify type of query {}. "
                      "Should be wellname or strain."
                      .format(self.__class__.__name__,query))
            return False
        CR=CombiReadings()
        for result in CR.query_by_dictionary({"combifile":self.value,
                                              querytype:query}):
            finalwarning=warning
            if overwrite==False:
                er=result["errorrecord"]
                if er.is_valid():
                    finalwarning=ErrorRecord.splitter.join([er.value,
                                                            finalwarning])
            if finalwarning=="": finalwarning=None
            result.update_atoms(errorrecord=finalwarning)
            LOG.warning("CombiFile().flag() flagged {}"
                        .format(result))

    def find_control(self,check_timepoints=None,
                     report=False,
                     return_reverse=True):
        """
        Given a choice, will return controls in order of preference,
        with errorrecords counting against, and number of shared timepoints counting for.
        
        check_timepoints: None, or a float 0.0-1.0, or an int...
            if a float 0.0-1.0, then matching controls will only be kept if they have
             at least that proportion of timepoints/self_timepoints
            if an int, then at least that int of timepoints in common
        report: report variance in timepoints, fed to res.timevalues
        return_reverse: if True, & self is_control, returns the non-control matching this control.
        """
        results=list(self.yield_controls())
        if check_timepoints is not None:
            results2=[]
            for res in results:
                common_timepoints=self["timeseries"].intersection(res["timeseries"])
                if type(check_timepoints)==int:
                    if len(common_timepoints)>=check_timepoints:
                        results2.append(res)
                elif type(check_timepoints)==float:
                    if len(common_timepoints)/float(len(self["timeseries"]))>=check_timepoints:
                        results2.append(res)
            results=results2
        L=len(results)
        if L==0:
            idrider="no matches"
        elif L==1:
            idrider="{}".format(results[0]["combifileid"].value)
        elif L>1:
            idrider="{} matches".format(L)
        if report:
            LOG.warning("{}.find_control() found {} with same layout "
                        "& timepoints but treatment={}"
                        .format(str(self),idrider,control_treatment))
        return results

    def has_control(self,**kwargs):
        if self.find_control(**kwargs):
            return True
        return False

    def find_duplicate(self,check_timepoints=None,report=True):
        """
        finds experiments with the same layout and treatment
        """
        pass

    def yield_combireadings_by_background(self):
        """
        Yields two dicts, e.g. {"AS":[combireading1, combireading3...],
                                "AE":[combireading2, combireading4...]},
                                
                                {"AS":"FS001-096",
                                 "AE":"FS101-196"}
        """
        if not hasattr(self,"letset_combireadings_dict"):
            self.letset_strainrange_dict={}
            self.letset_combireadings_dict={}
            for cr in self.yield_records():
                bg=cr["background"].value
                st=cr["strain"].value
                if bg:
                    if bg not in self.letset_strainrange_dict:
                        self.letset_strainrange_dict[bg]=[st]
                        self.letset_combireadings_dict[bg]=[cr]
                    else:
                        if st not in self.letset_strainrange_dict[bg]:
                            self.letset_strainrange_dict[bg]+=[st]
                        self.letset_combireadings_dict[bg]+=[cr]
            for k,v in self.letset_strainrange_dict.items():
                v.sort()
                try:
                    strainrange="{}{}-{}".format(v[0][:2],v[0][2:],v[-1][2:])
                except:
                    strainrange="unknownstrainrange"
                self.letset_strainrange_dict[k]=strainrange
        return self.letset_combireadings_dict, self.letset_strainrange_dict

    def yield_combireadings_by_strain(self):
        if not hasattr(self,"combireadings_by_strain_dict"):
            CSD={}
            for rec in self.yield_records():
                if rec["strain"].value not in CSD:
                    CSD[rec["strain"].value]=[rec]
                else:
                    CSD[rec["strain"].value].append(rec)
            self.combireadings_by_strain_dict=CSD
        return self.combireadings_by_strain_dict

    def sample(self):
        for record in self.yield_records():
            return record

    def output_to_txtOLD(self,
                      prefix="CombiFile",
                      extension="tab",
                      delimiter="\t",
                      timespacer="\t",
                      ask=False,
                      replace=False,
                      **kwargs):
        kwargs.update(locals().copy())
        del kwargs["self"]
        filepath=self.get_graphicspath(**kwargs)
        if os.path.exists(filepath):
            if ask:
                answer=raw_input("{} already exists. Overwrite it?"
                                 .format(filepath))
                if not answer.lower().startswith("y"):
                    return
            elif not replace:
                LOG.info("{} already exists".format(filepath))
                return
        prepare_path(os.path.dirname(filepath))
        with open(filepath,"wb") as fileob:
            writer=csv.writer(fileob,
                              delimiter=delimiter,
                              quoting=csv.QUOTE_MINIMAL)
            for i,rec in enumerate(self.yield_records()):
                if i==0:
                    row=rec._get_txt_headers(spacer=timespacer,
                                                 trim=True)
                    writer.writerow(row)
                row=rec._get_txt_row(spacer=timespacer,trim=True)
                writer.writerow(row)
            fileob.close()
            LOG.info("{} created".format(filepath))
        return filepath

    def output_to_txt(self,
                      prefix="CombiFile",
                      extension="tab",
                      delimiter="\t",
                      timespacer="\t",
                      ask=False,
                      replace=False,
                      **kwargs):
        """
        An improvement over the original method- yields measurements minus agar
        and also includes lag and slope values if available.
        """
        kwargs.update(locals().copy())
        del kwargs["self"]

        headers1=['readingid', 'plateposition', 'strain', 'ignore',
                  'isblank', 'isborder', 'readinggroup', 'treatment', 'agar absorbance',
                  'minimumwithoutagar', 'maximumwithoutagar', 'maximumchange',
                  'maximumslope','lag']
        headersLU=['readingid', 'plateposition', 'strain', 'ignore',
                  'isblank', 'isborder', 'readinggroup', 'treatment', 'emptymeasure',
                  'minimumwithoutagar', 'maximumwithoutagar', 'maximumchange',
                  'get_maxslope','get_lag']
        headers2=["{:.4f}".format(t) for t in self.timevalues()]
        headers=headers1+['measurementsminusagar']+headers2

        filepath=self.get_graphicspath(**kwargs)
        if os.path.exists(filepath):
            if ask:
                answer=raw_input("{} already exists. Overwrite it?"
                                 .format(filepath))
                if not answer.lower().startswith("y"):
                    return
            elif not replace:
                LOG.info("{} already exists".format(filepath))
                return
        prepare_path(os.path.dirname(filepath))
        with open(filepath,"wb") as fileob:
            writer=csv.writer(fileob,
                              delimiter=delimiter,
                              quoting=csv.QUOTE_MINIMAL)
            for i,rec in enumerate(self.yield_records()):
                if i==0:
                    row=headers
                    writer.writerow(row)
                rowA=[str(ATOMORNOT(rec[h])) for h in headersLU]
                rowB=[str(m) for m in rec["rawmeasuredvaluesminusagar"]]
                row=rowA+[""]+rowB
                writer.writerow(row)
            fileob.close()
            LOG.info("{} created".format(filepath))
        return filepath

    def display(self,label="strain",delimiter="\t",printit=True):
        platepositions=self.yield_records()
        colheaders=[""]+list(self["plate"].yield_colnumbers())
        rowheaders=list(self["plate"].yield_rowletters())
        rowlength=len(colheaders)-1
        data=[pp[label].value for pp in platepositions]
        output=[delimiter.join([str(ch) for ch in colheaders])]

        i=0
        for rowheader in rowheaders:
            output.append(delimiter.join([rowheader]+data[i:i+rowlength]))
            i+=rowlength
        output="\n".join(output)
        if printit:
            print output
        else:
            return output

    def draw(self,**kwargs):
        try:
            return FinalGrowth(self,**kwargs)
        except Exception as e:
            LOG.info("couldn't draw {}: {}".format(self.value,e))
            return False

    def draw_empty(self,**kwargs):
        try:
            return EmptyPlateView(self,**kwargs)
        except Exception as e:
            LOG.info("couldn't draw_empty {}: {}".format(self.value,e))
            return False

    def draw_printed(self,**kwargs):
        try:
            return PrintingQuality(self,**kwargs)
        except Exception as e:
            LOG.info("couldn't draw_plated {}: {}".format(self.value,e))
            return False

    def draw_layout(self,**kwargs):
        try:
            return LayoutView(self,**kwargs)
        except Exception as e:
            LOG.info("couldn't draw_layout {} for {}: {}"
                     .format(self["platelayout"].value,
                             self.value,
                             e))
            return False

    def animate(self,**kwargs):
        if self["timespan"].is_sufficient(fortext="animate"):
            try:
                return Animation_Temp(self,**kwargs)
            except Exception as e:
                pyplt.close('all')
                LOG.info("couldn't animate {}: {}".format(self.value,e))
                return False

    def plot(self,**kwargs):
        if self["timespan"].is_sufficient(fortext="plot"):
            try:
                return CurvesWithoutAgar_PrintedMass(self,**kwargs)
            except Exception as e:
                LOG.info("couldn't plot {}: {}".format(self.value,e))
                return False
    
    def plot_normal(self,**kwargs):
        if self["timespan"].is_sufficient(fortext="plot_normal"):
            try:
                return CurvesNormalized_PrintedMass(self,**kwargs)
            except Exception as e:
                LOG.info("couldn't plot_normal {}: {}".format(self.value,e))
                return False

    def plot_grouped(self,**kwargs):
        if self["timespan"].is_sufficient(fortext="plot_grouped"):
            try:
                return CurvesWithoutAgar_Groups(self,**kwargs)
            except Exception as e:
                LOG.info("couldn't plot_grouped {}: {}".format(self.value,e))
                return False

    def plot_replicates(self,**kwargs):
        if self["timespan"].is_sufficient(fortext="plot_replicates"):
            try:
                return ReplicatePlots(self,**kwargs)
            except Exception as e:
                LOG.info("couldn't plot_replicates {}: {}".format(self.value,e))
                return False

    def histogram(self,**kwargs):
        if self["timespan"].is_sufficient(fortext="histogram"):
            try:
                return Histogram_MaxWithoutAgar(self,**kwargs)
            except Exception as e:
                LOG.info("couldn't histogram {}: {}".format(self.value,e))
                return False

    def scatterplot(self,**kwargs):
        if self["timespan"].is_sufficient(fortext="scatterplot"):
            try:
                return Scatterplot_PrintedMass_Lag(self,**kwargs)
            except Exception as e:
                LOG.info("couldn't scatterplot {}: {}".format(self.value,e))
                return False

    def illustrate(self,**kwargs):
        overwrite=kwargs.pop("overwrite",False)
        try:
            TV=self["timevalues"]
            assert TV
        except:
            LOG.error("unable to get valid time values for {}"
                      .format(self.value))
            return
        if overwrite or not self["allprocessed"].value:
            self.open_plots_folder()
            vislookup=Locations().configdict["combifilevisualizations"]
            usr=self.user()
            if usr in vislookup:
                vislist=vislookup[usr]
            else:
                vislist=vislookup["!default"]
            faillog=[]
            for i,visclassname in enumerate(vislist):
                visclass=globals().get(visclassname,None)
                if visclass is None:
                    LOG.error("couldn't get visclass {}".format(visclassname))
                    faillog.append(visclassname)
                else:
                    try:
                        output=visclass(self,number=i+1,**kwargs)
                    except Exception as e:
                        LOG.error("couldn't visualize {} for {}: {} {}"
                                  .format(visclassname,self.value,e,get_traceback()))
                        faillog.append(visclassname)
            if faillog:
                LOG.warning("couldn't create some visualizations: {}"
                            .format(", ".join(faillog)))
            else:
                self.update_atoms(allprocessed=True)
            PSFP=self.get_plotssubfolderpath()
            if os.path.exists(PSFP):
                CD=Locations().get_userpath()
                CDname=os.path.split(CD)[-1]
                lnkname=os.path.join(PSFP,"~Data files_"+CDname+".lnk")
                create_Windows_shortcut(targetpath=CD,
                                        locationpath=lnkname)
            try:
                pyplt.close('all')
            except Exception as e:
                LOG.error("couldn't close pyplt to free up memory because {} {}"
                          .format(e,get_traceback()))
            
        else:
            LOG.info("{} already fully illustrated"
                     .format(self.value))

    def illustrateOLD(self,**kwargs):
        overwrite=kwargs.pop("overwrite",False)
        try:
            TV=self["timevalues"]
            assert TV
        except:
            LOG.error("unable to get valid time values for {}"
                      .format(self.value))
            return
        if overwrite or not self["allprocessed"].value:
            self.open_plots_folder()
            allplots=[self.draw_empty(**kwargs),
                      #self.draw_layout(**kwargs),
                      self.draw_plated(**kwargs),
                      self.draw(**kwargs),
                      self.plot(**kwargs),
                      self.plot_normal(**kwargs),
                      self.plot_grouped(**kwargs),
                      self.histogram(**kwargs),
                      self.scatterplot(**kwargs),
                      self.plot_replicates(**kwargs),
                      self.animate(**kwargs)]#,
            if False in allplots:
                LOG.warning("couldn't create all plots: {}"
                            .format(str(allplots)))
            else:
                self.update_atoms(allprocessed=True)
            PSFP=self.get_plotssubfolderpath()
            if os.path.exists(PSFP):
                CD=Locations().get_userpath()
                CDname=os.path.split(CD)[-1]
                lnkname=os.path.join(PSFP,"~Data files_"+CDname+".lnk")
                create_Windows_shortcut(targetpath=CD,
                                        locationpath=lnkname)
            try:
                pyplt.close('all')
            except Exception as e:
                LOG.error("couldn't close pyplt to free up memory because {} {}"
                          .format(e,get_traceback()))
            
        else:
            LOG.info("{} already fully illustrated"
                     .format(self.value))

    def plot_qtls(self,**kwargs):
        CE=ControlledExperiments(self.dbasenameroot)
        cexes=CE.query_by_kwargs(combifile=self.value)
        if cexes:
            xs,ys,cs=[],[],[]
            for cex in cexes:
                for FS in cex.yield_qtlsets():
                    y,x=FS.generate_xys()
                    if x and y:
                        xs.append(x)
                        ys.append(y)
                        cs.append(FS.genotypegroup)
                if xs:
                    title="{} ({}).{}".format(self.value,
                                              self["treatment"].value,
                                              Locations.graphicstype)
                    savepath=os.path.join(Locations().rootdirectory,
                                          "rQTL output",
                                          "By CombiFile",
                                          title)
                    savepath=os.path.normpath(savepath)
                    CurvePlot(timevalues=ys, #xvalues
                              measurements=xs, #yvalues
                              colorvalues=cs,
                              ybounds=(0,15),
                              xbounds=(0,12071326),
                              yaxislabel="Peak LOD",
                              xgridlines=get_chrcumulative().values(),
                              xaxislabel="bp",
                              title=title,
                              savepath=savepath,
                              show=False)

    def analyze(self,**kwargs):
        export=kwargs.setdefault("export",True)
        rqtl=kwargs.setdefault("rqtl",True)
        illustrate=kwargs.setdefault("illustrate",True)
        if export:
            try:
                self.output_to_txt(**kwargs)
            except:
                LOG.error("FAILED TO OUTPUT_TO_TXT {}"
                          .format(self.value))
        if rqtl:
            try:
                self.output_to_rQTL(**kwargs)
            except:
                LOG.error("FAILED TO OUTPUT_TO_rQTL {}"
                          .format(self.value))
        if illustrate:
            self.illustrate(**kwargs)

    def yield_measuresets(self):
        """
        Used by compare function. Sorts records 
        """
        straindict={}
        for cr in self.yield_records():
            if cr["strain"].value not in straindict:
                straindict[cr["strain"].value]=[cr["measuredvalues"]]
            else:
                straindict[cr["strain"].value].append(cr["measuredvalues"])
        for st in straindict:
            yield (st,zip(self["timevalues"],zip(*straindict[st])))

    def yield_controls(self):
        if self.is_control():
            return
        controlCFs=CombiFiles("Controls")
        userCFs=CombiFiles(self.dbasenameroot)
        for control in Treatment.controls:
            #Gather controls from CombiFiles("Controls")
            query=CombiFile(platelayout=self["platelayout"],
                            treatment=control,
                            dbasenameroot=controlCFs.dbasenameroot)
            result=controlCFs.query_by_record_object(query)
            for r in result:
                yield r
            foundids=[c.value for c in result]
            #Add any controls from user CombiFiles() not in above
            query=CombiFile(platelayout=self["platelayout"],
                            treatment=control,
                            dbasenameroot=userCFs.dbasenameroot)
            result=userCFs.query_by_record_object(query)
            for r in result:
                if r.value not in foundids:
                    yield r

    def return_scored_controls(self,report=True):
        if self.is_control():
            return False
        else:
            results=self.yield_controls()
        if not results:
            return False

        scoredresults=[]
        for res in results:
            common_timepoints=self["timeseries"].intersection(res["timeseries"])
            scoredresults.append((-len(common_timepoints),res))
        scoredresults.sort()
        results=[r for s,r in scoredresults]
        
        L=len(results)
        if L==0:
            idrider="no controls"
        elif L==1:
            idrider="1 control: {}".format(results[0]["combifileid"].value)
        elif L>1:
            idrider="{} controls".format(L)
        if report:
            LOG.info("found {} for {}"
                     .format(idrider,str(self)))
        return results

    def lock(self):
        self.update_atoms(allprocessed=True)

    def unlock(self):
        self.update_atoms(allprocessed=False)

    def _delete_also(self):
        for f in self.yield_sourcefiles():
            if f is None:
                return
            try:
                LOG.info("Deleting connection to combifile {} ({})"
                         "in File {} ({})"
                         .format(self.value,
                                 self.dbasenameroot,
                                 f.value,
                                 f.dbasenameroot))
                f.update_atoms(combifile=None)
            except Exception as e:
                LOG.error("Can't delete {} from {} sourcefiles because {} {}"
                          .format(f,str(self),e,get_traceback()))

    def open_plots_folder(self,create_shortcut=True):
        sfname=self.get_subfoldername()
        folderpath=os.path.join(Locations().get_plotspath(),
                                sfname)
        open_on_Windows(folderpath)
        if create_shortcut:
            create_Windows_shortcut(targetpath=folderpath,
                                    locationpath=os.path.join(Locations().get_userpath(),
                                                              "~"+sfname+".lnk"))

class CombiFiles(DBTable,InMemory):
    _shared_state={}
    tablepath="/combifiles"
    recordclass=CombiFile

    def create(self,sourcelist,*args,**kwargs):
        """
        sourcelist should a file object or list thereof, such as might be returned
        by Files().get()
        """
        kwargs.setdefault("save",True)
        kwargs.setdefault("read",True)
        if sourcelist is None:
            return None
        if type(sourcelist)==list:
            files=sourcelist
        elif type(sourcelist)==File:
            files=[sourcelist]
        output=[]
        if len(files)<2:
            return
        if files:
            #first split into survivors and nonsurvivors and produce a different
            #combifile for each 
            nonsurvivor=[f for f in files if f["issurvivor"].value==False]
            survivor=[f for f in files if f["issurvivor"].value==True]
            for issurv,fileset in zip([False,True],[nonsurvivor,survivor]):
                if len(fileset)>0:
                    #Check to see if fileset has multiple layouts, and further split
                    #resulting combifiles accordingly
                    subfilesets={}
                    layouts={}
                    for f in fileset:
                        pl=f["platelayout"]
                        layoutname=pl.value
                        if layoutname not in subfilesets:
                            subfilesets[layoutname]=[f]
                            layouts[layoutname]=pl
                        else:
                            subfilesets[layoutname].append(f)
                    for loname,subfileset in subfilesets.items():
                        fileletstosort=[f["fileletter"].value
                                        for f in subfileset]
                        fileletstosort.sort()
                        filelets=''.join(fileletstosort)

                        expids=list(set([f["experimentid"].value
                                         for f in subfileset]))
                        assert len(expids)==1
                        expid=expids[0]

                        trtmnts=list(set([f["treatment"].value
                                          for f in subfileset]))
                        if not len(trtmnts)==1:
                            LOG.critical("multiple treatments ({}) for {}{}"
                                         .format(trtmnts, expid, filelets))
                            sys.exit()
                        trtmnt=trtmnts[0]

                        cfid="{}{}".format(expid,filelets)
                        cf=self.recordclass(combifileid=cfid,
                                            experimentid=expid,
                                            platelayout=layouts[loname],
                                            treatment=trtmnt,
                                            issurvivor=issurv,
                                            dbasenameroot=self.dbasenameroot)
                        output.append(cf)
                        if kwargs["save"]:
                            if cf not in self:
                                cf.store(check=False)
                                for f in subfileset:
                                    f.update_atoms(combifile=cfid)
                        if kwargs["read"]:
                            cf.read(store=kwargs["save"])
        return output

    def update(self,**kwargs):
        """
        
        """
        kwargs.setdefault("overwrite",False)
        FLS=Files()
        #tostore=[]
        LOG.info("READING ALL COMBIFILES")
        for expid in FLS.get_values_of_atom("experimentid"):
            files=FLS.query_by_dictionary({"experimentid":expid})
            if files:
                if not kwargs["overwrite"]:
                    #filter out files with combifile already assigned
                    files = [f for f in files
                             if not f["combifile"].is_valid()]
                if files:
                    LOG.info("found {} files not yet in a combifile: {}"
                             .format(len(files),tuple([f.value for f in files])))
                    self.create(files,**kwargs)
                    self.backup_to_All()

    def total(self):
        return sum([p["ncurves"].value for p in self])

    def analyze(self,**kwargs):
        export=kwargs.setdefault("export",True)
        rqtl=kwargs.setdefault("rqtl",False)
        illustrate=kwargs.setdefault("illustrate",True)
        for cf in self:
            cf.analyze(**kwargs)

    def summary_by_treatment(self):
        pass

    def lock(self):
        for i in self:
            i.lock()

    def unlock(self):
        for i in self:
            i.unlock()

    def backup_to_All(self):
        if self.dbasenameroot=="All":
            return None
        allcombifiles=CombiFiles("All")
        for cf in self:
            if cf not in allcombifiles:
                LOG.info("About to copy {} to 'All'".format(cf.value))
                copydatato(cf["combifileid"].value,
                           "All",
                           datafiles='copy',
                           plotfiles='shortcut',
                           dbaseobs='copy',
                           report=True)

#

#CONTROLLED EXPERIMENTS #######################################################
class ControlledExperimentID(DBString):
    coltype=tbs.StringCol(60)
    shortheader="cExID"
    colclip=6

    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            if rec["combifile"].is_valid() and rec["controlfileid"].is_valid():
                self.set_value("{}_{}".format(rec["combifile"].value,
                                              rec["controlfileid"].value))
        return self.value

class ControlFileID(CombiFileID):
    coltype=tbs.StringCol(30)
    shortheader="cflID"
    colclip=8

class TimeFocus(DBFloat32):
    """
    Being the focal timepoint used for ratio calculations,
    plus or minus PlusMinus hours
    """
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            ST=rec.get_source_combifile().timevalues()
            CT=rec.get_control_combifile().timevalues()
            PM=rec["plusminus"].value
            self.set_value(self.pick_best_timefocus(ST,CT,PM))
        return self.value

    def pick_best_timefocus(self,T1,T2,plusminus=0.5):
        """
        """
        minmax=min(max(T1),max(T2))
        nearest1=T1[closest_index(T1,minmax)]
        nearest2=T2[closest_index(T2,minmax)]
        middle=(nearest1+nearest2)/2.0
        return middle-plusminus

class PlusMinus(DBFloat32):
    """
    see TimeFocus above
    """
    pass

class ControlledExperiment(CombiFile,GraphicGenerator):
    tableclassstring="ControlledExperiments"
    slots=[ControlledExperimentID,CombiFile,ControlFileID,
           ExperimentID,PlateLayout,
           Treatment,IsSurvivor,NMeasures,NCurves,
           TimeSpan,TimeSeries,TempSeries,
           TimeFocus,PlusMinus,AllProcessed]

    defaultlookup="controlledexperimentid"
    coltype=tbs.StringCol(60)
    shortheader="conEx"
    colclip=6
    strict=True
    subrecordtables={}
    control_treatments=["YPD","YPD 30C"]
    titleformat="{prefix}{controlledexperimentid} {platelayout} ({treatment}){suffix}"
    graphicsnamerootformat="{controlledexperimentid} {platelayout} ({treatment})"

    def get_subrecordtable(self):
        if self.dbasenameroot not in self.__class__.subrecordtables:
            rec=ControlledReadings(self.dbasenameroot)
            self.subrecordtables[self.dbasenameroot]=rec
        return self.subrecordtables[self.dbasenameroot]

    def get_subrecordtype(self):
        return ControlledReading

    def get_source_combifile(self):
        if not hasattr(self,"source_combifile"):
            self.source_combifile=self["combifile"]
        return self.source_combifile

    def get_control_combifile(self):
        if not hasattr(self,"control_combifile"):
            controlCFs=CombiFiles("Controls")
            userCFs=CombiFiles(self.dbasenameroot)
            lookup=self["controlfileid"].value
            results=controlCFs.query_by_kwargs(combifileid=lookup)
            if not results:
                results=userCFs.query_by_kwargs(combifileid=lookup)
            if not results:
                LOG.error("can't get control combifile {}".format(lookup))
                return None
            elif len(results)!=1:
                LOG.error("{} control combifiles called {}".format(len(results),
                                                                   lookup))
                return None
            else:
                self.control_combifile=results[0]
        return self.control_combifile

    def get_focus_indices(self):
        if not hasattr(self,"focus_indices"):
            if not self["timefocus"].is_valid():
                self["timefocus"].calculate()
            
            TF,PM=self["timefocus"].value,self["plusminus"].value
            S=self.get_source_combifile().timevalues()
            C=self.get_control_combifile().timevalues()

            if hasattr(self,"treatmenttimepoints"):
                self.focus_indices=(([S.index(t) for t in self.treatmenttimepoints]),
                                    ([C.index(t) for t in self.controltimepoints]))
            else:
                self.focus_indices=(get_indices_around(S,TF,PM),
                                    get_indices_around(C,TF,PM))
        return self.focus_indices

    def get_source_timefoci(self):
        if not hasattr(self,"source_timefoci"):
            SI,CI=self.get_focus_indices()
            ST=self.get_source_combifile().timevalues()
            self.source_timefoci=indices_to_values(ST,SI)
        return self.source_timefoci

    def get_control_timefoci(self):
        if not hasattr(self,"control_timefoci"):
            SI,CI=self.get_focus_indices()
            CT=self.get_control_combifile().timevalues()
            self.control_timefoci=indices_to_values(CT,CI)
        return self.control_timefoci

    def has_been_read(self):
        if not hasattr(self,"alreadyread"):
            query=self.get_subrecordtype()(combifile=self.value)
            self.alreadyread=query in self.get_subrecordtable()
        return self.alreadyread

    @classmethod
    def create_from_combifiles(cls,
                               treatmentcombifile,
                               controlcombifile,
                               rounder="{:.4f}",
                               timefocus=None,
                               plusminus=0.5,
                               treatmenttimepoints=None,
                               controltimepoints=None,
                               read=True,
                               store=True,
                               report=True):
        if type(treatmentcombifile)==str:
            CF=CombiFiles()[treatmentcombifile]
        else:
            CF=treatmentcombifile
        if type(controlcombifile)==str:
            CN=CombiFiles("Controls")[controlcombifile]
        else:
            CN=controlcombifile
        
        if not CF:
            LOG.error("No treatmentcombifile {}".format(treatmentcombifile))
            return None
        if not CN:
            LOG.error("No controlcombifile {}".format(controlcombifile ))
            return None
        
        query=ControlledExperiment(combifile=CF,
                                   controlfileid=CN.value,
                                   experimentid=CF["experimentid"])
        query["controlledexperimentid"].calculate()
        CEXID=query["controlledexperimentid"].value
        if query in query._get_table():
            LOG.error("already created {}"
                      .format(CEXID))
            return False

        CFts=CF["timeseries"]
        common_indices=CFts.intersection_indices(CN["timeseries"],
                                                 rounder=rounder)
        combined_timepoints=CFts.intersection(indices=common_indices,
                                              as_dbseries=False)

        if not combined_timepoints:
            LOG.error("No combined timepoints for {}".format(CEXID))
            return None

        tspn=combined_timepoints[-1] - combined_timepoints[0]
        CFtmps=CF["tempseries"]
        combined_temppoints=CFtmps.intersection(indices=common_indices,
                                                as_dbseries=False)
        ct_rounded=[rounder.format(v) for v in combined_timepoints]

        #CFmeasuresets=sorted(CF.yield_measuresets())
        #CNmeasuresets=dict(CN.yield_measuresets())

        ce=ControlledExperiment(controlledexperimentid=CEXID,
                                combifile=CF,
                                controlfileid=CN.value,
                                experimentid=CF["experimentid"],
                                platelayout=CF["platelayout"],
                                treatment=CF["treatment"],
                                issurvivor=CF["issurvivor"],
                                nmeasures=len(combined_timepoints),
                                ncurves=CF["ncurves"].value,
                                timespan=tspn,
                                timeseries=combined_timepoints,
                                tempseries=combined_temppoints,
                                plusminus=plusminus)

        if timefocus:
            ce["timefocus"].set_value(timefocus)
        else:
            ce["timefocus"].calculate(plusminus=plusminus)

        if not treatmenttimepoints:
            SI,CI=ce.get_focus_indices()
            ce.treatmenttimepoints=ce.get_source_timefoci()
            ce.controltimepoints=ce.get_control_timefoci()
        else:
            ce.treatmenttimepoints=treatmenttimepoints
            ce.controltimepoints=controltimepoints

        if report:
            LOG.info("ControlledExperiment {} is comparing timepoints "
                     "{} and {}".format(ce["controlledexperimentid"].value,
                                        ce.treatmenttimepoints,
                                        ce.controltimepoints))
        if read:
            #print "_"*40
            #ce.scrutinize()
            #print "*"*40
            ce.read(store=store) #stores readings
        if store:
            ce.store() #stores ControlledExperiment
        return ce
    
    def read(self,store=True):
        if not self.has_been_read():
            SCF=self.get_source_combifile()
            CCF=self.get_control_combifile()
            if not SCF:
                LOG.error("controlledexperiment {} returns no source combifile"
                          .format(self.value))
                return None
            if not CCF:
                LOG.error("controlledexperiment {} returns no control combifile"
                          .format(self.value))
                return None

            self.records=[]
            Srec=list(SCF.yield_records())
            Crec=list(CCF.yield_records())
            if not Srec:
                LOG.critical("yield_records yielded nothing for source record {}"
                             .format(SCF.value))
                sys.exit()
            if not Crec:
                LOG.critical("yield_records yielded nothing for control record {}"
                             .format(CCF.value))
                sys.exit()
            
            for SR,CR in zip(Srec,Crec):
                #assert SR["strain"]==CR["strain"]
                #assert SR["wellname"]==CR["wellname"]
                st=str(SR["strain"].value)
                srid=SR["readingid"].value
                crid=CR["readingid"].value
                crdid="{}__{}".format(srid,crid)
                #sav=SR.average_of_timepoints_plus_minimum_minus_agar()
                #cav=CR.average_of_timepoints_plus_minimum_minus_agar()
                cr=ControlledReading(controlledreadingid=crdid,
                                     controlledexperiment=self,
                                     combireading=SR,
                                     controlreadingid=crid,
                                     treatment=self["treatment"].value,
                                     strain=st,
                                     errorrecord=SR["errorrecord"]+CR["errorrecord"])
                cr.calculate_all()
                self.records.append(cr)
            if store:
                ControlledReadings().store_many_record_objects(self.records)
                self.update_atoms(ncurves=len(self.records))
            return self.records
        else:
            return False

    def has_been_read(self):
        if not hasattr(self,"alreadyread"):
            query=self.get_subrecordtype()(controlledexperiment=self.value)
            self.alreadyread=query in self.get_subrecordtable()
        return self.alreadyread

    def yield_records(self,read=False):
        if not hasattr(self,"records"):
            tab=self.get_subrecordtable()
            self.records=tab.get(controlledexperiment=self["controlledexperimentid"].value)
        for result in self.records or []:
            yield result

    def yield_qtls(self):
        Q=QTLs(self.dbasenameroot)
        if len(Q)==0:
            LOG.error("No QTLs entered into QTLs({})".format(self.dbasenameroot))
        else:
            allqtls=Q.query_by_kwargs(controlledexperiment=self.value)
            for qtl in allqtls:
                yield qtl

    def yield_qtlsets(self):
            splitter=defaultdict(list)
            for q in self.yield_qtls():
                gg=q["genotypegroup"].value
                splitter[gg].append(q)
            if splitter:
                for gg,qset in splitter.items():
                    yield FeatureSet(qset,
                                     treatment=self["treatment"].value,
                                     controlledexperiment=self,
                                     genotypegroup=gg)

    def split_records_by_rQTLgroup(self):
        if not hasattr(self,"records_by_rQTLgroup"):
            temp=defaultdict(list)
            for cr in self.yield_records():
                rqg=cr["rqtlgroup"].value
                temp[rqg].append(cr)
            #ADD ANY BLANKS TO EVERY OTHER GROUP:
            if "" in temp:
                blanks=temp.pop("")
                for k,v in temp.items():
                    v+=blanks
            self.records_by_rQTLgroup=temp
        return self.records_by_rQTLgroup

    def get_subfoldername(self,**kwargs):
        return self["combifile"].get_subfoldername()

    def draw_ratios(self,**kwargs):
        if self["timespan"].is_sufficient(fortext="draw_ratios"):
            try:
                return ControlledRatios(self,**kwargs)
            except Exception as e:
                LOG.info("couldn't draw_ratios {}: {} {}"
                         .format(self.value,e,get_traceback()))
                return False

    def plot(self,**kwargs):
        self["combifile"].plot(**kwargs)
        self.get_control_combifile().plot(**kwargs)

    def plot_qtls(self,**kwargs):
        xs,ys,cs=[],[],[]
        for FS in self.yield_qtlsets():
            print self
            print len(FS)
            y,x=FS.generate_xys()
            if x and y:
                xs.append(x)
                ys.append(y)
                cs.append(FS.genotypegroup)
        if xs:
            title="{} ({}).{}".format(self.value,
                                      self["treatment"].value,
                                      Locations.graphicstype)
            savepath=os.path.join(Locations().rootdirectory,
                                  "rQTL output",
                                  "By ControlledExperiment",
                                  title)
            savepath=os.path.normpath(savepath)
            CurvePlot(timevalues=ys, #xvalues
                      measurements=xs, #yvalues
                      colorvalues=cs,
                      ybounds=(0,15),
                      xbounds=(0,12071326),
                      yaxislabel="Peak LOD",
                      xgridlines=get_chrcumulative().values(),
                      xaxislabel="bp",
                      title=title,
                      savepath=savepath,
                      show=False)

    def output_to_rQTL(self,*args,**kwargs):
        """
        args are one or more PhenotypeCalculators, each one generating a
        column in the resulting rQTL file

        If kwarg averagereplicates is True, then this effect is applied last
        """
        kwargs.setdefault("skipnoalleles",False)
        kwargs.setdefault("remove_ignore",True)
        kwargs.setdefault("combine_replicates",False)
        return rQTLinputReader.create_from_object(self,*args,**kwargs)

    def analyze(self,**kwargs):
        if not self["allprocessed"].value:
            allactions=[self.draw_ratios(**kwargs),
                        #self.histogram(**kwargs),
                        self.output_to_rQTL(**kwargs)]
            if False in allactions:
                LOG.warning("couldn't create all plots: {}"
                            .format(str(allactions)))
            else:
                self.update_atoms(allprocessed=True)
                
            self["combifile"].open_plots_folder()

    def lock(self):
        self.update_atoms(allprocessed=True)

    def unlock(self):
        self.update_atoms(allprocessed=False)

    def _delete_also(self):
        return

    def diagnostics(self):
        warnings=[]
        def WARN(message):
            warnings.append(message)
            LOG.warning(message)
        #check key parameters have been stored
        if not self["timeseries"].is_valid(): 
            WARN("{} has no timeseries"
                 .format(self.value))
        
        CF=CombiFiles(self.dbasenameroot)
        CFid=self["combifile"].value
        if CFid not in CF.get_values_of_atom("combifileid"):
            WARN("{} is not in CombiFiles({})"
                 .format(CFid,self.dbasenameroot))
        CN=CombiFiles("Controls")
        CNid=self["controlfileid"].value
        if CNid not in CN.get_values_of_atom("combifileid"):
            WARN("{} is not in CombiFiles('Controls')"
                 .format(CNid))
        
        ncurves=self["ncurves"].value
        if hasattr(self,"records"): del self.records
        recs=list(self.yield_records())
        if ncurves!=len(recs):
            WARN("ControlledExperiment({}) ncurves={} but "
                 "has {} ControlledReading records"
                 .format(self.value,ncurves,len(recs)))
            for rec in recs:
                warnings+=rec.diagnostics()
        
        return warnings

class ControlledExperiments(DBTable,InMemory):
    _shared_state={}
    tablepath="/controlledexperiments"
    recordclass=ControlledExperiment

    def update(self,read=True,store=True):
        cf=None
        for cf in CombiFiles():
            CEXS=self.create_controlled_experiments(cf,read=read,store=store)
        filename=os.path.join(Locations().get_userpath(),
                              "_ControlledExperiments.tab")
        self.output_to_txt(filename,overwrite=True)

    def create_controlled_experiments(self,combifile,
                                      rounder="{:.4f}",
                                      read=True,
                                      store=True,
                                      report=True):
        """
        generates a new ControlledExperiment 
        comparing this CombiFile to another.
        """
        CF=combifile
        if not CF["timespan"].is_sufficient(fortext="ControlledExperiment"):
            return False
        controls=CF.return_scored_controls()
        if not controls:
            return None

        controlled_experiments=[]
        for CN in controls:
            ce=ControlledExperiment.create_from_combifiles(CF,
                                                           CN,
                                                           rounder=rounder,
                                                           read=read,
                                                           store=store,
                                                           report=report)
            if ce:
                LOG.info("Created {}".format(str(ce)))

    def analyze(self):
        for ce in self:
            ce.analyze()
        return

    def lock(self):
        for i in self:
            i.lock()

    def unlock(self):
        for i in self:
            i.unlock()

    def total(self):
        return sum([ce["ncurves"].value for ce in self
                    if ce["ncurves"].is_valid()])

    def diagnostics(self):
        warnings=[]
        def WARN(message):
            warnings.append(message)
            LOG.warning(message)
        
        controlledexperimentsnreadings=self.total()
        R=ControlledReadings(self.dbasenameroot)
        nreadings=len(R)
        
        if controlledexperimentsnreadings!=nreadings:
            WARN("ControlledExperiments({}) should have {} controlled readings "
                 "but ControlledReadings({}) has {}"
                 .format(self.dbasenameroot,controlledexperimentsnreadings,
                         self.dbasenameroot,nreadings))
        for cex in self:
            warnings+=cex.diagnostics()
        return warnings
#
class File(DBRecord,GraphicGenerator):
    """
    >>> testfilename="EX4b (YPD) [Basic384] t+0 (DATParserWithTemp).DAT"
    >>> testfilepath=os.path.join(Locations().rootdirectory,"tests",testfilename)

    >>> temp_f=File(filepath=testfilepath)
    >>> temp_f.calculate_all()
    >>> print temp_f["size"].value
    144930
    >>> print temp_f in Files("Test")
    False
    """
    tableclassstring="Files"
    slots=[FileID,Filepath,User,ExperimentNumber,ExperimentID,FileLetter,
           Treatment,ExperimentTimeStamp,PlateLayout,Note,
           EmptyReading,Reorient,IsSurvivor,SurvivorStart,FileReader,
           NCurves,NMeasures,TimeOffset,TimeSpan,TimeSeries,TempSeries,
           Size,DateModified,CombiFile,ErrorRecord]
    defaultlookup="fileid"
    defaultfilenamereader=ReadingFileNameReader
    subrecordtables={}
    coltype=tbs.StringCol(10)
    strict=True
    titleformat="{prefix}{fileid} ({note}) {platelayout} ({treatment}){suffix}"
    subfoldernameformat="{fileid} '{platelayout}' ({note}) {treatment}"
    graphicsnamerootformat="{fileid} {platelayout} ({treatment})"

    def get_subrecordtable(self):
        if self.dbasenameroot not in self.__class__.subrecordtables:
            rec=Readings(self.dbasenameroot)
            self.subrecordtables[self.dbasenameroot]=rec
        return self.subrecordtables[self.dbasenameroot]

    def get_subrecordtype(self):
        return Reading

    def get_filenamereader(self):
        if not hasattr(self,"filenamereader"):
            self.defaultfilenamereader.cautious=False
            self.filenamereader=self.defaultfilenamereader(self["filepath"].get_fullpath())#,passerrorsto=self)
            if self.filenamereader.get_is_OK() is False:
                return False
        return self.filenamereader

    def get_parser(self):
        if not hasattr(self,"parser"):
            if self["filereader"].is_valid():
                readerclass=globals()[self["filereader"].value]
                self.parser=readerclass(self["filepath"].get_fullpath(),
                                        passerrorsto=self)
            else:
                self.parser=find_format_of(self["filepath"].get_fullpath())
        return self.parser

    def read(self,check=True,store=True):
        #self.scrutinize()
        goahead=True
        def LOGERROR(self,message):
            LOG.error(message)
            self.update_atoms(errorrecord=message)
        if check:
            if self.has_been_read():
                goahead=False
                LOG.warning("{} readings already in Readings()"
                            .format(self.value))
                list(self.yield_records())
        if goahead:
            LOG.info("Beginning File({}).read()"
                     .format(self.value))
            
            FNR=self.get_filenamereader()
            if not FNR:
                LOGERROR("get_filenamereader() returned {}"
                         .format(ri))
                return False

            PL=PlateLayout.preprocess(FNR.properties["layout"])

            if not PL.is_valid():
                LOGERROR("couldn't find platelayout {}"
                         .format(FNR.properties["layout"]))
                return False

            self.calculate_all() #other subrecords complete themselves
            
            PARS=self.get_parser()
            if not PARS:
                LOGERROR("get_parser() returned {}"
                         .format(PARS))
                return False

            elif type(PARS)==list:
                LOGERROR("get_parser() returned multiple matching formats {}"
                         .format(ri))
                return False
            elif PARS:
                self.shareddata,self.rowdata=PARS.parse()

                if self.shareddata["n_curves"]!=PL["capacity"].value:
                    LOGERROR("{} has {} measurements but "
                             "layout {} has {}"
                             .format(self["filepath"].value,
                                     self.shareddata["ncurves"],
                                     PL.value,
                                     PL["capacity"].value))
                    return False
                #print self.shareddata

                if PARS.get_is_OK() is False:
                    LOGERROR("parser is_OK is False")
                    return False
                
                platetype=({96:"96",
                            384:"384",
                            1536:"1536",
                            100:"B100"}[self.shareddata["n_curves"]])
                plate=Plates()[platetype]

                timepoints=self.shareddata["timepoints"]
                if self["timeoffset"].is_valid():
                    toff=self["timeoffset"].value
                    timepoints=[t+toff for t in timepoints]
                
                prp=self.shareddata.get("platereaderprogram",None)
                
                if not PL.is_valid():
                    LOGERROR("{} not a valid platelayout".format(PL.value))
                    return False

                pps=list(PL.yield_records())

                if self["reorient"].value:
                    pps.reverse()
                readings=[]
                flagdict=FNR.properties.get("flags",{})

                for i,row in enumerate(self.rowdata):
                    pp=pps[i]
                    well=pp["well"]
                    wellname=pp["wellname"]
                    strain=pp["strain"]
                    if wellname.value in flagdict:
                        errorflag=wellname.value
                        errorreason=flagdict[wellname.value]
                    elif strain.value in flagdict:
                        errorflag=strain.value
                        errorreason=flagdict[strain.value]
                    else:
                        errorreason=None

                    RID="{}_{}".format(self.value,well.value)
                    if self["emptyreading"].value==True:
                        r=Reading(readingid=RID,
                                  file=self,
                                  plateposition=pp,
                                  well=well,
                                  strain=strain,
                                  isblank=pp["isblank"],
                                  isborder=pp["isborder"],
                                  readinggroup=pp["groupid"].value,
                                  treatment=self["treatment"].value,
                                  emptymeasure=np.mean(row["measurements"]),
                                  platereaderprogram=prp,
                                  errorrecord=errorreason)
                    else:
                        mn=min(row["measurements"]) if len(row["measurements"])>1 else 0
                        r=Reading(readingid=RID,
                                  file=self,
                                  plateposition=pp,
                                  well=well,
                                  strain=strain,
                                  isblank=pp["isblank"],
                                  isborder=pp["isborder"],
                                  readinggroup=pp["groupid"].value,
                                  treatment=self["treatment"].value,
                                  minimum=mn,
                                  measurements=[m-mn
                                                for m in row["measurements"]],
                                  platereaderprogram=prp,
                                  errorrecord=errorreason)

                    if errorreason:
                        LOG.warning("flagged Reading({}) because {} is flagged {}"
                                    .format(r.value,errorflag,errorreason))
                    readings.append(r)
                if self["reorient"].value:
                    readings.reverse()

                updates={"filereader":PARS.__class__.__name__,
                         "nmeasures":self.shareddata["n_measures"],
                         "ncurves":self.shareddata["n_curves"],
                         "experimenttimestamp":self.shareddata.get("exp_datetime",None),
                         "platelayout":PL}

                if self["emptyreading"].value==False:
                    updates.update({"timespan":timepoints[-1]-timepoints[0],
                                    "timeseries":TimeSeries(timepoints),
                                    "tempseries":TempSeries(self.shareddata.get("temperaturepoints",None))})

                self.records=readings
                self.update_atoms(**updates)

                LOG.debug("updated atoms {}".format(updates))

                if store:
                    #NB check=True slows things down a lot
                    #So assume that not stored else has_been_read() wouldn't
                    #have returned False?
                    Readings().store_many_record_objects(self.records,check=False)

            return len(getattr(self,"records",[]))

    def has_been_read(self):
        if not hasattr(self,"alreadyread"):
            query=self.get_subrecordtype()(file=self.value)
            self.alreadyread=query in self.get_subrecordtable()
        return self.alreadyread
    
    def rename_file_with_error(self,errorstring):
        filepath=self["filepath"].get_fullpath()
        path,filename=os.path.split(filepath)
        if filename.startswith("["):
            LOG.error("already renamed with error brackets []")
            return False
        else:
            newfilename="[{}] {}".format(errorstring.upper(),filename)
            newfilepath=os.path.join(path,newfilename)
            LOG.warning("{}.rename_file_with_error() is renaming {} to {}"
                        .format(self.__class__.__name__,filepath,newfilepath))
            os.rename(filepath,newfilepath)
            self.unread()
            self.delete()
            return True

    def unread(self):
        LOG.info("unreading & deleting {} ({})".format(self,type(self)))
        if not hasattr(self,"value") or self.value is None:
            self["fileid"].calculate()

        readings=Readings().get(file=self["fileid"].value)
        if not readings:
            LOG.info("no readings to remove for {}".format(self.value))
            return
        for reading in readings:
            LOG.info("deleting reading {} for {}".format(reading,self.value))
            reading.delete()

    def yield_records(self,read=False):
        if not hasattr(self,"records"):
            tab=self.get_subrecordtable()
            self.records=tab.get(file=self["fileid"].value)
        for result in self.records or []:
            yield result

    def flags(self):
        return self["errorrecord"].get_flagdict()

    def timevalues(self):
        return self["timeseries"]._get_trimmed()

    def tempvalues(self):
        return self["tempseries"]._get_trimmed()

    def get_coords(self):
        """
        It's slow to pull together a list of well coords (for plots)
        so only do it once
        """
        if not hasattr(self,"coords"):
            self.coords=self["plate"].get_coords()
        return self.coords

    def sample(self):
        for record in self.yield_records():
            return record

    def has_changed(self):
        """
        checks filepath and sees if path still exists
        and if so whether self["size"] or self["datemodifed"] are as expected.
        """
        filepath=self["filepath"].get_fullpath()

        if not os.path.exists(str(filepath)):
            return False

        if self["size"].value==None:
            return True
        if int(self["size"].value)!=int(os.path.getsize(filepath)):
            LOG.error("{} has different size to value stored in database"
                      .format(filepath))
            return True
        if int(self["datemodified"].value)!=int(os.path.getmtime(filepath)):
            LOG.error("{} has different datemodified to value stored "
                      "in database"
                      .format(filepath))
            return True
        return False

    def is_empty(self):
        return self["timeoffset"].value==-100

    def draw_if_empty(self,pathformatter=os.path.join(Locations()["plots"],
                                                      "_Empty plate views",
                                                      "{userfolder}",
                                                      "EmptyPlate {graphicsn"
                                                      "ameroot}.{extension}"),
                      **kwargs):
        if self.is_empty():
            return AgarThickness(self,pathformatter=pathformatter,
                                 **kwargs)

    def get_RenamedFile(self,store=True):
        RF=RenamedFile(renamedfilename=self["filepath"].value,
                       renamedfolder=Locations().get_userpath())
        RF.calculate_all()
        if store:
            if RF not in RenamedFiles():
                RF.store()
        return RF

    def diagnostics(self):
        warnings=[]
        def WARN(message):
            warnings.append(message)
            LOG.warning(message)
        #check key parameters have been stored
        if not self["filereader"].is_valid(): 
            WARN("{} has no filereader"
                 .format(self.value))
        if not self["platelayout"].is_valid(): 
            WARN("{} has no platelayout"
                 .format(self.value))
        if not self["experimenttimestamp"].is_valid(): 
            WARN("{} has no experimenttimestamp"
                 .format(self.value))
        if not self["ncurves"].is_valid(): 
            WARN("{} has no ncurves"
                 .format(self.value))
        if warnings:
            return warnings

        
        ncurves=self["ncurves"].value
        if hasattr(self,"records"): del self.records
        recs=list(self.yield_records())
        if ncurves!=len(recs):
            WARN("File({}) ncurves={} but has {} records"
                 .format(self.value,ncurves,len(recs)))
            for rec in recs:
                warnings+=rec.diagnostics()
        
        return warnings

class Files(DBTable,InMemory):
    """
    """
    _shared_state={}
    tablepath="/files"
    recordclass=File

    @classmethod
    def get_dmonitor(cls):
        if hasattr(cls,"dmonitor"):
            if cls.dmonitor.directory==Locations().get_userpath():
                return cls.dmonitor
        cls.dmonitor=DirectoryMonitor(Locations().get_userpath(),
                                      include=[".xlsx",".DAT",".csv"],
                                      exclude=[".txt",".p"])
        return cls.dmonitor

    def update(self,**kwargs):
        """
        Any new files are added. Any changed files are reread.
        """
        found_paths=[os.path.normpath(p) for p in self.get_dmonitor()]
        stored_files=[f for f in self]
        stored_paths=[f["filepath"].get_fullpath() for f in self]
        stored_dict=dict(zip(stored_paths,stored_files))
        new_paths=[p for p in found_paths if p not in stored_paths]
        missing_paths=[p for p in stored_paths if p not in found_paths]
        changed_paths=[f["filepath"].get_fullpath()
                       for f in stored_files if f.has_changed()]

        if missing_paths:
            LOG.info("REMOVING MISSING FILES")
            for path in missing_paths:
                f=File(filepath=os.path.basename(path))
                f["FileID"].calculate()
                LOG.debug("missing path {}".format(path))
                f.unread()
                f.delete()

        if changed_paths:
            LOG.info("REMOVING CHANGED FILES")
            for path in changed_paths:
                f=File(filepath=os.path.basename(path))
                f.unread()
                f.delete()

        if new_paths+changed_paths:
            LOG.info("ADDING NEW & CHANGED FILES")
            for path in new_paths+changed_paths:
                f=File(filepath=os.path.basename(path))
                f.calculate_all()
                f.store()
                rf=f.get_RenamedFile(store=True)

        if kwargs.get("read_unread",True):
            self.read_unread(**kwargs)

    def read_unread(self,**kwargs):
        LOG.info("READING UNREAD")
        """
        for f in self:
            if not f.has_been_read():
                LOG.debug("no readings already found for {}".format(f.value))
                try:
                    f.read()
                except Exception as e:
                    LOG.error(e)
                f.draw_if_empty()
            elif not f["filereader"].is_valid():
                LOG.debug("filereader not yet validated for {}".format(f.value))
                try:
                    f.read()
                except Exception as e:
                    LOG.error(e)
                f.draw_if_empty()
            else:
                LOG.debug("already read {}".format(f.value))
        return self
        """
        for f in self:
            f.read()
            f.draw_if_empty()

    def total(self):
        return sum([p["ncurves"].value for p in self])

    def get_combifile_dict(self,alreadymade=False,read=False,save=False):
        output=[]
        #Return nothing if 1 file or less.
        if len(self)<2:
            return {}
        #Split out all files already with a valid combifile
        alreadydone=[]
        notdone=[]
        output={}
        for f in self:
            if f["combifile"].is_valid():
                if alreadymade:
                    if f["combifile"] not in alreadydone:
                        alreadydone.append(f["combifile"])
            else:
                notdone.append(f)

        #Now separate out different experimentids
        expiddict=defaultdict(list)
        for f in notdone:
            expiddict[f["experimentid"].value].append(f)

        for expid,expidset in expiddict.items():
            #Split expidset into survivors and nonsurvivors and produce
            #a different combifile for each
            
            nonsurvivor=[f for f in expidset
                         if f["issurvivor"].value==False]
            survivor=[f for f in expidset
                      if f["issurvivor"].value==True]
            for issurv,fileset in zip([False,True],[nonsurvivor,survivor]):
                if len(fileset)>0:
                    #Fourth, check to see if fileset has multiple layouts,
                    #and further split resulting combifiles accordingly
                    subfilesets={}
                    layouts={}
                    for f in fileset:
                        pl=f["platelayout"]
                        layoutname=pl.value
                        if layoutname not in subfilesets:
                            subfilesets[layoutname]=[f]
                            layouts[layoutname]=pl
                        else:
                            subfilesets[layoutname].append(f)
                    for loname,subfileset in subfilesets.items():
                        cf=CombiFile.create_from_files(*subfileset,
                                                       save=save,
                                                       read=read)
                        if cf:
                            output[cf.value]=cf
        if alreadymade:
            for cf in alreadydone:
                output[cf.value]=cf
        return output


    def unlock(self):
        for f in self:
            f.update_atoms(combifile=None)

    def diagnostics(self):
        warnings=[]
        def WARN(message):
            warnings.append(message)
            LOG.warning(message)
        
        filesnreadings=self.total()
        R=Readings(self.dbasenameroot)
        nreadings=len(R)
        
        if filesnreadings!=nreadings:
            WARN("Files({}) should have {} readings "
                 "but Readings({}) has {}"
                 .format(self.dbasenameroot,filesnreadings,
                         self.dbasenameroot,nreadings))
            for file in self:
                warnings+=file.diagnostics()
#
class OriginalFilename(DBString):
    coltype=tbs.StringCol(255)
    colclip=30

    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            filepath=rec.find_filepath()
            if filepath:
                content=read_data_file(filepath)
                if content is False:
                    return False
                else:
                    shareddata,rowdata=content
                    OFil=originalfilename_from_shareddata(shareddata)
                    if OFil:
                        self.set_value(OFil)
        return self.value

class OriginalFolder(DBString):
    coltype=tbs.StringCol(255)
    colclip=20
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            OFil=rec["originalfilename"]
            if OFil.is_valid():
                platereader_output=Locations().platereader_output
                pth=os.path.join(platereader_output,OFil.value)
                if os.path.exists(pth):
                    self.set_value(platereader_output)
        return self.value

class RenamedFilename(DBString):
    coltype=tbs.StringCol(255)
    colclip=20

class RenamedFolder(DBString):
    coltype=tbs.StringCol(255)
    colclip=20

class DateCreated(DBDateTime):
    """
    Actually I'm using datemodified, because copies get a new datecreated
    but the meaning is the date the file was originally created
    which should be fine as long as nobody edits it.
    """
    shortheader="dateC"
    colclip=7
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            filepath=rec.find_filepath()
            
            if filepath:
                self.set_value(os.path.getmtime(filepath))
        return self.value

class RenamedFile(DBRecord):
    tableclassstring="RenamedFiles"
    slots=[OriginalFilename,OriginalFolder,
           RenamedFilename,RenamedFolder,
           DateCreated]
    defaultlookup="originalfilename"
    strict=True

    def find_filepath(self):
        #Look for original first
        OFil=self["originalfilename"]
        OFld=self["originalfolder"]
        if OFld.is_valid() and OFil.is_valid():
            if os.path.exists(OFld.value):
                filepath=os.path.join(OFld.value,OFil.value)
                if os.path.exists(filepath):
                    return filepath
        #Or look for renamed
        RFil=self["renamedfilename"]
        RFld=self["renamedfolder"]
        if RFld.is_valid():
            if os.path.exists(RFld.value):
                filepath=os.path.join(RFld.value,RFil.value)
                if os.path.exists(filepath):
                    return filepath
        return False

    def get_originalfilepath(self):
        if not self["originalfolder"].is_valid():
            return
        if not self["originalfilename"].is_valid():
            return
        return os.path.join(self["originalfolder"].value,
                            self["originalfilename"].value)

    def get_renamedfilepath(self):
        if not self["renamedfolder"].is_valid():
            return
        if not self["renamedfilename"].is_valid():
            return
        return os.path.join(self["renamedfolder"].value,
                            self["renamedfilename"].value)

    def get_file(self):
        NF=self["renamedfilename"]
        if not NF.is_valid():
            return None
        namedict=ReadingFileNameReader(NF.value).properties
        fileid="{user}{experimentnumber}{fileletter}".format(**namedict)
        searchresult=Files().get(fileid)
        if type(searchresult)==list:
            LOG.error("Multiple Files found with fileid {}".format(fileid))
            return searchresult
        elif not searchresult:
            LOG.error("No File found with fileid {}".format(fileid))
            return None
        else:
            return searchresult

    def remake_file(self):
        OFP=self.get_originalfilepath()
        RFP=self.get_renamedfilepath()
        if not OFP:
            LOG.error("{} does not have valid originalfilepath".format(self))
            return
        if not RFP:
            LOG.error("{} does not have valid renamedfilepath".format(self))
            return
        if not os.path.exists(OFP):
            LOG.error("{} does not exist".format(OFP))
            return
        if os.path.exists(RFP):
            LOG.info("{} already exists".format(RFP))
            return
        return copy_to(OFP,RFP)

class RenamedFiles(DBSharedTable):
    _shared_state={}
    tablepath="/renamedfiles"
    recordclass=RenamedFile

    def populate(self):
        all=[]
        for subfolder in Locations().yield_userpaths():
            F=Files(os.path.basename(subfolder))
            for FOB in F:
                RF=self.recordclass(renamedfilename=FOB["filepath"].value,
                                    renamedfolder=subfolder)
                RF.calculate_all()
                if RF not in self:
                    all.append(RF)
                    #print RF
        self.store_many_record_objects(all)

    def return_platereader_output_list(self):
        platereader_output=Locations().platereader_output
        output={}
        for rf in self:
            if rf["originalfolder"].is_valid():
                output[rf["originalfilename"].value]=rf["renamedfilename"].value
        for fl in yield_subpaths(platereader_output,
                                 dig=False,onlytype='files',includeroot=True):
            flbn=os.path.basename(fl)
            extn=os.path.splitext(flbn)[-1]
            if flbn not in output:
                if extn in [".csv",".DAT",".xlsx",".xls"]:
                    if flbn[0]!="[":
                        output[flbn]=''
        sortlist=[]
        for Ofil,Rfil in output.items():
            CT=os.path.getctime(os.path.join(platereader_output,Ofil))
            sortlist.append((Ofil,Rfil,CT))
        sortlist.sort(key=lambda t: t[2],reverse=True)
        return sortlist

    def remake(self):
        for rf in self:
            rf.remake_file()

#STRAINS ######################################################################
class StrainID(DBString):
    coltype=tbs.StringCol(30)

class IsBlank(DBBool):
    shortheader="isB"
    colclip=3
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False
            
            self.set_value(rec["strainid"].value in ['b','','-',' '])
        return self.value

class AliasOf(DBString):
    coltype=tbs.StringCol(30)

class Source(DBString):
    coltype=tbs.StringCol(30)
class Ignore(DBBool): pass
class GenotypeFilepath(Filepath): pass
    
class Background(DBString):
    coltype=tbs.StringCol(100)

class Modifications(DBString):
    coltype=tbs.StringCol(100)

class rQTLgroup(DBString):
    coltype=tbs.StringCol(50)

class Ploidy(DBuInt8):
    pass

class MatingType(DBString):
    coltype=tbs.StringCol(2)
#
class Strain(DBRecord,GraphicGenerator):
    tableclassstring="Strains"
    slots=[StrainID,IsBlank,AliasOf,Source,PlateLayout,
           GenotypeFilepath,Ignore,Background,Modifications,
           rQTLgroup,Ploidy,MatingType]
    defaultlookup="strainid"
    coltype=tbs.StringCol(30)
    strict=False
    subrecordtables={}
    titleformat="All curves {strainid}"
    subfoldernameformat="_StrainPlots"
    graphicsnamerootformat=titleformat

    def get_subrecordtable(self):
        if self.dbasenameroot not in self.__class__.subrecordtables:
            rec=CombiReadings(self.dbasenameroot)
            self.subrecordtables[self.dbasenameroot]=rec
        return self.subrecordtables[self.dbasenameroot]

    def get_subrecordtype(self):
        return CombiReading

    def yield_records(self,include_controls=True):
        if not hasattr(self,"records"):
            tab=self.get_subrecordtable()
            self.records=tab.get(strain=self.value) or []
            nametracker=[rec.value for rec in self.records]
            if include_controls:
                for c in CombiReadings("Controls").get(strain=self.value) or []:
                    if c.value not in nametracker:
                        self.records.append(c)
        for result in self.records or []:
            yield result

    def is_blank(self):
        if not self["isblank"].is_valid():
            self["isblank"].set_value(self["strainid"].value in ['b','','-',' '])
        return self["isblank"].value

    def genotypes(self):
        if self.is_blank(): return {}
        if not self["genotypefilepath"].is_valid():
            proxy=Strains()[self["aliasof"].value]
            if proxy:
                if proxy["genotypefilepath"].is_valid():
                    return proxy.genotypes()
        if not hasattr(self.__class__,"genotype_dict"):
            try:
                T=self._get_table()
                self.__class__.genotype_dict=T.get_genotype_dict()
            except Exception as e:
                LOG.error("couldn't get_genotype_dict because {}".format(e))
                return {}
        return self.__class__.genotype_dict.get(self["strainid"].value,{})

    def alleles(self):
        return self.genotypes().get("alleles",False)

    def markers(self):
        return self.genotypes().get("markers",False)

    def platesources(self):
        return list(self["platelayout"].yield_records(strain=self["strainid"].value))

    def plot(self,**kwargs):
        pass

#
class Strains(DBSharedTable,InMemory):
    """
    name	note	MAT	ho-	HYG+	G418+	leu-	lys-	met-	ura-	Alias	Source	Parent1	Parent2	Group	Background
    What about qtl markers? How to store these in an expandable way?
    Needs to be capable to storing arbitrary number & type of genotypes, e.g. SNPs (by
    location & base change or by parental genotype), auxotrophies & deletions etc
    """
    _shared_state={}
    tablepath="/strains"
    recordclass=Strain
    sourcefile="strains.csv"
    attemptedtoload=False
    #sourcefilereader=StrainData(sourcefile)

    def populate(self):
        if Strains.attemptedtoload:
            return False
        LOG.info("populating Strains()")
        sourcefile=os.path.join(Locations()["genotypes"],Strains.sourcefile)
        if not os.path.exists(sourcefile):
            LOG.error("No strains info available; no file called {}"
                      .format(sourcefile))
            Strains.attemptedtoload=True
            return False
        self.sfr=Strains.sourcefilereader=StrainData(sourcefile)
        shareddata,rowdata=self.sfr.parse()
        tostore=[]
        aliases=[]
        allGFP={}
        for i,rd in enumerate(rowdata):
            GFP=rd.get("GenotypeFile",None)
            if GFP not in allGFP:
                fullGFP=os.path.join(Locations()["genotypes"],GFP)
                if os.path.exists(fullGFP):
                    allGFP[GFP]=fullGFP
                else:
                    LOG.error("no genotype file called {}"
                              .format(fullGFP))
                    fullGFP=None
                    allGFP[GFP]=None
            else:
                fullGFP=allGFP[GFP]

            s=Strain(strainid=rd.get("name",None),
                     source=rd.get("Source",None),
                     platelayout=rd.get("PlateLayout",None),
                     genotypefilepath=fullGFP,
                     ignore={"false":False,
                             "true":True,
                             "":None}[rd.get("Ignore","").lower()],
                     background=rd.get("Background",None),
                     rqtlgroup=rd.get("rQTLgroup",None),
                     ploidy=len(rd.get("MAT","")),
                     matingtype=rd.get("MAT",None))
                     #note=rd["note"]))
            tostore.append(s)
            if rd.get("Alias",None):
                for alias in rd["Alias"].split(";"):
                    alias=alias.strip()
                    s=Strain(strainid=alias,
                             source=rd.get("Source",None),
                             aliasof=rd.get("name",None),
                             platelayout=rd.get("PlateLayout",None),
                             ignore={"false":False,
                                     "true":True,
                                     "":None}[rd.get("Ignore","").lower()],
                             background=rd.get("Background",None),
                             rqtlgroup=rd.get("rQTLgroup",None),
                             ploidy=len(rd.get("MAT","")),
                             matingtype=rd.get("MAT",None))
                    aliases.append(s)
        self.store_many_record_objects(tostore+aliases,check=False)
        return self

    def update(self):
        self.clear()
        self.populate()

    def get_genotype_dict(self):
        if not hasattr(self,"genotypelookup"):
            self.genotypelookup={}
            allfiles=self.get_values_of_atom("genotypefilepath")
            for GFP,count in allfiles.items():
                if GFP:
                    if os.path.isfile(GFP):
                        if not hasattr(self,"genotypefiles"):
                            self.genotypefiles={}
                            self.genotyperows={}
                        if GFP not in self.genotypefiles:
                            gdob=GenotypeData(GFP)
                            try:
                                SD,RD=gdob.parse()
                                GD=gdob.make_genotypedict()
                                self.genotypelookup.update(GD)
                                self.genotypefiles[GFP]=gdob
                            except Exception as e:
                                LOG.error("can't parse {} because {}"
                                          .format(GFP,e))
            if not self.genotypelookup:
                del self.genotypelookup
                return {}
            LOG.info("created Strains().genotypelookup from {}"
                     .format([os.path.basename(f) for f in allfiles if f]))
        return self.genotypelookup

    def plot(self,include_controls=True,**kwargs):
        """
        e.g. D:\PHENOS2\Plots\SoftwareTest\_Strain_plots
        """
        return curveplot_strain(self,include_controls=include_controls,**kwargs)

#
class PlatePositionID(DBString):
    coltype=tbs.StringCol(100)
    strict=True

class PlateIndex(DBuInt16):
    pass

class GroupID(DBString):
    coltype=tbs.StringCol(30)
    strict=True

class PlatePosition(DBRecord):
    """
    """
    tableclassstring="PlatePositions"
    slots=[PlatePositionID,PlateIndex,PlateLayout,Well,Strain,IsBlank,GroupID]
    defaultlookup="platepositionid"
    coltype=tbs.StringCol(100)
    colclip=10
    strict=True

    def is_blank(self):
        return self["isblank"].value

    def wellrowletter(self):
        return self["well"].calculate_wellrowletter(self["wellrow"].value)
#
class PlatePositions(DBSharedTable,InMemory):
    """
    
    """
    _shared_state={}
    tablepath="/platepositions"
    recordclass=PlatePosition

    def update(self):
        """
        checks that existing platepositions match the ncurves of each platelayout
        in platelayouts, and if not clears the table.
        Reads in (adding platepositions) any platelayouts not already read in.
        """
        pl=PlateLayouts()
        pp=PlatePositions()
        ppdict=pp.get_values_of_atom("platelayout")
        already_entered=[]
        errors=0
        for layoutstring,layoutncurves in ppdict.items():
            plobject=pl.get(layoutstring)
            if plobject is None:
                LOG.error("can't find layoutstring {}".format(layoutstring))
                continue
            elif type(plobject)==list:
                LOG.error("{} matches for layoutstring {}".format(len(plobject),layoutstring))
                plobject=plobject[0]
            positionncurves=plobject["capacity"].value
            if layoutncurves!=positionncurves:
                LOG.warning("PlatePositions().update found {} positions "
                            "for {}, not {} as in PlateLayouts"
                            .format(positionncurves,layoutstring,
                                    layoutncurves))
                errors+=1
            else:
                already_entered.append(layoutstring)
        if errors>0:
            LOG.warning("PlatePositions().update found contradictions "
                        "so reading again")
            pp.clear()
            already_entered=[]

        for plobject in pl:
            if plobject["layoutstring"].value not in already_entered:
                plobject.read(store=True)

#

#READINGS #####################################################################
class ReadingID(DBString):
    """
    """
    coltype=tbs.StringCol(40)
    def calculate(self):
        rec=self.get_record()
        if rec is False: return False

        rec.value="{}_{}".format(rec["file"].value,rec["well"].value)
        self.set_value(rec.value)

class ReadingGroup(DBString):
    coltype=tbs.StringCol(40)
    shortheader="rGrp"
    colclip=4
    strict=False
class EmptyMeasure(DBFloat32):
    invalid_values=[None,"-","",np.nan,float('nan'),0,0.0]
class PlatedMass(DBFloat32):
    invalid_values=[None,"-","",np.nan,float('nan'),0,0.0]
    def calculate(self):
        rec=self.get_record()
        if rec is False: return False

        em=rec["emptymeasure"].value
        ts=rec["measuredvalues"]
        if em and ts:
            if not all(ts):
                self.set_value(ts[0]-em)
                return self.value
        return None

class Minimum(DBFloat32):
    invalid_values=[None,"-","",np.nan,float('nan')]

class Measurements(DBSeries):
    colclip=30

class PlateReaderProgram(DBString):
    coltype=tbs.StringCol(30)
    shortheader="pRp"
    colclip=8

class Model(DBString):
    coltype=tbs.StringCol(100) #BUT REIMPLEMENT AS RECORDATOM?
class ControlledReadingID(DBString):
    coltype=tbs.StringCol(120)
    shortheader="crdID"
    colclip=8

class ControlReadingID(DBString):
    coltype=tbs.StringCol(60)
    shortheader="crID"
    colclip=8

class FinalAverage(DBFloat32):
    pass

class Ratio(DBFloat32):
    def calculate(self):
        if not self.is_valid():
            rec=self.get_record()
            if rec is False: return False

            CEX=rec["controlledexperiment"]
                
            SI,CI=CEX.get_focus_indices()
            R=rec.get_treatment_reading()
            if not R:
                LOG.error("No treatment reading found for "
                          "ControlledReading {}({})"
                          .format(rec.value,
                                  rec.dbasenameroot))
                return None
            Rvals=R.rawmeasuredvaluesminusagar()
            C=rec.get_control_reading()
            if not C:
                LOG.error("No control reading found for "
                          "ControlledReading {}({})"
                          .format(rec.value,
                                  rec.dbasenameroot))
                return None
            Cvals=C.rawmeasuredvaluesminusagar()
            Rfocalvals=indices_to_values(Rvals,SI)
            Cfocalvals=indices_to_values(Cvals,CI)

            rn,cn=len(Rfocalvals),len(Cfocalvals)
            if rn==0: LOG.error("reading {} has 0 timepoints in range"
                                .format(R.value))
            if cn==0: LOG.error("controlreading {} has 0 timepoints in range"
                                .format(C.value))
            if not rn or not cn:
                return None
            
            ra=sum(Rfocalvals)/float(rn)
            ca=sum(Cfocalvals)/float(cn)
            rat=ra/ca
            if rat>1000:
                LOG.warning("ControlledReading {} (ControlledExperiment {})"
                            "gets Ratio of {} from Rfocalvals={} and "
                            "Cfocalvals={}, rn={}, cn={}, R={}, C={}"
                            .format(self.value,rec.value,
                                    rat,Rfocalvals,Cfocalvals,rn,cn,Rvals,Cvals))
            self.set_value(rat)
            rec["finalaverage"].set_value(ra)
        return self.value
#
class Reading(DBRecord):
    slots=[ReadingID,File,PlatePosition,Well,Strain,IsBlank,IsBorder,
           ReadingGroup,Treatment,PlateReaderProgram,
           EmptyMeasure,PlatedMass,Minimum,Measurements,
           Model,ErrorRecord]
    tableclassstring="Readings"
    defaultlookup="ReadingID"
    defaultcolorby="readinggroup"
    defaultcolor="black"
    coltype=tbs.StringCol(40)
    strict=True

    def get_parent(self):
        return self["file"]

    def get_curve_dict(self,**kwargs):
        """
        A plotting class (e.g. Plot) can call this method
        to get a dictionary of information pertinent to the plot
        """
        curvetype=kwargs.setdefault("curvetype","zeroed")
        xlist,ylist=[],[]
        if curvetype=="temp":
            temps=self["tempseries"]
            if temps.is_valid():
                xlist,ylist=zip(*temps._get_trimmed())
        else:
            times=self["timeseries"]
            if times.is_valid():
                xlist,zylist=zip(*self["timeseries"]._get_trimmed())
                mn=self["minimum"].value
                if curvetype=="zeroed": ylist=zylist
                elif curvetype=="raw": ylist=[y+mn for y in zylist]

        kwargs["xlist"]=xlist
        kwargs["ylist"]=ylist
        kwargs.setdefault("minx",min(xlist))
        kwargs.setdefault("maxx",max(xlist))
        kwargs.setdefault("miny",min(ylist))
        kwargs.setdefault("maxy",max(ylist))
        
        if self["emptymeasure"].is_valid():
            kwargs["emptymeasure"]=self["emptymeasure"].value
            
        kwargs.setdefault("isblank",self["strain"].value in ["b","","-",None])

        kwargs.setdefault("colorvalue",self[kwargs.get("colorby",
                                                       self.defaultcolorby)].value)
        if "colorby" not in kwargs or kwargs["colorvalue"]==None:
            kwargs.setdefault("defaultcolor",self.defaultcolor)

        if "labelby" in kwargs:
            if type(kwargs["labelby"]) in [tuple,list]:
                kwargs["label"]=", ".join([str(self[labelby].value)
                                           for labelby in kwargs["labelby"]])
            elif type(kwargs["labelby"])==str:
                kwargs["label"]=self[kwargs["labelby"]].value

        return kwargs

    def is_blank(self):
        if not self["isblank"].is_valid():
            self["isblank"].set_value(self["strain"].is_blank())
        return self["isblank"].value

    def is_empty(self):
        return bool(self["emptymeasure"].value)

    def wellrowletter(self):
        return self["well"].calculate_wellrowletter(self["wellrow"].value)

    def timevalues(self):
        return self["timeseries"]._get_trimmed()
    xvalues=timevalues

    def measuredvalues(self):
        return self["measurements"]._get_trimmed()
    yvalues=measuredvalues

    def summeasuredvalues(self):
        if not hasattr(self,"sumofmeasuredvalues"):
            self.sumofmeasuredvalue=float(sum(self.measuredvalues()))
        return self.sumofmeasuredvalue

    def rawmeasuredvalues(self):
        mn=self["minimum"].value or 0
        return [y+mn for y in self.measuredvalues()]

    def tempvalues(self):
        return self["tempseries"]._get_trimmed()

    def maximumchange(self):
        return float(max(self["measurements"].value))

    def average_of_timepoints(self,
                              timepoints=[15.33, 15.66, 16.0, 16.33]):
        indices=self["timeseries"].intersection_indices(timepoints,
                                                        rounder="{:.1f}")
        #assert len(indices)==len(timepoints)
        values=[self["measuredvalues"][i] for i in indices]
        return sum(values)/float(len(values))

    def average_of_timepoints_plus_minimum_minus_agar(self,
                                           timepoints=[15.33, 15.66, 16.0, 16.33]):
        return self.average_of_timepoints(timepoints)+self["minimum"].value-self["emptymeasure"].value

    def plot(self,**kwargs):
        return CurvePlot(self,**kwargs)

    def __cmp__(self,other):
        """
        Should return a negative integer if self < other, zero if self == other,
        a positive integer if self > other
        """
        if self["timeseries"]==other["timeseries"]:
            SMV,OMV=self.summeasuredvalues(),other.summeasuredvalues()
            return int(SMV-OMV)
        else:
            LOG.critical("timeseries don't match for {} and {}"
                         .format(self,other))
            sys.exit()

    def should_ignore(self):
        if self.is_blank():
            return "ignore based on is_blank"
        if self["strain"]["ignore"].value==True:
            return "ignore based on strain"
        if self["errorrecord"].value:
            return "ignore based on errorrecord {}".format(self["errorrecord"].value)
        return False

    def diagnostics(self):
        warnings=[]
        def WARN(message):
            warnings.append(message)
            LOG.warning(message)
        return warnings

class Readings(DBTable,InMemory):
    tablepath="/readings"
    recordclass=Reading

    def update(self):
        LOG.debug("calling Readings().update()")
        Files().read_unread()
        return self

    def diagnostics(self):
        warnings=[]
        def WARN(message):
            warnings.append(message)
            LOG.warning(message)
        return warnings
#
class CombiReading(Reading,GraphicGenerator):
    tableclassstring="CombiReadings"
    slots=[ReadingID,CombiFile,PlatePosition,Well,Strain,IsBlank,IsBorder,
           ReadingGroup,Treatment,
           EmptyMeasure,PlatedMass,Minimum,Measurements,
           Model,ErrorRecord]
    titleformat="{prefix} {strain} ({readingid}) {platelayout} ({treatment}){suffix}"
    #subfoldernameformat="{combifileid} '{platelayout}' ({note}) {treatment}"
    graphicsnamerootformat="{strain} {wellname} {combifileid} {platelayout} ({treatment})"
    coltype=tbs.StringCol(40)

    def get_parent(self):
        return self["combifile"]

    def get_subfoldername(self,*args,**kwargs):
        return os.path.join(self.get_parent().get_subfoldername(*args,**kwargs),
                            "CurveAnalyses")

    def rawmeasuredvaluesminusagar(self):
        em=self["emptymeasure"].value or 0
        return [y-em for y in self.rawmeasuredvalues()]

    def minimumwithoutagar(self):
        return self["minimum"].value-self["emptymeasure"].value

    def maximumwithoutagar(self):
        return (max(self["measurements"]._get_trimmed())+self["minimum"].value)-self["emptymeasure"].value

    def average_about_time(self,timepoint=16,plus_minus=0.5,
                           report=True,generatefresh=False):
        P=self.get_parent()
        timeindices=P.pick_timeindices(timepoint=timepoint,
                                       plus_minus=plus_minus,
                                       report=report,
                                       generatefresh=generatefresh)
        MV=self.rawmeasuredvaluesminusagar()
        readings=[MV[i] for i in timeindices]
        nreadings=len(readings)
        try:
            average=sum(readings)/float(nreadings)
        except:
            average=None
        return average,nreadings

    def is_empty():
        return self["emptymeasure"].is_valid()

    def user(self):
        return self["combifile"]["user"]

    def plot(self,**kwargs):
        return CurveAnalysis(self,**kwargs)

    def get_replicates(self):
        query=self.__class__(combifile=self["combifile"].value,
                             strain=self["strain"].value)
        results=self._get_table().query_by_record_object(query)
        return results

    def plot_with_replicates(self,**kwargs):
        #kwargs.setdefault("colorby","wellname")
        kwargs.setdefault("colorby","platedmass")
        kwargs.setdefault("labelby","wellname")
        kwargs.setdefault("title","CombiReading  {} {}, {} ({})"
                          " plot_with_replicates"
                          .format(self["strain"].value,
                                  self["wellname"].value,
                                  self["combifile"].value,
                                  self["platelayout"].value))
        kwargs.setdefault("subfolder",self["experimentid"].value)
        replicates=self.get_replicates()
        return CurvePlot(replicates,**kwargs)

    def genotypes(self):
        return self["strain"].genotypes()

    def alleles(self):
        return self["strain"].alleles()

    def markers(self):
        return self["strain"].markers()

    def intervals(self,upto=None):
        """
        returns minimum and maximum interval between timepoints
        """
        TV=self.timevalues()
        if upto:
            TV=TV[:upto]
        intervals=[y-x for x,y in get_kmer_list(TV,k=2)]
        return min(intervals),max(intervals)

    def get_inflection(self,smoothing=15):
        """
        Smooth data, then get deltas (differences between measures)
        and identify first peak among deltas, and trace that
        back to the nearest original timepoint and measurement
        """
        #if sum(self.intervals(upto=30))>2:
        #    return False
        if not hasattr(self,"measureinflection"):
            self.iD=calc_inflection(self.rawmeasuredvaluesminusagar(),
                                    self.timevalues())
            self.__dict__.update(self.iD)
        return getattr(self,"inflectionM",False),getattr(self,"inflectionT",False)

    def get_lag(self):
        if not hasattr(self,"lagtime"):
            self.get_inflection()
        return getattr(self,"lagtime",False)

    def get_maxslope(self):
        if not hasattr(self,"maxMslope"):
            self.get_inflection()
        return getattr(self,"maxMslope",False)

class CombiReadings(Readings):
    tablepath="/combireadings"
    recordclass=CombiReading

    def assess_platedmasses(self,versus="maximumchange"):
        """
        Correlates platedmass to 
        """
        all=[(cr["treatment"].value,cr["platedmass"],cr[versus])
             for cr in self]
        bytreatment={}
        for t,p,m in all:
            if t not in bytreatment:
                bytreatment[t]=[]
            if p.is_valid() and m:
                bytreatment[t].append((p.value,m))
        import matplotlib.pyplot as pyplt
        for trt,tup in bytreatment.items():
            try:
                yp,xm=zip(*tup)
                fig=pyplt.figure()
                fig.suptitle(trt)
                pyplt.axis([0.0, 3.5, 0.0, 3.0])
                pyplt.ylabel('platedmass')
                pyplt.xlabel(versus)
                pyplt.scatter(xm,yp)
                fig.savefig("platedmass vs {} {}.{}"
                            .format(versus,trt,
                                    Locations.graphicstype))
                pyplt.show()
            except:
                LOG.error("couldn't plot platedmasses for treatment {}"
                          .format(trt))
        return bytreatment

    def yield_records(self):
        for rec in self:
            yield rec

    def output_to_rQTL(self,*args,**kwargs):
        """
        args are one or more PhenotypeCalculators, each one generating a
        column in the resulting rQTL file

        If kwarg averagereplicates is True, then this effect is applied last
        """
        return rQTLinputReader.create_from_object(self,*args,**kwargs)
#
class ControlledReading(CombiReading):
    tableclassstring="ControlledReadings"
    slots=[ControlledReadingID,ControlledExperiment,Treatment,
           CombiReading,ControlReadingID,
           Strain,FinalAverage,Ratio,
           ErrorRecord]
    defaultlookup="ControlledReadingID"
    coltype=tbs.StringCol(120)

    def get_parent(self):
        return self["controlledexperiment"]

    def rawmeasuredvaluesminusagar(self):
        """
        ControlledExperiment timevalues may differ from source combifile
        timevalues as ControlledExperiment.create_from_combifiles
        uses intersection function to create combined_timepoints.
        Therefore this function must only return rawmeasuredvaluesminusagar
        from the source CombiReading that match these timepoints
        
        """
        combinedT=self["controlledexperiment"].timevalues()
        sourcecombireading=self["combireading"]
        source_measures=sourcecombireading.rawmeasuredvaluesminusagar()
        source_times=sourcecombireading.timevalues()
        if len(source_times)==len(combinedT):
            return source_measures
        else:
            S="{:.2f}"
            Z=zip(source_times,source_measures)
            lookup={S.format(k):v for k,v in Z}
            return [lookup[S.format(T)] for T in combinedT]

    def is_empty(self):
        return False

    def get_treatment_reading(self):
        return self["combireading"]

    def get_control_reading(self):
        if not hasattr(self,"control_reading"):
            controlCRs=CombiReadings("Controls")
            userCRs=CombiReadings(self.dbasenameroot)
            lookup=self["controlreadingid"].value
            results=controlCRs.query_by_kwargs(readingid=lookup)
            if not results:
                results=userCRs.query_by_kwargs(readingid=lookup)
            if not results:
                LOG.error("can't get control combireading {}".format(lookup))
                return None
            elif len(results)!=1:
                LOG.error("{} control combireadings called {}".format(len(results),
                                                                      lookup))
                return None
            else:
                self.control_reading=results[0]
        return self.control_reading

    def get_treatment_ratio(self,timefocus=16.0,
                            plus_minus=0.5,report=False):
        R=self.get_treatment_reading()
        C=self.get_control_reading()
        
        ra,rn=R.average_about_time(timepoint=timefocus,
                                   plus_minus=plus_minus,
                                   report=report)
        ca,cn=C.average_about_time(timepoint=timefocus,
                                   plus_minus=plus_minus,
                                   report=report)
        if rn==0: LOG.error("reading {} has 0 timepoints in range"
                            .format(R.value))
        if cn==0: LOG.error("controlreading {} has 0 timepoints in range"
                            .format(C.value))
        return ra/ca

    def diagnostics(self):
        warnings=[]
        def WARN(message):
            warnings.append(message)
            LOG.warning(message)
        #check key parameters have been stored
        if not self["finalaverage"].is_valid(): 
            WARN("{} has no finalaverage"
                 .format(self.value))        
        return warnings


class ControlledReadings(DBTable,InMemory):
    _shared_state={}
    tablepath="/controlledreadings"
    recordclass=ControlledReading
#

#FEATURES #####################################################################

class FeatureID(DBuInt64):
    shortheader="fID"
class SGDID(DBString):
    coltype=tbs.StringCol(40)
class SGDdbxref(DBString): pass
class SourceType(DBString):
    coltype=tbs.StringCol(16)
class SGDcategory(DBString):
    coltype=tbs.StringCol(40)
    shortheader="cat"
    colclip=4
class Chromosome(DBuInt8):
    shortheader="chr"
    colclip=2
class FeatureStart(DBuInt64):
    shortheader="fSTA"
class FeatureEnd(DBuInt64):
    shortheader="fEND"
class Score(DBFloat32): pass
class Strand(DBLetter): pass
class Frame(DBLetter): pass
class ParentFeatureID(SGDID):
    shortheader="parent"
class OntologyTerms(DBString):
    shortheader="Ontology"
    colclip=8
class SGDNote(DBString):
    colclip=12
class Gene(DBString):
    coltype=tbs.StringCol(40)
    colclip=10
class GeneAlias(DBString):
    shortheader="galias"
    colclip=10
class ORFClassification(DBString):
    shortheader="oclass"
    colclip=10
    coltype=tbs.StringCol(40)
class GFFSourceFile(DBString):
    shortheader="sfile"
    colclip=10
class GFFSourceDate(DBDateTime):
    shortheader="time"

class Feature(DBRecord):
    """
    Feature information drawn from a GFF file
    """
    slots=[FeatureID,SGDID,SGDdbxref,SourceType,SGDcategory,
           Chromosome,FeatureStart,FeatureEnd,Score,Strand,Frame, #Attributes
           ParentFeatureID,OntologyTerms,SGDNote,Gene,GeneAlias,ORFClassification,
           GFFSourceFile,GFFSourceDate]
    tableclassstring="Features"
    defaultlookup="FeatureID"
    coltype=tbs.UInt64Col()
    nullvalue=np.nan
    strict=False

    def summary(self):
        return "{}:{}-{} ({}) #{}".format(self["chromosome"].value,
                                          self["featurestart"].value,
                                          self["featureend"].value,
                                          self["sgdid"].value,
                                          self.value)

    def yield_overlaps(self,only=["gene"]):
        """
        Returns all Features on the same chromosome
        which overlap this one, however narrowly
        """
        tab=self._get_table()
        ST,EN=self["featurestart"].value,self["featureend"].value
        for f in tab.get(chromosome=self["chromosome"].value):
            if only and f["sgdcategory"].value not in only:
                continue
            fST,fEN=f["featurestart"].value,f["featureend"].value
            if ST<=fST<=EN:
                yield f
            elif ST<=fEN<=EN:
                yield f
            elif fST<=ST<=EN<=fEN:
                yield f

    def get_cumulative_startend(self):
        c=self["chromosome"].value
        additive=get_chrcumulative()[c]
        ST,EN=self["featurestart"].value,self["featureend"].value
        return float(ST+additive),float(EN+additive)

class Features(DBSharedTable,InMemory):
    tablepath="/features"
    recordclass=Feature

    def populate(self,sourcefilename="saccharomyces_cerevisiae.gff",
                 store=True):
        filepath=os.path.join(Locations()["genotypes"],sourcefilename)
        if not os.path.exists(filepath):
            LOG.error("Can't find {}".format(filepath))
            return
        LOG.info("populating Features() from {}".format(filepath))
        timestamp=os.path.getctime(filepath)
        RD=GFFReader(filepath)
        sd,rd=RD.parse()
        tostore=[]

        def process_chromosome(chrstring):
            if chrstring.lower().startswith("chr"):
                chrstring=chrstring[3:]
            if chrstring=="mt":
                return 0
            return fromRoman(chrstring)

        for row in rd:
            F=Feature(featureid=row["rownumber"],
                      sgdid=row.get("ID",None),
                      sgddbxref=row.get("dbxref",None),
                      sourcetype=row.get("source",None),
                      sgdcategory=row.get("feature",None),
                      chromosome=process_chromosome(row.get("chromosome",None)),
                      featurestart=row.get("start",None),
                      featureend=row.get("end",None),
                      score=row.get("score",None),
                      strand=row.get("strand",None),
                      frame=row.get("frame",None),
                      parentfeatureid=row.get("Parent",None),
                      ontologyterms=row.get("Ontology_term",None),
                      sgdnote=row.get("Note",None),
                      gene=row.get("gene",None),
                      genealias=row.get("Alias",None),
                      orfclassification=row.get("orf_classification",None),
                      gffsourcefile=filepath,
                      gffsourcedate=timestamp)
            tostore.append(F)
        if store:
            self.store_many_record_objects(tostore,check=False)
        return tostore

#QTLS #########################################################################
class QTLID(DBuInt64): pass

class QTLFilepath(Filepath):
    shortheader="file"
    colclip=5

class PhenotypeColumn(DBString):
    coltype=tbs.StringCol(30)
    shortheader="phenocol"
    colclip=8

class GenotypeGroup(DBString): #AlleleSet
    coltype=tbs.StringCol(12)
    shortheader="gengrp"
    colclip=7

class FeaturePeak(FeatureStart):
    shortheader="fPK"

class FeatureStartCM(DBFloat32):
    shortheader="fSTA_cm"

class FeatureEndCM(DBFloat32):
    shortheader="fEND_cm"

class FeaturePeakCM(DBFloat32):
    shortheader="fPK_cm"

class FeatureList(DBString):
    coltype=tbs.StringCol(10000)
    shortheader="features"
    
    colclip=10

class ScoreThreshold(Score):
    shortheader="thresh"
    colclip=8

class Methodology(DBString):
    colclip=10

class LODscore(DBFloat32):
    shortheader="LOD"
    colclip=5

class Chromosome(DBuInt8):
    shortheader="chr"
    colclip=5

#
class QTL(DBRecord):
    """
    This QTL object is designed to be a flexible
    container for QTL information from multiple sources
    so must handle QTLs that have a single vague locus or
    a more defined extent, and store all key info.
    If a start is defined but no end then the start
    is treated as the centre of the QTL region.
    
    
    File
    Phenotype
    QTL Name
    Chromosome
    Peak LOD
    LOD Threshold
    alpha
    Interval Type
    Start (cM)
    Peak (cM)
    End (cM)
    Start (bp)
    Peak (bp) ##<<
    End (bp)
    Features

    """
    slots=[QTLID,QTLFilepath,
           ControlledExperiment,CombiFile,Treatment,PlateLayout,
           PhenotypeColumn,GenotypeGroup,
           Chromosome,FeatureStart,FeatureEnd,FeaturePeak,
           FeatureStartCM,FeatureEndCM,FeaturePeakCM,
           FeatureList,
           Score,ScoreThreshold,
           Methodology]
    tableclassstring="QTLs"
    defaultlookup="QTLID"

    def get_cumulative_startend(self):
        c=self["chromosome"].value
        additive=get_chrcumulative()[c]
        ST,EN=self["featurestart"].value,self["featureend"].value
        return float(ST+additive),float(EN+additive)

    def is_point(self):
        if self["featureend"].value==0:
            return True

    def get_cumulative_point(self):
        c=self["chromosome"].value
        additive=get_chrcumulative()[c]
        ST=self["featurestart"].value
        return float(ST+additive)

class QTLs(DBTable,InMemory):
    tablepath="/qtls"
    recordclass=QTL
    #qtldirectory="rQTL input"
    qtldirectory="testrQTLinput"

    def get_sets(self,
                 groupby=["treatment","combifile","genotypegroup"],
                 report=True):
        """
        Sorted into dictionary of dictionaries matching groupby
        e.g. {PLATELAYOUT1:{TREATMENT:FeatureSet(with colorby variable)},
              PLATELAYOUT2:{TREATMENT:FeatureSet(with colorby variable)}}
        """
        def list_to_dict(inputlist,quality):
            output={}
            for item in inputlist:
                try:
                    k=ATOMORNOT(item[quality])
                    if k not in output:
                        output[k]=[]
                    output[k]+=[item]
                except Exception as e:
                    LOG.error("Can't find quality {} in item {} because {} {}"
                              .format(quality,item,e,get_traceback()))
            return output

        starterdict=list_to_dict(self,groupby[0])

        def apply_list_to_dict_recursively(inputdict,qualitylist):
            """
            Get dict like {"A":[x,x,x,x,x],
                           "B":[y,y,y,y,y]}
            then turn each list into a dict based on first quality in qualitylist:
            {"A":{"1":[x,x],
                  "2":[x,x,x]},
             "B":{"1":[y,y,y],
                  "2":[y,y]}}
            and so on for each list until not more qualities in qualitylist
            """
            
            if not qualitylist:
                return inputdict
            if type(inputdict)!=dict or not inputdict:
                return inputdict
            q,qualitylist2=qualitylist[0],qualitylist[1:]
            output={}
            for k,v in inputdict.items():
                if v:
                    dictoflist=list_to_dict(v,q)
                    if qualitylist2:
                        dictoflist=apply_list_to_dict_recursively(dictoflist,
                                                                  qualitylist2)
                    output[k]=dictoflist
                else:
                    output[k]=v
            return output

        output=apply_list_to_dict_recursively(starterdict,groupby[1:])

        def display_nested_dict(inputdict,tabcount=0):
            if type(inputdict)!=dict:
                print "\t"*tabcount,len(inputdict),"ITEMS"
                return
            else:
                for k,v in inputdict.items():
                    print "\t"*tabcount,k,len(v)
                    display_nested_dict(v,tabcount+1)

        if report is True:
            display_nested_dict(output)
        
        return output

    def yield_nested_dict_breakdown(self,nesteddict,keys=[],stoplevel=2):
        for k,v in nesteddict.items():
            if stoplevel-1==0 or type(v)!=dict:
                yield keys+[k],v
            else:
                for K,V in self.yield_nested_dict_breakdown(v,
                                                            keys=keys+[k],
                                                            stoplevel=stoplevel-1):
                    yield K,V

    def plot_by(self,
                groupby=["treatment","genotypegroup"],
                #groupby=["treatment","genotypegroup","combifile"],
                ignorephenotypesbeginningwith=["AWA"],
                report=True,
                **kwargs):
        """
        Each level of groupby gets a separate plot,
        except the final groupby which is separately coloured
        """
        counter=0
        GS=self.get_sets(groupby=groupby,report=False)
        FN=self.yield_nested_dict_breakdown
        DBNR=self.dbasenameroot
        folder="{}_QTL plots by {}".format(DBNR,",".join(groupby))
        folderpath=os.path.join(Locations().rootdirectory,
                                "rQTL output",
                                folder)
        extension=kwargs.get("extension",Locations.graphicstype)
        for headers,qtldict in FN(GS,stoplevel=len(groupby)-1):
            titleformat="_".join(["{}" for r in range(len(headers)+1)])
            title=titleformat.format(self.dbasenameroot,*headers)
            savepath=os.path.join(folderpath,title+"."+extension)
            
            xs,ys,cs=[],[],[]
            ms,mcs=[],[]
            markercount=0
            for groupname,qtllist in qtldict.items():
                qtllist2=[]
                for ignore in ignorephenotypesbeginningwith:
                    for q in qtllist:
                        if not q["phenotypecolumn"].value.startswith(ignore):
                            qtllist2.append(q)
                    qtllist=qtllist2
                if not qtllist:
                    continue
                qset=FeatureSet(qtllist)
                if qset.are_points():
                    MXYS=qset.generate_markerxys()
                    ms+=MXYS
                    mcs+=[str(markercount)]*len(MXYS)
                    markercount+=1
                else:
                    y,x=qset.generate_xys()
                    if x:
                        xs.append(x)
                        ys.append(y)
                        cs.append(groupname)
            if xs:
                if mcs:
                    if len(mcs)==1:
                        mcs='yellow'
                    else:
                        inker2=Inker(mcs)
                        mcs=inker2.colors
                CurvePlot(timevalues=ys, #xvalues
                          measurements=xs, #yvalues
                          colorvalues=cs,
                          extension=extension,
                          extramarkers=ms,
                          extramarkercolorvalues=mcs,
                          ybounds=(0,15),
                          xbounds=(0,12071326),
                          yaxislabel="Peak LOD",
                          xgridlines=get_chrcumulative().values(),
                          xaxislabel="bp",
                          title=title,
                          legendloc='upper center',
                          legendcol=6,
                          savepath=savepath,
                          show=False)

#
class FeatureSet(object):
        
    def __init__(self,featurelist,**kwargs):
        self.__dict__.update(kwargs)
        self.featurelist=featurelist
        self.atomdict=combidict(*featurelist)

    def __getitem__(self,key):
        return self.atomdict[key]

    def __len__(self):
        return len(self.featurelist)

    def generate_xys(self):
        if not self.featurelist: return None,None
        xys=[]
        for q in self.featurelist:
            x1,x2=q.get_cumulative_startend()
            y=float(q["score"].value)
            xys+=[(x1,0),(x1,y),(x2,y),(x2,0)]
        return zip(*xys)

    def are_points(self):
        return all([q.is_point() for q in self.featurelist])

    def generate_markerxys(self):
        if not self.featurelist: return None,None
        xys=[]
        for q in self.featurelist:
            x1=q.get_cumulative_point()
            y=float(q["score"].value)
            xys+=[(x1,y)]
        return xys

    def plot(self):
        xs,ys,cs=[],[],[]
        y,x=self.generate_xys()
        if x:
            xs.append(x)
            ys.append(y)
            cs.append(self.genotypegroup)
            if xs:
                title="{}_{}.{}".format(self.controlledexperiment.dbasenameroot,
                                        self.treatment,
                                        Locations.graphicstype)
                savepath=os.path.join(Locations().rootdirectory,
                                      "rQTL output",
                                      title)
                savepath=os.path.normpath(savepath)
                CurvePlot(timevalues=ys, #xvalues
                          measurements=xs, #yvalues
                          colorvalues=cs,
                          ybounds=(0,15),
                          xbounds=(0,12071326),
                          yaxislabel="Peak LOD",
                          xgridlines=get_chrcumulative().values(),
                          xaxislabel="bp",
                          title=title,
                          savepath=savepath,
                          show=True)
        """
                 labels=[qset.qtls],
                 title=None,
                 titleloc='left',
                 titlefontsize=11,
                 savepath=None,
                 extension="jpg",
                 copyto=None,
                 show=False,
                 figsize=(15,10),

                 xbounds=None,     #work out from timevalues
                 ybounds=(0,3.0),  #standard measurement range
                 colorscheme='rainbow',
                 colorschemebounds=(0,1),
                 backgroundcolor='white',
                 xaxislabel='time (hrs)',
                 yaxislabel='',
                 axislabelfontsize=10,
                 xaxisscale='linear', #could be 'log' or 'symlog'
                 yaxisscale='linear', #could be 'log' or 'symlog'
                 
                 labelfontsize=None,
                 labelfontcolor='grey',
                 labelfontalpha=1.0,
                 labelcount=20,
                 labelcutoffpercentiles=None,
                 labelbandstart=0.14,
                 labelbandheight=0.5,
                 legendlabel='',
                 legendloc='lower right',
                 legendfontsize=7,
                 legendfontcolor='black',
                 invertcolorbar=False,
                 **kwargs):
        """
#
def treatment_ratio_comparator(reading,controlreading,timefocus=16.0,
                               plus_minus=0.5,report=False):
    R=reading
    C=controlreading
    
    ra,rn=R.average_about_time(timepoint=timefocus,
                               plus_minus=plus_minus,
                               report=report)
    ca,cn=C.average_about_time(timepoint=timefocus,
                               plus_minus=plus_minus,
                               report=report)
    if rn==0: LOG.error("reading {} has 0 timepoints in range"
                        .format(R.value))
    if cn==0: LOG.error("controlreading {} has 0 timepoints in range"
                        .format(C.value))
    return ra/ca

def printall():
    for t in [Locations(),Plates(),Wells(),PlateLayouts(),Strains(),
              Files(),Readings(),CombiFiles(),CombiReadings()]:
        print t
        print

def average_replicate_timepoints(rowdata):
    """
    function FN to be fed to CombiFiles().output_to_rQTL with replicate_fn kwarg,
    e.g. CombiFiles().output_to_rQTL(replicate_fn=average_replicate_timepoints)
    each row should be a dict with headers "phenotyperow","strain","genotyperow","record"
    but strain and genotyperow should be the same for all rows
    """
    strain=rowdata[0]["strain"]
    genotypes=rowdata[0]["genotyperow"]
    phenotyperows=[row["phenotyperow"] for row in rowdata]
    phenotyperow=[sum(col)/float(len(phenotyperows))
                  for col in zip(*phenotyperows)]
    return {"phenotyperow":phenotyperow,
            "strain":strain,
            "n_replicates":len(rowdata),
            "genotyperow":genotypes}
#
def update(**kwargs):
    DBase.autobackup=True
    Files().update(**kwargs)
    #PlateLayouts().update(**kwargs)
    CombiFiles().update(**kwargs)
    CombiFiles().analyze(**kwargs)
    #ControlledExperiments().update(**kwargs)
    #ControlledExperiments().analyze(**kwargs)

def output_extremes_to_stinger(*args,**kwargs):
    """
    Generates a Stinger instruction file which will pick the most and least successful
    strains based on the readings or CombiFiles listed in args.
    It will then generate Stinger instruction file(s) for rearraying these on new plate(s).
    If targetfile is specified (a StingerReader object)
    then this instruction file will merge with that one and not overwrite it.
    Compares measurements by simply summing them, and takes replicates into account
    by summing the sum of measurements from all replicates
    """
    global readings
    readings=[]
    sources=[]
    titles=[]
    subfolders=[]
    platelayouts=[]
    treatments=[]
    for a in args:
        if type(a)==CombiFile:
            readings+=a.sorted_readings()
            sources+=[a]
            titles+=[a.get_title()]
            subfolders+=[a.get_subfoldername()]
            if a["platelayout"] not in platelayouts:
                platelayouts+=[a["platelayout"]]
            if a["treatment"] not in treatments:
                treatments+=[a["treatment"]]
        elif type(a)==list:
            for r in a:
                assert type(r) in [Reading,CombiReading]
                readings.append(r)
                RC=r["combifile"]
                if RC not in sources:
                    sources+=[RC]
                T=RC.get_title()
                if T not in titles:
                    titles+=[T]
                SFP=RC.get_subfoldername()
                if SFP not in subfolders:
                    subfolders+=[SFP]
                if r["platelayout"] not in platelayouts:
                    platelayouts+=[r["platelayout"]]
                if r["treatment"] not in treatments:
                    treatments+=[r["treatment"]]

    rootname="+".join([s["combifileid"].value for s in sources])
    fulldescriptor="{}_({})".format(",".join([os.path.splitext(l.value)[0]
                                              for l in platelayouts]),
                                    ",".join([t.value for t in treatments]))
    filepaths=[os.path.join(f,fulldescriptor) for f in subfolders]
    strainnames=[r["strain"].value for r in readings]
    summeasuredvalues=[r.summeasuredvalues() for r in readings]
    maximumchanges=[r["maximumchange"] for r in readings]

    #for a,b,c in zip(strainnames,summeasuredvalues,maximumchanges):
    #    print a,b,c
    
    #Histogram numbers
    for t,f,s in zip(titles,filepaths,subfolders):
        sp1=Histogram(source=summeasuredvalues,
                      ylabel="Sum of measured values",
                      titleprefix="{} Histogram of sum of measured values".format(rootname),
                      title=t,
                      maxy=60.0,
                      miny=0.0,
                      titlesuffix=fulldescriptor,
                      save=False,
                      subdirectory=Locations().get_plotspath(),
                      subfolder=s)
        sp2=Histogram(source=maximumchanges,
                      ylabel="Maximum changes",
                      titleprefix="{} Histogram of maximum changes".format(rootname),
                      title=t,
                      maxy=3.0,
                      miny=0.0,
                      titlesuffix=fulldescriptor,
                      save=False,
                      subdirectory=Locations().get_plotspath(),
                      subfolder=s)

    #NOW extract calculate total summeasuredvalues for each strain (sum replicates)
    strainlookup=defaultdict(list)
    for rd in readings:
        #print rd,rd["strain"].value
        strainlookup[rd["strain"].value].append(rd)
    #
    kwargs.setdefault("separatetargets",True)
    kwargs.setdefault("targetcapacity",384)
    #
    kwargs.setdefault("totalstrains",len(strainlookup))
    kwargs.setdefault("toppercentile",0.05)
    kwargs.setdefault("toptotal",
                      int(kwargs["totalstrains"]*kwargs["toppercentile"]))
    kwargs.setdefault("bottompercentile",kwargs["toppercentile"])
    kwargs.setdefault("bottomtotal",
                      int(kwargs["totalstrains"]*kwargs["bottompercentile"]))
    LOG.info("PICKING BIGGEST {toptotal} AND SMALLEST {bottomtotal} "
             "COLONIES FROM {totalstrains} TOTAL STRAINS"
             .format(**kwargs))
    kwargs.setdefault("replicates","as original")
    #kwargs.setdefault("targetfile",StingerReader())
    summedreplicates=sorted([(sum([r.summeasuredvalues() for r in v]),v[0]) for v in strainlookup.values()])
    SRX=[y for x,y in summedreplicates[::-1]]
    #
    topreadings=SRX[:kwargs["toptotal"]]
    bottomreadings=SRX[-kwargs["bottomtotal"]:]
    #


    #Rootname derived from all CombiFileIDs included, e.g. TS7ab+TS5ab (not layout names)
    #Top set go into new layout <rootname>+"_top_"+N
    #Bottom set go into new layout <rootname>+"_bottom_"+N
    #Each layout gets a stinger instruction file named with source and target layouts



    if kwargs["separatetargets"]:
        targetplate=Plates().get(capacity=kwargs["targetcapacity"])
        
        toplayoutstring=rootname+"_top_{}".format(len(topreadings))
        toplayout=PlateLayout.create(topreadings,
                                     plate=targetplate,
                                     layoutstring=toplayoutstring)
        toplayout.draw(save=False,show=True)
        
        bottomlayoutstring=rootname+"_bottom_{}".format(len(bottomreadings))
        bottomlayout=PlateLayout.create(bottomreadings,
                                        plate=targetplate,
                                        layoutstring=bottomlayoutstring)
        bottomlayout.draw(save=False,show=True)

        #stingerfile=StingerReader.create_from_layouts(sources=sources,
        #                                                     targets=[toplayout,bottomlayout],
        #                                                     write=True)

    with open("templist.txt","w") as fo:
        fo.write("TOP\n")
        for tr in topreadings:
            fo.write("{}\t{}\n".format(tr.summeasuredvalues(),tr))
        fo.write("BOTTOM\n")
        for br in bottomreadings:
            fo.write("{}\t{}\n".format(br.summeasuredvalues(),br))
        LOG.info("SAVED TEMPLIST.TXT")

#
def read_qtl_digest(path=None,store=True):
    if path is None:
        path=browse(startingdirectory=os.path.join(Locations().rootdirectory,
                                                   "rQTL output"))
        LOG.info("Opening "+path)
    RD=rQTLoutputdigestReader(path)
    sd,rd=RD.parse()
    headers=sd["headers"]
    nqtls=sd["nqtls"]
    LOG.info("Found {} nqtls in {}"
             .format(nqtls,path))
    tostore=[]
    checkfirst=True
    QTLS=QTLs()
    lastqtlcount=len(QTLS)
    for i,row in enumerate(rd):
        """
        [u'File', u'End (cM)', u'Interval Type', u'LOD Threshold', u'End (bp)', u'Features', u'Phenotype', u'QTL Name', u'Peak (cM)', u'alpha', u'Start (cM)', u'Peak LOD', u'Chromosome', u'Start (bp)']
        """
        NRD=rQTLFileNameReader2(row["File"])
        if not NRD.properties:
            LOG.error("couldn't parse filename {}"
                      .format(row["File"]))
            continue
        PROP=NRD.properties
        Q=QTL(qtlid=lastqtlcount+i,
              qtlfilepath=path,
              controlledexperiment=PROP.get("controlledexperimentid",None),
              combifile=PROP.get("combifile",None),
              treatment=PROP.get("treatment",None),
              platelayout=PROP.get("layout",None),
              phenotypecolumn=row["Phenotype"],
              genotypegroup=PROP.get("genotypegroup",None),
              chromosome=row["Chromosome"],
              featurestart=row["Start (bp)"],
              featureend=row["End (bp)"],
              featurepeak=row.get("Peak (bp)",None),
              featurestartcm=row["Start (cM)"],
              featureendcm=row["End (cM)"],
              featurepeakcm=row["Peak (cM)"],
              featurelist=row["Features"],
              score=row["Peak LOD"],
              scorethreshold=row["LOD Threshold"],
              methodology="{Interval Type} {alpha}".format(**row))
        tostore.append(Q)
    if store:
        QTLS.store_many_record_objects(tostore,check=False)
        LOG.info("Stored {} QTL objects".format(len(tostore)))
    return tostore
#

def plot_features(featurenamelist,colorlist=None):
    extension=Locations.graphicstype
    order=[] #[chr,start,ys,xs,cols,lbs]
    #ys,xs,cols,lbs=[],[],[],[]
    for fn,cn in zip(featurenamelist,colorlist):
        featurelist=Features().query_by_kwargs(gene=fn)
        if not featurelist:
            continue
        FS=FeatureSet(featurelist)
        y,x=FS.generate_xys()
        x2=[]
        for xv in x:
            if str(xv)=='nan':
                x2.append(0.5)
            else:
                x2.append(xv)
        order.append([featurelist[0]["chromosome"].value,
                      featurelist[0]["featurestart"].value,
                      list(y),
                      x2,
                      cn,
                      featurelist[0]["gene"].value])
    order.sort()
    ys,xs,cols,lbs=[],[],[],[]
    for o in order:
        print o[0],o[1],o[5]
        ys.append(o[2])
        xs.append(o[3])
        cols.append(o[4])
        lbs.append(o[5])

    cp=CurvePlot(timevalues=ys, #xvalues
                 measurements=xs, #yvalues
                 colorvalues=cols,
                 labels=lbs,
                 extension=extension,
                 ybounds=(0,1),
                 xbounds=(0,12071326),
                 yaxislabel="",
                 xgridlines=get_chrcumulative().values(),
                 xaxislabel="bp",
                 title=str(lbs),
                 legendloc='upper center',
                 savepath=None,
                 show=True)

#AUTOCURATOR ##################################################################
class Autocurator(object):
    def __init__(self):
        self.tests=[self.check_timevalues,
                    self.check_printedmass_spread,
                    self.check_printedmass_geography,
                    self.check_maximumchange_spread,
                    self.check_maximumchange_geography,
                    self.check_blanks_and_growth]
        for CF in CombiFiles():
            print CF

    def check_timevalues(self,ob):
        return ob["timespan"].is_sufficient(fortext="for Autocurator")

    def get_values(self,valuestring,ob):
        X="list_"+valuestring
        if not hasattr(ob,X):
            lst=[ATOMORNOT(rec[valuestring])
                 for rec in ob.yield_records()]
            setattr(ob,X,lst)
        return getattr(ob,X)

    def get_platedmasses(self,ob):
        return self.get_values("platedmass",ob)

    def get_maximumchanges(self,ob):
        return self.get_values("maximumchange",ob)

    def get_distancesfromedge(self,ob):
        return self.get_values("distancefromedge",ob)

    def get_distancesfromcenter(self,ob):
        return self.get_values("distancefromcenter",ob)

    def get_distancesfromleft(self,ob):
        return self.get_values("wellx",ob)

    def get_distancesfromtop(self,ob):
        return self.get_values("welly",ob)
#
    def is_normal_distribution(self,values):
        pass

    def is_correlated(self,pairedvalues):
        pass
#
    def check_printedmass_spread(self,ob):
        pass

    def check_printedmass_geography(self,ob):
        pass

    def check_maximumchange_spread(self):
        pass

    def check_maximumchange_geography(self):
        pass

    def check_blanks_and_growth(self):
        pass


#

def sample_curveanalyses(n=30):
    CR=CombiReadings()
    rds=list(CR.yield_records())
    shuffle(rds)
    testcrs=rds[:50]
    for cr in testcrs:
        print cr
        cr.plot(show=True,savepath=False)

#MAIN #########################################################################
if __name__=='__main__':
    setup_logging("INFO")#CRITICAL")
    sys.excepthook=log_uncaught_exceptions

    #Data from http://www.yeastgenome.org/search?q=paraquat&is_quick=true
#    paraquatresistancedecreased=['CCS1','FRS2','IRA2','NAR1','POS5','PUT1','RNR4','SOD1','SOD2','UTH1']
#    paraquatresistanceincreased=['PUT1','TPO1']
#    paraquatresistancenormal=['CCS1','SOD1']
#    feats=['CCS1','FRS2','IRA2','NAR1','POS5','PUT1','RNR4','SOD1','SOD2','UTH1','TPO1']
#    cols=['black','red','red','red','red','black','red','black','red','red','green']
    #plot_features(feats,cols)
    #