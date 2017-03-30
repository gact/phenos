#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-

#STANDARD LIBRARY
import os,sys,time,shutil,subprocess
import logging,platform,ConfigParser,traceback
import numpy as np
from itertools import chain
from math import e
from collections import defaultdict
#OTHER
from matplotlib import use as mpluse
mpluse('PS')
import matplotlib.pyplot as pyplt
import win32com.client


# #############################################################################

filename = os.path.basename(__file__)
authors = ("David B. H. Barton")
version = "2.7"

LOG=logging.getLogger()

#

#UTILITY LAMBDAS ##############################################################

#flattens a nested list, e.g. flatten([[1,2],[3,4]]) returns [1,2,3,4]
flatten=lambda nested: list(chain.from_iterable(nested))

#combines two pairs of timepoints & measurements and returns in timepoint
#order e.g.
#  tzip([0,2],[30,40],[1,7],[35,100]) returns [(0,1,2,7),(30,35,40,100)]
tzip=lambda t1,m1,t2,m2: zip(*sorted(zip(t1,m1)+zip(t2,m2)))

ATOMORNOT=lambda(aon): getattr(aon,"value",aon)

def cellcount_estimate(rawmeasuredminusagar):
    """
    log10(P)=0.7625(A)+4.8914
    P=77875.3e(1.75572A)
    Determined empirically using cell counts
    and least squares curve fitting
    """
    A=rawmeasuredminusagar
    return 77875.3*e**(1.75572*A)

def calc_slope(measures,timepoints):
    """
    The average slope of the measures and timepoints, averaged across every difference
    in the set provided to avoid problems with noisy data
    """
    try:
        mD=delta_series(measures,k=2)
        tD=delta_series(timepoints,k=2)
        allslopes=[m/float(t) for m,t in zip(mD,tD)]
        return sum(allslopes)/len(allslopes)
    except Exception as e:
        LOG.error("Can't calculate slope for {}/{}"
                  "because {} {}".format(str(measures),str(timepoints),e,get_traceback()))
        return None

def calc_lag(slope,measureinflection,minimum,timeinflection):
    """
    Taking the slope at the inflection point (the steepest part
    of the curve), and tracing that slope back until it reaches
    the value of the minimum measurement, gives the lag time.
    """
    if not slope:
        return None
    try:
        measureinflectionchange=measureinflection-minimum
        timeoflinescrossing=measureinflectionchange/slope
        timeofslopecrossingminimum=timeinflection-timeoflinescrossing
    except Exception as e:
        LOG.error("Can't calculate lag for slope {}, measureinflection {}, "
                  "minimum {}, timeinflection {} "
                  "because {} {}".format(slope,measureinflection,
                                         minimum,timeinflection,
                                         e,get_traceback()))
        return None
    if np.isinf(timeofslopecrossingminimum): return None
    return timeofslopecrossingminimum

def calc_inflection(measurements,timevalues,smoothing=15):
    output={}
    M=output["M"]=measurements
    C=output["C"]=[cellcount_estimate(m) for m in M]
    T=output["T"]=timevalues
    minint,maxint=intervals(T)
    if maxint-minint>2.0 or minint<0.1 or maxint>3.0:
        LOG.warning("minimum interval = {}, maximum interval = {}:"
                    " uneven timepoints , therefore aborting "
                    "calculations early".format(minint,
                                                maxint))
        return output
    sM=output["sM"]=smooth_series(M,k=smoothing)
    sT=output["sT"]=smooth_series(T,k=smoothing)
    DsM=output["DsM"]=delta_series(sM)
    DsT=output["DsT"]=smooth_series(sT,k=2)
    if not DsM:
        LOG.warning("smoothed measurements don't give valid delta "
                    "values, therefore aborting "
                    "calculations early")
        return output
    sDsM=output["sDsM"]=smooth_series(DsM,k=2)
    sDsT=output["sDsT"]=smooth_series(DsT,k=2)
    #sDsMpeakI=output["sDsMpeakI"]=find_first_peak(sDsM)
    sDsMpeakI=output["sDsMpeakI"]=sDsM.index(max(sDsM))
    if not sDsMpeakI:
        LOG.warning("not getting valid sDsMpeakI therefore aborting "
                    "calculations early")
        return output
    sDsMpeakM=output["sDsMpeakM"]=sDsM[sDsMpeakI]
    sDsTpeakT=output["sDsTpeakT"]=sDsT[sDsMpeakI]
    iMTi=output["iMTi"]=closest_index(T,sDsTpeakT)
    inflectionT=output["inflectionT"]=T[iMTi]
    inflectionM=output["inflectionM"]=M[iMTi]
    #take segment of line surrounding inflection point and
    slopewindow=4
    leftindex=iMTi-slopewindow
    rightindex=iMTi+slopewindow
    Msub=M[leftindex:rightindex+1]
    Csub=C[leftindex:rightindex+1]
    Tsub=T[leftindex:rightindex+1]
    
    #print "1: {} ({}) @ {}".format(M1,C1,T1)
    #print "2: {} ({}) @ {}".format(M2,C2,T2)
    maxslope=output["maxMslope"]=calc_slope(Msub,Tsub)
    Cslope=output["maxCslope"]=calc_slope(Csub,Tsub)
    minminusagar=min(M)
    maxchange=max(M)-minminusagar
    #slopeC=cellcount_estimate(self.slope)
    #print "MI {}, TI {}".format(self.measureinflection,
    #                            self.timeinflection)
    #print "Slopes {} ({})".format(self.slope,Cslope)#,slopeC)
    lagtime=output["lagtime"]=calc_lag(maxslope,inflectionM,
                                       minminusagar,inflectionT)
    #print "lag {} hrs".format(self.lag)
    halfmaxchange=maxchange/2.0
    halfmaxchangeindex=closest_index(M,halfmaxchange)
    halfpeaktime=output["halfpeaktime"]=T[halfmaxchangeindex]
    return output

def doubling_time(slope):
    """
    NOT YET IMPLEMENTED
    slope (change_in_rawmeasuredvalueminusagar / change_in_time)
    """
    cellcountslope=cellcount_estimate(slope)

def get_kmer_list(iterable,k=2):
    """reduces len of iterable by k-1"""
    return [iterable[x:x+k] for x in range(len(iterable)+1-k)]

def intervals(values,upto=False):
        if upto:
            values=values[:upto]
        intervals=[y-x for x,y in get_kmer_list(values,k=2)]
        return min(intervals),max(intervals)

def smooth_series(iterable,k=2):
    """reduces len of iterable by k-1"""
    avg=lambda L:float(sum(L))/k
    return [avg(i) for i in get_kmer_list(iterable,k=k)]

def antimirror_before_zero(iterable):
    """
    to avoid problems with slope-finding algorithm,
    any initial dips in the curve are replaced with negative mirrors of the readings
    after the zero, provided that the zero occurs within the first half of the sequence
    """
    zeroindex=iterable.index(0.0)
    if zeroindex>len(iterable)/2.0:
        return iterable
    segment_to_antimirror=iterable[zeroindex+1:(zeroindex*2)+1]
    negatives=[-v for v in segment_to_antimirror[::-1]]
    return negatives+iterable[zeroindex:]

def delta_series(iterable,k=2):
    delta=lambda L:L[-1]-L[0]
    return [delta(i) for i in get_kmer_list(iterable,k=k)]

def find_first_peak(iterable):
    lv=-100000
    for i,v in enumerate(iterable):
        if v<=lv: return i-1
        lv=v

def get_chrcumulative():
    """
    Returns dictionary of bp additions to be added to bp coordinates
    of features on a given chromosome to tranform them into genome-wide
    coordinates.
    Used by graphics.py when plotting QTLs/Features along
    the length of the whole genome
    >>> print get_chrcumulative()[3]
    1043402
    """
    if "chrcumulative" in globals():
        return globals()["chrcumulative"]
    else:
        global chrcumulative
        chrcumulative={}
        chrlengths={1:230218,
                    2:813184,
                    3:316620,
                    4:1531933,
                    5:576874,
                    6:270161,
                    7:1090940,
                    8:562643,
                    9:439888,
                    10:745751,
                    11:666816,
                    12:1078177,
                    13:924431,
                    14:784333,
                    15:1091291,
                    16:948066}
        keys=sorted(chrlengths.keys())
        for i,c in enumerate(keys):
            previouschrs=keys[:i]
            chrcumulative[c]=sum([chrlengths[x] for x in previouschrs])
        return chrcumulative

def display_image(filepath,**kwargs):
    size=kwargs.setdefault("size",(18,12))
    im = pyplt.imread(filepath)
    fig, ax = pyplt.subplots(figsize=size)
    implot = ax.imshow(im,aspect="auto")
    pyplt.axis('off')
    pyplt.show()
    pyplt.close()

def sorter(iterable,operationfunction):
    dd=defaultdict(list)
    for each in iterable:
        dd[operationfunction(each)].append(each)
    return dd

def fromRoman(romannumeralstring):
    """
    https://github.com/enthought/Python-2.7.3/blob/master/Doc/tools/roman.py
    """
    romannumeralstring=romannumeralstring.upper()
    romanNumeralMap=(('M', 1000),
                     ('CM',900),
                     ('D', 500),
                     ('CD',400),
                     ('C', 100),
                     ('XC',90),
                     ('L', 50),
                     ('XL',40),
                     ('X', 10),
                     ('IX',9),
                     ('V', 5),
                     ('IV',4),
                     ('I', 1))
    result=0
    index=0
    for numeral,integer in romanNumeralMap:
        while romannumeralstring[index:index+len(numeral)]==numeral:
            result+=integer
            index+=len(numeral)
    return result

def closest_index(lst,value):
    """
    Returns the index of the closest value to 'value' in lst
    """
    return min(range(len(lst)), key=lambda i: abs(lst[i]-value))

def get_indices_around(lst,centervalue,plusminus=0.5):
    output=[]
    for i,v in enumerate(lst):
        if centervalue-plusminus<=v<=centervalue+plusminus:
            output.append(i)
    return output

def indices_to_values(lst,indices):
    return [lst[i] for i in indices]

def get_allnone_mask(list_of_lists):
    """
    returns the indices of every position that is None in every
    sublist. Used to filter out all-None columns from markers and
    alleles
    """
    output=[]
    index=0
    while True:
        try:
            if not any([lst[index] for lst in list_of_lists]):
                output.append(index)
            index+=1
        except IndexError:
            break
    return output

def mask_by_index(lst,indices_to_skip):
    return [v for i,v in enumerate(lst) if i not in indices_to_skip]

def padded_display_from_headers(lst,headers,rowclip=300):
    padblocks=["{"+":^{}".format(len(header)+2)+"}" for header in headers]
    lst=[pad.format(element) for pad,element in zip(padblocks,lst)]
    return "".join(lst)[:rowclip]

def reconcile_dicts(*dicts,**kwargs):
    """
    combines all dicts into one.
    If flag=True then prints errors for each duplicate key
    If flag=False, renames duplicate keys with index of dict in brackets,
    e.g. "key (0)"
         "key (1)"
    But if collapse=True, keys will be combined if the values are the same
    >>> d1={'a':1,'b':2,'c':3,'d':4}
    >>> d2={'a':1,'b':4,'c':3,'D':4}
    >>> print reconcile_dicts(d1,d2,flag=False,collapse=True)
    {'a': 1, 'c': 3, 'd': 4, 'b (1)': 4, 'b (0)': 2, 'D': 4}
    """
    flag=kwargs.pop("flag",True)
    collapse=kwargs.pop("collapse",True)
    #First find duplicate keys
    combineddict={}
    for i,dct in enumerate(dicts):
        for k,v in dct.items():
            if k not in combineddict:
                combineddict[k]=[(i,v)]
            else:
                combineddict[k].append((i,v))
    #Now decide what to do
    output={}
    for k,ivpairs in combineddict.items():
        if len(ivpairs)==1:
            output[k]=ivpairs[0][1]
        else:
            if flag==True:
                LOG.warning("Key '{}' is duplicated: {}"
                            .format(k,dict(ivpairs)))
            values=list(set([v for i,v in ivpairs]))
            if collapse is True and len(values)==1:
                output[k]=values[0]
            else:
                for i,v in ivpairs:
                    output["{} ({})".format(k,i)]=v
    return output

def filterdict(dictionary,keys=[]):
    """
    Returns a dict taken from dictionary but only with the keys in keys
    >>> print filterdict({'a':1,'b':2,'c':3},['a','b'])
    {'a': 1, 'b': 2}
    """
    return {k:v for k,v in dictionary.items() if k in keys}

def scriptdir():
    return os.path.dirname(os.path.realpath(sys.argv[0]))

def chscriptdir():
    os.chdir(scriptdir())

def find_rootdir(searchdir=None):
    if searchdir is None:
        searchdir=os.path.dirname(os.path.realpath(sys.argv[0]))
    rootdir=False
    shutdown=0
    while not rootdir:
        if os.path.exists(os.path.join(searchdir,"Logs")):
            rootdir=searchdir
        else:
            searchdir=os.path.split(searchdir)[0]
            if not searchdir:
                break
        shutdown+=1
        if shutdown>100:
            break
    return rootdir

def get_config_filepath(filename="config.txt"):
    """
    Thanks Tom Walsh for this!
    If the config file doesn't exist at the proper location,
    but does exist in the script directory or level above
    then it will be copied into the proper location.
    A shortcut will also be created.
    """
    platform_system=platform.system()
    configfilename=filename
    if platform_system!='Windows':
        raise RuntimeError("unsupported platform: {!r}".format(platform_system))
    else:
        appdata=os.getenv('APPDATA')
        if appdata is None or not os.path.isdir(appdata):
            raise RuntimeError("%APPDATA% environment variable is invalid or undefined")
        config_filepath=os.path.join(appdata,'PHENOS',configfilename)
        if os.path.exists(config_filepath):
            try:
                LOG.info("Found config file at {}".format(config_filepath))
            except:
                pass
            return config_filepath
        else:
            #LOOK FOR CONFIG IN OR ABOVE SCRIPT DIRECTORY
            setup_config_txt(destinationpath=config_filepath)
        return config_filepath

def get_desktop_dirpath():
    platform_system=platform.system()
    if platform_system!='Windows':
        raise RuntimeError("unsupported platform: {!r}".format(platform_system))
    else:
        return os.path.normpath(os.path.expanduser('~\Desktop'))

def setup_config_txt(destinationpath):
    """
    If necessary, copies filename from above scriptdir to appdata
    folder and creates shortcut from that to the desktop
    """
    appdatadir,filename=os.path.split(destinationpath)
    SCD=scriptdir()
    possible=[os.path.join(SCD,filename),
              os.path.join(os.path.dirname(SCD),filename)]
    foundpath=None
    for P in possible:
        LOG.info("Looking for {}"
                 .format(P))
        if os.path.exists(P):
            foundpath=P
            break
    if foundpath:
        copy_to(foundpath,destinationpath)
        LOG.info("Copied {} from {} to {}"
                 .format(filename,foundpath,destinationpath))
        desktopshortcutpath=os.path.join(get_desktop_dirpath(),
                                         "Shortcut to {}.lnk"
                                         .format(filename))
        create_Windows_shortcut(destinationpath,
                                desktopshortcutpath,
                                report=True)
    else:
        LOG.critical("Can't find {} in {} or {}"
                     .format(filename,foundpath,config_filepath))
        sys.exit()

def get_config_dict():
    CFpth=get_config_filepath()
    CFpars=ConfigParser.SafeConfigParser()
    CFpars.optionxform = str #prevents section header cases from being changed

    def safeget(section,defaultheader,defaultcontent):
        if not CFpars.has_section(section):
            return None
        return CFpars.get(section,defaultheader,defaultcontent)

    def getall(section,default):
        if not CFpars.has_section(section):
            return None
        return dict(CFpars.items(section))
    
    CFpars.read(CFpth)
    def splitcontrols(controlsstring):
        return [c.strip() for c in controlsstring.split(",")]
    
    def splitnumbers(numberstring):
        return tuple([int(n.strip()) for n in numberstring.split(",")])

    def splitvalues(dictionary):
        return {k:[i.strip() for i in v.split(",")]
                for k,v in dictionary.items()}

    output={"config_filepath":CFpth,
            "configparser":CFpars,
            "scriptdirectory":scriptdir(),
            "target_directory":safeget("Locations",
                                       "target_directory",
                                       find_rootdir()),
            "source_directory":safeget("Locations",
                                       "source_directory",
                                       None),
            "user_folder":safeget("Locations",
                                  "user_folder",
                                  "Test"),
            "graphicstype":safeget("Graphics",
                                   "type",
                                   "png"),
            "windowposition":splitnumbers(safeget("GUI",
                                                  "position",
                                                  "800,600,0,0")),
            "controls":splitcontrols(safeget("Controls",
                                             "controls",
                                             "YPD, YPD 30C, "
                                             "COM, COM 30C")),
            "phenotypecalculators":splitvalues(getall("PhenotypeCalculators",
                                                      {"!default":"AverageWithoutAgarAtTimeCalc"})),
            "combifilevisualizations":splitvalues(getall("CombiFileVisualizations",
                                            {"!default":"EmptyPlateView, "
                                             "PrintingQuality, "
                                             "FinalGrowth, Animation_Temp, "
                                             "CurvesWithoutAgar_PrintedMass, "
                                             "CurvesWithoutAgar_Groups, "
                                             "CurvesWithoutAgar_Slopes, "
                                             "CurvesWithoutAgar_Lags, "
                                             "CurvesNormalized_PrintedMass, "
                                             "Histogram_MaxChange, "
                                             "Scatterplot_PlatedMass_Lag, "
                                             "ReplicatePlots"}))}
    if "phenotypecalculators" in output:
        pc2={}
        for k,v in output["phenotypecalculators"].items():
            if k.startswith("!"):
                pass
            elif not k.endswith("$"):
                k=k+"$"
            pc2[k]=v
        output["phenotypecalculators"]=pc2
    return output

def check_and_fix_paths(create_userfolders=True):
    CD=get_config_dict()
    if not os.path.exists(CD["target_directory"]):
        try:
            prepare_path(CD["target_directory"])
        except Exception as e:
            raise RuntimeError("target_directory {} doesn't exist "
                               "and PHENOS can't create it"
                               .format(CD["target_directory"],e,
                               get_traceback()))
    if not os.path.exists(CD["source_directory"]):
        try:
            prepare_path(CD["source_directory"])
            print ("source_directory {} doesn't exist so "
                   "creating it. Ensure microplate reader "
                   "is set up to output to this location"
                   .format(CD["source_directory"]))
        except Exception as e:
            raise RuntimeError("source_directory {} doesn't exist "
                               "and PHENOS can't create it because {} {}"
                               .format(CD["source_directory"],e,
                               get_traceback()))
    fulluserpath=os.path.join(CD["target_directory"],
                              "Data files",
                              CD["user_folder"])
    if not os.path.exists(fulluserpath):
        if create_userfolders:
            try:
                prepare_path(fulluserpath)
            except Exception as e:
                raise RuntimeError("user_folder {} doesn't exist "
                                   "and PHENOS can't create it because {} {}"
                                   .format(fulluserpath,e,get_traceback()))
        else:
            tryfolders=["All","Test","New folder"]
            for tryfolder in tryfolders:
                trypath=os.path.join(CD["target_directory"],
                                     "Data files",
                                     tryfolder)
                if os.path.exists(trypath):
                    CD["user_folder"]=tryfolder
                    return CD
            prepare_path(os.path.join(CD["target_directory"],
                                      "Data files",
                                      tryfolder))
            CD["user_folder"]=tryfolder
    return CD

def yield_subpaths(startpath,dig=True,onlytype="all",includeroot=True):
    if dig:
        for root,dirs,files in os.walk(startpath,topdown=True):
            if not includeroot:
                root=os.path.normpath(root.replace(startpath,''))
                if root.startswith(os.path.sep):
                    root=root[1:]
            if onlytype in ["all","files"]:
                for name in files:
                    yield os.path.join(root,name)
            if onlytype in ["all","dirs"]:
                for name in dirs:
                    yield os.path.join(root,name)
    else:
        for subpath in os.listdir(startpath):
            fullpath=os.path.join(startpath,subpath)
            if not includeroot:
                output=fullpath.replace(startpath,'')
                if output.startswith(os.path.sep):
                    output=output[1:]
            else:
                output=fullpath
            if onlytype in ["files"]:
                if os.path.isfile(fullpath):
                    yield output
            elif onlytype in ["dirs"]:
                if os.path.isdir(fullpath):
                    yield output
            elif onlytype in ["all"]:
                yield output

def examine_path(filepath,clip=260):
    """
    >>> chscriptdir()
    >>> d=examine_path("dbtypes.py")
    >>> print d['extension']
    .py
    >>> print d['filename']
    dbtypes.py
    """
    filepath=os.path.normpath(filepath)
    cwd=os.getcwd()
    directory,filename=os.path.split(filepath)
    filenamebody,extension=os.path.splitext(filename)
    exists=os.path.exists(filepath)
    iscomplete= cwd==filepath[:len(cwd)]
    badchars=set(filename)-set(" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
                               "OPQRSTUVWXYZ0123456789"
                               ".,_+-=;!^~()[]'@&#%$\\/")
    FP=os.path.join(cwd,filepath) if not iscomplete else filepath
    return {"filepath":filepath,
            "length":len(filepath),
            "filenamebody":filenamebody,
            "extension":extension,
            "filename":filename,
            "directory":directory,
            "exists":exists,
            "badchars":list(badchars),
            "isvalid":len(badchars)==0 and len(filepath)<=clip,
            "size":os.path.getmtime(filepath) if exists else None,
            "datemodified":os.path.getsize(filepath) if exists else None,
            "iscomplete":iscomplete,
            "workingdirectory":cwd,
            "fullpath":FP,
            "scriptdirectory":os.path.dirname(os.path.realpath(sys.argv[0]))}

def prepare_path(dpath,report=False):
    """
    creates all necessary subdirectories to ensure that filepath can
    then be created.
    dpath must be a directory.
    """
    if not os.path.exists(dpath):
        try:
            os.makedirs(dpath)
            if report:
                LOG.info("created {}".format(dpath))
            return dpath
        except Exception as e:
            LOG.critical("couldn't create {} because {} {}"
                         .format(dpath,e,get_traceback()))
            return False

def copy_to(filepath,targetpath,report=True):
    """
    N.B. Ensure targetpath exists if it is a directory>
    If it IS a directory, shutil.copy will keep the basename
    of the original filepath
    """
    if not os.path.exists(filepath):
        return False
    prepare_path(os.path.dirname(targetpath))
    shutil.copy(filepath,targetpath)
    if report:
        LOG.info("copy created: {}".format(targetpath))
    return os.path.exists(targetpath)

def copy_contents_to(sourcedirectory,targetdirectory,report=True,
                     ignore=[".lnk"]):
    assert os.path.exists(sourcedirectory)
    prepare_path(targetdirectory)
    for subpath in yield_subpaths(sourcedirectory,dig=True,onlytype="all",
                                  includeroot=False):
        fullsourcepath=os.path.join(sourcedirectory,subpath)
        fulltargetpath=os.path.join(targetdirectory,subpath)
        if os.path.isdir(fullsourcepath):
            prepare_path(fulltargetpath)
        else:
            ext=os.path.splitext(fulltargetpath)[-1]
            if os.path.exists(fulltargetpath):
                LOG.error("already exists: {}".format(fulltargetpath))
            elif ext in ignore:
                LOG.info("ignoring {}".format(fulltargetpath))
            else:
                try:
                    shutil.copy(fullsourcepath,fulltargetpath)
                    if report:
                        LOG.info("copied {} to {}"
                                 .format(fullsourcepath,fulltargetpath))
                except Exception as e:
                    LOG.error("shutil.copy({},{}) failed{} {}"
                              .format(fullsourcepath,fulltargetpath,
                                      e,get_traceback()))

def check_path(filepath,
               replace_bad=True,
               clip_path=True,
               create_directory=True,
               replace_char="~",
               clip=260):
    """
    Paths longer than 260 characters produce errors, so this will check and correct them,
    in addition to doing character replacement and creating directories if needed
    
    """
    filepath=os.path.normpath(filepath)
    check=examine_path(filepath,clip=clip)
    if check["badchars"]:
        if replace_bad:
            for char in check["badchars"]:
                check["filename"]=check["filename"].replace(char,replace_char)
                check["filepath"]=os.path.join(check["directory"],
                                               check["filename"])
        else:
            return False
    if check["length"]>clip:
        if clip_path:
            LOG.debug(check["extension"])
            clip=clip-(len(check["extension"])+1)
            FPMX,EXT=os.path.splitext(check["filepath"])
            FPMXC=FPMX[:clip]+"~"
            check["filepath"]=FPMXC+EXT
        else:
            return False
    if not os.path.exists(check["directory"]):
        if create_directory:
            prepare_path(check["directory"])
        else:
            return False
    return check["filepath"]

def get_class_by_name(name):
    """
    >>> c=get_class_by_name("DATReaderWithoutTemp")
    >>> print c.__name__
    DATReaderWithoutTemp
    WARNING Doesn't work from inside other modules!
    """
    return globals().get(name,None)


def get_newlogpath():
    logfolder=os.path.join(check_and_fix_paths()["target_directory"],
                           "Logs")
    prepare_path(logfolder)
    pp=os.path.join(logfolder,
                    "phenos{}.log".format(time.strftime("%y%m%d%H%M%S")))
    return pp

def create_Windows_shortcut(targetpath,locationpath,report=False):
    try:
        shell=win32com.client.Dispatch("WScript.Shell")
        shortcut=shell.CreateShortCut(locationpath)
        shortcut.Targetpath=targetpath
        shortcut.save()
        if report:
            LOG.info("created shortcut to {} in {}"
                     .format(targetpath,locationpath))
    except Exception as e:
        LOG.error("failed to create shortcut to {} in {} because {} {}"
                  .format(targetpath,locationpath,e,get_traceback()))

def open_on_Windows(somepath):
    try:
        if os.path.isdir(somepath):
            subprocess.Popen('explorer "{}"'.format(somepath))
        else:
            subprocess.Popen('notepad "{}"'.format(somepath))
    except:
        LOG.error("couldn't open {}".format(somepath))

def log_uncaught_exceptions(*exc_args):
    """
    This, once set at sys.excepthook, makes sure uncaught exceptions
    are saved to the log.
    """
    exc_txt=''.join(traceback.format_exception(*exc_args))
    LOG.error("Unhandled exception: %s",exc_txt)
    #logging.shutdown()

def get_traceback():
    return ''.join(traceback.format_exception(*sys.exc_info()))

def setup_logging(level="INFO",
                  fileformat='%(levelname)s [ln %(lineno)d, '
                  '%(module)s.%(funcName)s]   %(message)s [%(asctime)s]\n',
                  #stdoutformat='%(message)s\n'):
                  stdoutformat='%(levelname)s [ln %(lineno)d, '
                  '%(module)s.%(funcName)s]   %(message)s [%(asctime)s]\n'):
    """
    https://docs.python.org/2/howto/logging.html#logging-basic-tutorial
    http://stackoverflow.com/questions/5296130/restart-logging-to-a-new-file-python
    """
    if level is None:
        LOGLEVEL=logging.INFO#DEBUG
    elif type(level)==str:
        LOGLEVEL={"DEBUG":logging.DEBUG,
                  "INFO":logging.INFO,
                  "WARNING":logging.WARNING,
                  "ERROR":logging.ERROR,
                  "CRITICAL":logging.CRITICAL}[level]
    else:
        LOGLEVEL=level

    filepath=get_newlogpath()
    if LOG.handlers: # wish there was a LOG.close()
        for handler in LOG.handlers[:]:  # make a copy of the list
            LOG.removeHandler(handler)
    LOG.setLevel(LOGLEVEL)

    fh=logging.FileHandler(filepath)
    fh.setFormatter(logging.Formatter(fileformat))
    LOG.addHandler(fh)

    sh=logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter(stdoutformat))
    LOG.addHandler(sh)

    LOG.info('_'*50)
    LOG.info('Set up logging to {}'.format(filepath))

#

class DirectoryWrapper(object):
    def __init__(self,dirpath=None,godeep=True):
        if dirpath is None:
            dirpath=scriptdir()
        self.fullpath=os.path.dirname(dirpath)

    def exists(self):
        return os.path.exists(self.fullpath)

    def create(self):
        if not self.exists():
            os.makedirs(self.fullpath)

    def parent(self):
        return DBDirectory(os.path.split(self.fullpath)[0])

    def contents(self):
        pass
        

    def __eq__(self,other):
        if type(other)==str:
            return self.fullpath==other
        else:
            return self.fullpath==other.fullpath

    def intersection(self,other):
        pass

    def __add__(self,other):
        if type(other)==str:
            return DBDirectory(os.path.join(self.fullpath,other))
        #elif 
        pass

    def __iter__(self):
        pass


#MAIN #########################################################################
if __name__=='__main__':
    setup_logging("INFO")#CRITICAL")
    sys.excepthook=log_uncaught_exceptions

    #setup_config_txt(destinationpath="C:\Users\localadmin1\AppData\Roaming\PHENOS\config D.txt")

    #import doctest
    #doctest.testmod()
