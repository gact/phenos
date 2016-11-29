#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
"""

################################################################################

import os, sys, string
from phenos import *
import tkFileDialog

################################################################################

filename = os.path.basename(__file__)
authors = ("David B. H. Barton")
version = "1.0"
#
LOCS=Locations()
windowposition='{}x{}+{}+{}'.format(*LOCS.windowposition)
platereader_output=LOCS.platereader_output
FALL=Files("All")
PLO=PlateLayouts()
if len(PLO)==0:
    PLO.update()

copytoall=False

def build_filetitle(**kwargs):
    if kwargs.get("treatment",None):
        kwargs["treatment"]=" ({treatment})".format(**kwargs)
    if kwargs.get("layout",None):
        kwargs["layout"]=" [{layout}]".format(**kwargs)
    if kwargs.get("orientation",None):
        kwargs["orientation"]="R"
    if kwargs.get("exclusions",None):
        kwargs["exclusions"]=" {{{exclusions}}}".format(**kwargs)
    if kwargs.get("timeoffset",None):
        if kwargs.get("survivor",None):
            kwargs["timeoffset"]=" {survivor}{timeoffset}".format(**kwargs)
        else:
            kwargs["timeoffset"]=" {timeoffset}".format(**kwargs)
    if kwargs.get("note",None):
        kwargs["note"]=" ({note})".format(**kwargs)
    if kwargs.get("extension",None):
        if not kwargs["extension"].startswith("."):
            kwargs["extension"]=".{extension}".format(**kwargs)
    kwargs2={k:v for k,v in kwargs.items() if v}

    pattern=("{userinitials}{experimentnumber}{fileletter}"
             "{treatment}"
             "{layout}{orientation}"
             "{exclusions}"
             "{timeoffset}"
             "{note}"
             "{extension}")
    return string.Formatter().vformat(pattern,
                                      (),
                                      defaultdict(str,**kwargs2)).strip()

class RenameLog(object):
    lastrenamedlog="lastrenamed.log"
    def __init__(self):
        self.cursorfile=os.path.join(platereader_output,self.lastrenamedlog)
        self.lastrenamed=""
        self.lastrenamedtime=0
        if os.path.exists(self.cursorfile):
            with open(self.cursorfile,"r") as txtfile:
                self.lastrenamed=os.path.normpath(txtfile.read())
                self.assesslastrenamed()
        self.firstrenamed=self.lastrenamed


    def assesslastrenamed(self):
        if self.lastrenamed:
            self.lastrenamedpath=os.path.join(platereader_output,
                                              self.lastrenamed)
            self.lastrenamedtime=os.path.getmtime(self.lastrenamedpath)

    def storelastrenamed(self):
        with open(self.cursorfile,"w") as txtfile:
            txtfile.write(self.lastrenamed)

    def reset(self):
        self.lastrenamed=self.firstrenamed
        self.assesslastrenamed()
        self.storelastrenamed()
        del self.files

    def getunrenamedfiles(self):
        if not hasattr(self,"files"):
            self.dm=DirectoryMonitor(platereader_output,
                                     dig=False,
                                     include=[".DAT",".csv"])
            self.files=[]
            for F in self.dm:
                M=os.path.getmtime(F)
                if M>self.lastrenamedtime:
                    self.files.append((M,F))
            self.files.sort()
        return self.files

    def get_next(self,storechange=True):
        FS=self.getunrenamedfiles()
        if not storechange:
            return FS[0]
        if FS:
            self.lastrenamedtime,self.lastrenamedpath=FS.pop(0)
            self.lastrenamed=os.path.basename(self.lastrenamedpath)
            self.storelastrenamed()
            return self.lastrenamedtime,self.lastrenamed
        else:
            return None,None

    def format_file_date(self,filename=None,moddate=None,storechange=False):
        if filename is None and moddate is None:
            moddate,filename=self.get_next(storechange=storechange)
        return "{}, last modified on {}".format(filename,
                                                time.ctime(moddate))

    def __str__(self):
        output=[platereader_output,
                "_"*30,
                "LAST: {} {}".format(self.lastrenamed,
                                     self.lastrenamedtime),
                "_"*30]
        output+=["NEXT {}: {} {}".format(i,f,m)
                 for i,(m,f) in enumerate(self.getunrenamedfiles())]
        return os.linesep.join(output)


def choose_file_to_rename():
    RL=RenameLog()
    LST=[(a,b,time.asctime(time.localtime(c)))
         for a,b,c in RenamedFiles().return_platereader_output_list()]
    
    root=tk.Tk()
    LB1=MultiColumnListbox(root,
                           title="PHENOS",
                           instruct="Select file to rename.",
                           headers=["Filename",
                                    "Already renamed as",
                                    "Date/time finished"],
                           lists=LST,
                           default=LST[0][0],
                           delete_fn=delete_renamedfile)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop() #waits for selection/cancel
    FILETORENAME=LB1.values[0]
    LOG.info("user selected file {} to rename".format(FILETORENAME))
    if FILETORENAME:
        return {"originalfilename":FILETORENAME}

def summarise_file(MAINDICT):
    filepath=os.path.join(platereader_output,
                          MAINDICT["originalfilename"])
    shareddata,rowdata=read_data_file(filepath)
    warnings=[]
    timepoints=", ".join(["{:.2f}".format(f) for f in shareddata["timepoints"]])
    default="Array size"
    if "temperaturepoints" in shareddata:
        TMP=shareddata["temperaturepoints"]
        average,MINT,MAXT=sum(TMP)/len(TMP),min(TMP),max(TMP)
        temppoints=", ".join(["{:.1f}".format(t) for t in TMP])
        Twarning=""
    else:
        temppoints=MINT=MAXT="INCUBATOR NOT TURNED ON"
        Twarning="N/A"
    SO=time.asctime(time.localtime(shareddata["exp_datetime"]))
    FO=time.asctime(time.localtime(shareddata["finishedtime"]))
    MINM=shareddata["minimummeasure"]
    MAXM=shareddata["maximummeasure"]

    def check_prp():
        if filename.startswith(shareddata["platereaderprogram"]):
            return ""
        return "NOT IN FILENAME!?"

    def check_mintemp(mintemp):
        if type(mintemp)==str:
            return "N/A"
        if not average-0.5<mintemp<average+0.5:
            return "TOO LOW!"
        return ""

    def check_maxtemp(maxtemp):
        if type(maxtemp)==str:
            return "N/A"
        if not average-0.5<maxtemp<average+0.5:
            return "TOO HIGH!"
        return ""

    def check_minmeasure(minmeasure):
        if minmeasure<0.001:
            return "TOO SMALL!"
        return ""

    def check_maxmeasure(maxmeasure):
        if maxmeasure>3.5:
            return "TOO HIGH!"
        return ""

    LST=[("Platereader program","",shareddata["platereaderprogram"]),
         ("Array size","",shareddata["n_curves"]),
         ("Started on","",SO),
         ("Finished on","",FO),
         ("Total runtime (hrs)","","{:.2f}".format(shareddata["runtime_hours"])),
         ("Number of measurements","",shareddata["n_measures"]),
         ("Timepoints","",timepoints),
         ("","",""),
         ("Temperature readings",Twarning,temppoints),
         ("Minimum temperature",check_mintemp(MINT),MINT),
         ("Maximum temperature",check_maxtemp(MAXT),MAXT),
         ("","",""),
         ("Lowest reading",check_minmeasure(MINM),MINM),
         ("Highest reading",check_maxmeasure(MINM),MAXM)]
    C1,C2,C3=zip(*LST)
    nonemptywarningindexes=[i for i,n in enumerate(C2) if n]
    if nonemptywarningindexes: defaultindex=nonemptywarningindexes[0]
    else: defaultindex=2
    default=C1[defaultindex]
    root=tk.Tk()
    LB1b=MultiColumnListbox(root,
                            title="PHENOS",
                            instruct=("Check file {}{}"
                                      "Hit OK/<Enter> to proceed with this "
                                      "file, or <Escape> to cancel and "
                                      "choose another file."
                                      .format(filename,os.linesep)),
                            buttontext="OK",
                            headers=["Check","WARNINGS","Value"],
                            lists=LST,
                            default=default)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop() #waits for selection/cancel
    if LB1b.values[0]:
        MAINDICT["shareddata"]=shareddata
        MAINDICT.update(shareddata)
        MAINDICT["rowdata"]=rowdata
        return MAINDICT
    else:
        return False

def count_files_in(folder,dig=False,include=[".csv",".DAT"]):
    dm=DirectoryMonitor(folder,dig=dig,include=include,report=False)
    return len(dm)

def choose_user_folder(MAINDICT,
                       IGNORE=["All","Controls"]):
    LST,LSTED=[],[]
    for p in LOCS.yield_userpaths():
        fp=os.path.basename(p)
        fpc=count_files_in(p)
        if fp not in IGNORE:
            LST.append((fp,fpc))
            LSTED.append(fp)
    if not LST:
        LST=[("New folder","")]
    LST.sort()
    DEF=LOCS.currentuserfolder
    if DEF in IGNORE or DEF not in LSTED:
        DEF="New folder"

    root=tk.Tk()
    LB2=MultiColumnListbox(root,
                           title="PHENOS",
                           instruct=("Select user folder.{}"
                                     "Or ESCAPE/<close> to save as tab "
                                     "file without further analysis"
                                     .format(os.linesep)),
                           headers=["User folder",
                                    "Number of files in folder"],
                           lists=LST,
                           default=DEF)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    USERFOLDER=LB2.values[0]
    LOG.info("user selected folder {}".format(USERFOLDER))

    if USERFOLDER=="New folder":
        USERFOLDER=None
        instruction="Enter name for new folder"
        while not USERFOLDER:
            root=tk.Tk()
            EB1=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            USERFOLDER=EB1.value
            fullpath=os.path.join(LOCS["datafiles"],USERFOLDER)
            if os.path.exists(fullpath):
                instruction="{} already exists. Choose again.".format(USERFOLDER)
                LOG.error(instruction)
                USERFOLDER=None
            else:
                try:
                    if USERFOLDER!="New folder":
                        LOCS.add_new_userfolder(USERFOLDER,setfolder=True)
                except Exception as e:
                    instruction=("Can't create {} because {}. Choose again."
                                 .format(fullpath,e,get_traceback()))
                    LOG.error(instruction)
                    USERFOLDER=None
    if USERFOLDER:
        LOCS.change(USERFOLDER,create=True)
        LOG.info("active folder set to {}".format(USERFOLDER))
        MAINDICT["userfolder"]=USERFOLDER
        return MAINDICT

def output_to_txt(MAINDICT,
                  extension="tab",
                  delimiter="\t",
                  spacer="\t",
                  ask=False,
                  replace=False,
                  **kwargs):
    headers=["well","isborder","minimum","maximum","measurements:"]
    sourcefilename=MAINDICT["originalfilename"]
    shareddata=MAINDICT["shareddata"]
    rowdata=MAINDICT["rowdata"]

    filepath=os.path.join(platereader_output,sourcefilename)
    if shareddata is None or rowdata is None:
        shareddata,rowdata=read_data_file(filepath)
    headers+=["{:.2f}".format(t) for t in shareddata["timepoints"]]

    targetfilename=os.path.splitext(sourcefilename)[0]+"."+extension
    targetfilefolder=os.path.join(platereader_output,"ConvertedFiles")
    prepare_path(targetfilefolder)
    #OPEN THIS TARGETFILEPATH FOLDER AT THE END
    targetfilepath=os.path.join(targetfilefolder,targetfilename)

    #get plate
    plt=Plates()[str(shareddata["n_curves"])]

    if os.path.exists(targetfilepath):
        if ask:
            answer=raw_input("{} already exists. Overwrite it?"
                             .format(targetfilepath))
            if not answer.lower().startswith("y"):
                return
        elif not replace:
            LOG.info("{} already exists".format(targetfilepath))
            open_on_Windows(targetfilefolder)
            return
    
    with open(targetfilepath,"wb") as fileob:
        writer=csv.writer(fileob,
                          delimiter=delimiter,
                          quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        for i,(row,well) in enumerate(zip(rowdata,plt.yield_records())):
            measures=row["measurements"]
            if spacer==delimiter:
                measurestring=list(measures)
            else:
                measurestring=[spacer.join([str(v)
                                            for v in row["measurements"]])]
            rowout=[str(well["wellid"].value),
                    str(well["isborder"].value),
                    str(min(measures)),
                    str(max(measures)),
                    ""]+measurestring
            writer.writerow(rowout)
        fileob.close()
        LOG.info("{} created".format(targetfilepath))
    open_on_Windows(targetfilefolder)
    #open_on_Windows(targetfilepath)
    return targetfilepath

def choose_user_initials(MAINDICT):
    userfolder=MAINDICT["userfolder"]
    
    ALLINI=FALL.get_values_of_atom("user")
    F=Files(userfolder)
    if len(F)==0:
        USERINITIALS="*new*"
        INI=[]
    else:
        INI=F.get_values_of_atom("user")
        LST=list(INI.items())+[("*new*","")]
        DEF=F[-1]["user"].value

        root=tk.Tk()
        TIT="PHENOS"
        LB3=MultiColumnListbox(root,
                               title=TIT,
                               instruct=("Select initials.{}"
                                         "Or *new* to enter new initials."
                                         .format(os.linesep)),
                               headers=["User initials","Number of files"],
                               lists=LST,
                               default=DEF)
        root.focus_force()
        root.geometry(windowposition)
        root.mainloop()
        USERINITIALS=LB3.values[0]

    if USERINITIALS=="*new*":
        USERINITIALS=None
        instruction="Enter new user initials (<=5 letters)"
        while not USERINITIALS:
            root=tk.Tk()
            EB2=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            USERINITIALS=EB2.value
            if not 1<=len(USERINITIALS)<=5:
                instruction=("{} not OK. Must be 1-5 letters long. Choose again."
                             .format(USERINITIALS))
                LOG.error(instruction)
                USERINITIALS=None
            elif USERINITIALS in INI:
                instruction=("{} already in {}. Choose again"
                             .format(USERINITIALS,LOCS.currentdbase))
                LOG.error(instruction)
                USERINITIALS=None
            elif USERINITIALS in ALLINI:
                instruction=("{} already in use in another folder ({} files). "
                             "Choose again.".format(USERINITIALS,ALLINI[USERINITIALS]))
                LOG.error(instruction)
                USERINITIALS=None

    if USERINITIALS:
        MAINDICT["userinitials"]=USERINITIALS
        return MAINDICT

def choose_experiment_number(MAINDICT):
    userfolder=MAINDICT["userfolder"]
    userinitials=MAINDICT["userinitials"]
    
    FLST=Files(userfolder).get(user=userinitials)
    if not FLST:
        EXPNUMBER=1
        LST=[("*new* (1)",""),
             ("*new* (other)","")]
        INI=[]
        DEF=LST[0][0]
    else:
        if type(FLST)!=list:
            FLST=[FLST]
        INI=defaultdict(list)
        for FL in FLST:
            previousexpnum=FL["experimentnumber"].value
            previousfilelet=FL["fileletter"].value
            INI[previousexpnum].append(previousfilelet)
        LST=sorted([(k,"".join(sorted(v))) for k,v in INI.items()],
                   reverse=True)
        EXPNUMBER=LST[0][0]+1
        DEF=LST[0][0]
        LST=[("*new* ({})".format(EXPNUMBER),""),
             ("*new* (other)",""),]+LST

    root=tk.Tk()
    TIT="PHENOS: '{}'".format(build_filetitle(**locals().copy()))
    LB4=MultiColumnListbox(root,
                           title=TIT,
                           instruct=("Select experiment number.{}"
                                     .format(os.linesep)),
                           headers=["Experiment number","Existing file letters"],
                           lists=LST,
                           default=DEF)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    EXPNUMBER=LB4.values[0]

    if EXPNUMBER=="*new* (other)":
        EXPNUMBER=None
        instruction="Enter new experiment number (0-255)"
        while not EXPNUMBER:
            root=tk.Tk()
            EB3=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            EXPNUMBER=EB3.value
            if EXPNUMBER is None:
                return None
            try:
                EXPNUMBER=int(EXPNUMBER)
            except:
                instruction=("{} not a number. Choose again.")
                LOG.error(instruction)
                EXPNUMBER=None
            if not 0<=EXPNUMBER<=255:
                instruction=("{} not OK. Must be 0-255. Choose again."
                             .format(EXPNUMBER))
                LOG.error(instruction)
                EXPNUMBER=None
            elif EXPNUMBER in INI:
                instruction=("{} already in {}. Choose again"
                             .format(EXPNUMBER,LOCS.currentdbase))
                LOG.error(instruction)
                EXPNUMBER=None
    
    if type(EXPNUMBER)==unicode:
        if EXPNUMBER.startswith("*new* "):
            EXPNUMBER=int(EXPNUMBER[7:-1])

    if EXPNUMBER:
        MAINDICT["experimentnumber"]=EXPNUMBER
        return MAINDICT

def choose_file_letter(MAINDICT):
    ok="abcdefghijklmnopqrstuvwxyz"
    userfolder=MAINDICT["userfolder"]
    userinitials=MAINDICT["userinitials"]
    experimentnumber=MAINDICT["experimentnumber"]
    
    FLST=Files(userfolder).get(user=userinitials,
                               experimentnumber=experimentnumber)
    if not FLST:
        FILELETTER="a"
        LST=[("*new* (a)",""),
             ("*new* (other)","")]
        INI={}
    else:
        previousfiles={}
        INI={}
        if type(FLST)!=list:
            FLST=[FLST]
        for FL in FLST:
            INI[FL["fileletter"].value]=FL["filepath"].value
            previousfiles[FL["fileletter"].value]=FL
        LST=sorted(INI.items(),reverse=True)
        MAINDICT["previousfiles"]=[previousfiles[l] for l,fn in LST]
        FILELETTER=chr(ord(LST[0][0])+1)
        if FILELETTER not in ok:
            LOG.error("fileletter {}' not valid"
                      .format(FILELETTER))
            return
        LST=[("*new* ({})".format(FILELETTER),""),
             ("*new* (other)",""),]+LST
    DEF=LST[0][0]
    root=tk.Tk()
    TIT="PHENOS: '{}'".format(build_filetitle(**locals().copy()))
    LB4=MultiColumnListbox(root,
                           title=TIT,
                           instruct=("Select file letter.{}"
                                     .format(os.linesep)),
                           headers=["File letter","Used in"],
                           lists=LST,
                           default=DEF,
                           notselectable=INI.keys())
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    FILELETTER=LB4.values[0]

    if FILELETTER=="*new* (other)":
        FILELETTER=None
        instruction="Enter new file letter (a-z)"
        while not FILELETTER:
            root=tk.Tk()
            EB3=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            FILELETTER=EB3.value
            if FILELETTER is None:
                return None
            try:
                FILELETTER=FILELETTER.lower()
            except:
                instruction=("{} not a letter. Choose again.")
                LOG.error(instruction)
                FILELETTER=None
            if FILELETTER not in ok:
                instruction=("{} not OK. Must be a-z. Choose again."
                             .format(FILELETTER))
                LOG.error(instruction)
                FILELETTER=None
            elif FILELETTER in INI:
                instruction=("{} already in experiment {}{}. Choose again"
                             .format(FILELETTER,
                                     userinitials,
                                     experimentnumber))
                LOG.error(instruction)
                FILELETTER=None

    if FILELETTER:
        if FILELETTER.startswith("*new* "):
            FILELETTER=FILELETTER[7:-1]
        MAINDICT["fileletter"]=FILELETTER
        return MAINDICT

def choose_treatment(MAINDICT):
    userfolder=MAINDICT["userfolder"]
    userinitials=MAINDICT["userinitials"]
    experimentnumber=MAINDICT["experimentnumber"]
    fileletter=MAINDICT["fileletter"]

    FAd=FALL.get_values_of_atom("treatment")
    for k,v in Files().get_values_of_atom("treatment").items():
        if k in FAd:
            FAd[k]+=v
        else:
            FAd[k]=v
    LST=sorted(FAd.items())
    #
    DEF="YPD"
    if fileletter!="a":
        FLST=Files(userfolder).get(user=userinitials,
                                   experimentnumber=experimentnumber)
        if FLST:
            if type(FLST)!=list:
                FLST=[FLST]
            DEF=FLST[0]["treatment"].value
    if DEF=="YPD":
        DEF="YPD (control)"
    #
    #Shunt YPD to top
    LST2=[("YPD (control)",FAd.get("YPD",0))]
    LST2+=[(a,b) for a,b in LST if a!="YPD"]
    LST2+=[("*new*","")]

    root=tk.Tk()
    TIT="PHENOS: '{}'".format(build_filetitle(**locals().copy()))
    LB5=MultiColumnListbox(root,
                           title=TIT,
                           instruct=("Select treatment.{}"
                                     .format(os.linesep)),
                           headers=["Treatment","Number of files in All with treatment"],
                           lists=LST2,
                           default=DEF)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    TREATMENT=LB5.values[0]

    if TREATMENT=="*new*":
        TREATMENT=None
        instruction="Enter new treatment name"
        while not TREATMENT:
            root=tk.Tk()
            EB4=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            TREATMENT=EB4.value
            if len(TREATMENT)>40:
                instruction="{} is too long. Choose again (<=40 characters).".format(TREATMENT)
                LOG.error(instruction)
                TREATMENT=None

    if TREATMENT=="YPD (control)":
        TREATMENT="YPD"
    if TREATMENT:
        MAINDICT["treatment"]=TREATMENT
        return MAINDICT

def choose_layout(MAINDICT):
    originalfilename=MAINDICT["originalfilename"]
    userfolder=MAINDICT["userfolder"]
    userinitials=MAINDICT["userinitials"]
    experimentnumber=MAINDICT["experimentnumber"]
    fileletter=MAINDICT["fileletter"]
    treatment=MAINDICT["treatment"]
    shareddata=MAINDICT["shareddata"]
    arraysize=shareddata["n_curves"]

    LST=[]
    for pl in PLO:
        if pl["capacity"].value==arraysize:
            matches=FALL.get(platelayout=pl.value) or []
            LST.append((pl.value,len(matches)))
    LST.append(("*browse*",""))

    DEF="Basic{}".format(arraysize)
    
    if fileletter!="a":
        FLST=Files(userfolder).query_by_dictionary({"user":userinitials,
                                                    "experimentnumber":experimentnumber,
                                                    "fileletter":"a"})
        if FLST:
            DEF=FLST[0]["platelayout"].value

    root=tk.Tk()
    TIT="PHENOS: '{}'".format(build_filetitle(**locals().copy()))
    LB6=MultiColumnListbox(root,
                           title=TIT,
                           instruct=("Select layout.\n"
                                     "If your layout isn't visible here "
                                     "then it doesn't match the data in "
                                     "the platereader file (hit <Escape>"
                                     " to quit).\nIf your layout hasn't "
                                     "been registered yet, hit *browse* "
                                     "and select it.\nIf it doesn't "
                                     "exist, you need to create it "
                                     "(modify one of the Basic layouts "
                                     "and save it under a new name)."),
                           headers=["Layouts ({})".format(arraysize),
                                    "Number of files in All with layout"],
                           lists=LST,
                           default=DEF)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    LAYOUT=LB6.values[0]

    if LAYOUT=="*browse*":
        LOC=LOCS["layouts"]
        INS="Select layout file, or <escape> to exit and create one"
        LAYOUT=None
        while not LAYOUT:
            root=tk.Tk()
            root.geometry(windowposition)
            root.withdraw()
            filename=tkFileDialog.askopenfilename(initialdir=LOC,
                                                  title=INS)
            root.destroy()
            if not filename:
                return
            else:
                LAYOUT=os.path.splitext(os.path.basename(filename))[0]
            query=PlateLayout(filepath=os.path.basename(filename),
                              layoutstring=LAYOUT)
            if query not in PLO:
                try:
                    query.read(store=True)
                    CAP=query["capacity"].value
                    if CAP!=arraysize:
                        INS=("Platelayout {} has size {}, "
                             "whereas {} has size {}. Choose again."
                             .format(filename,
                                     CAP,
                                     originalfilename,
                                     arraysize))
                        LOG.error(INS)
                        LAYOUT=None
                except Exception as e:
                    INS=("Couldn't read platelayout {} because {} {}. "
                         "Choose again."
                         .format(filename,e,get_traceback()))
                    LOG.error(INS)
                    LAYOUT=None

    if LAYOUT:
        MAINDICT["layout"]=LAYOUT
        return MAINDICT

def choose_orientation(MAINDICT):
    root=tk.Tk()
    OB1=OptionBox(root,
                  title="PHENOS",
                  instruct=("Was the plate correctly oriented, "
                            "with well A1 at the back left,\nand the "
                            "word 'Singer' on the PlusPlate lid\n "
                            "facing you and the correct way up?"))
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    ORIENT=OB1.value
    if ORIENT=="Yes":
        MAINDICT["orientation"]=""
    elif ORIENT=="No":
        LOG.error("Plate was incorrectly oriented. Will proceed on the "
                  "assumption that it was rotated 180 degrees from normal.")
        MAINDICT["orientation"]="R"
    return MAINDICT

def choose_exclusions(MAINDICT):
    userinitials=MAINDICT["userinitials"]
    experimentnumber=MAINDICT["experimentnumber"]
    fileletter=MAINDICT["fileletter"]
    treatment=MAINDICT["treatment"]
    layout=MAINDICT["layout"]
    shareddata=MAINDICT["shareddata"]
    rowdata=MAINDICT["rowdata"]
    
    if "emptyplate" in shareddata["platereaderprogram"]:
        return False
    if fileletter=="a":
        return False
    root=tk.Tk()
    OB2=OptionBox(root,
                  title="PHENOS",
                  instruct=("Are there any wells or samples you wish to "
                            "exclude from analysis, e.g. because of "
                            "contamination?"),
                  default="No")
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    answer=OB2.value
    if answer=="No":
        return False
    pl=PLO[layout]
    LST=[]
    headers=["Well name","Strain ID","Warnings","Max. change","Raw OD600"]
    DEF={}
    LOOKUP={}
    for row,pp in zip(rowdata,pl.yield_records()):
        well=pp["wellname"]
        strain=pp["strain"]
        LOOKUP[well.value]=strain.value
        blank=strain.is_blank()
        measures=row["measurements"]
        warning=""
        if len(measures)>0:
            average=sum(measures)/len(measures)
            maxchange=max(measures)-min(measures)
            if blank and maxchange>0.5:
                warning="SHOULD BE BLANK!"
            elif not blank and maxchange<0.1:
                warning="SHOULDN'T BE BLANK!"
        RS=", ".join(["{:.2f}".format(m) for m in measures])
        LST.append((well.value,strain.value,warning,maxchange,RS))
        if warning:
            DEF[well.value]=strain.value

    root=tk.Tk()
    TIT="PHENOS: '{}'".format(build_filetitle(**locals().copy()))
    instruction=("Select wells/strains to exclude, "
                 "<Escape> if none. N.B. to "
                 "habitually exclude a given strain"
                 "you should edit {} and set the"
                 "value for that strain in the IGNORE"
                 "column to TRUE"
                 .format(os.path.join(LOCS["genotypes"],
                                      "strains.csv")))
    LB7=MultiColumnListbox(root,
                           title=TIT,
                           instruct=instruction,
                           headers=headers,
                           selectmode="extended",
                           default=DEF.keys(),
                           lists=LST)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    EXCLUSIONS=LB7.values

    if not EXCLUSIONS:
        return None
    if type(EXCLUSIONS) in [str,unicode]:
        EXCLUSIONS=[EXCLUSIONS]
    
    #format exclusions
    #first find any cases where all of a given strain have been selected
    
    ALLSTRAINS=LOOKUP.values()
    for well in EXCLUSIONS:
        strain=LOOKUP.get(str(well),None)
        if not strain:
            LOG.warning("Couldn't find exclusion {}({})"
                        .format(type(well),str(well)))
        elif strain in ALLSTRAINS:
            ALLSTRAINS.remove(strain)
    
    watchlist={}
    for well in EXCLUSIONS:
        strain=LOOKUP.get(str(well),None)
        if not strain:
            LOG.warning("Couldn't find exclusion {}({})"
                        .format(type(well),str(well)))
        else:
            if strain not in ALLSTRAINS:
                watchlist[strain]=""
            else:
                watchlist[well]=""

    for WL in watchlist.keys():
        root=tk.Tk()
        EB5=EntryBox(root,
                     title="PHENOS",
                     instruct=("Enter one-word reason for exclusion of {}\n"
                               "e.g. contamination, misprint, empty"
                               .format(WL)),
                     default="contamination")
        root.focus_force()
        root.geometry(windowposition)
        root.mainloop()
        watchlist[WL]=EB5.value

    reversewatchlist=defaultdict(list)
    for k,v in watchlist.items():
        reversewatchlist[v].append(k)

    EXCLUSIONS=";".join([",".join(v)+"="+k for k,v in reversewatchlist.items()])
    if EXCLUSIONS:
        if len(EXCLUSIONS)>100:
            warning=("List of exclusions is very large and will "
                     "probably produce a filename that is too long:\n"
                     "{}\n"
                     "Returning '' instead."
                     .format(EXCLUSIONS))
            LOG.warning(warning)
            return None
    MAINDICT["exclusions"]=EXCLUSIONS
    return MAINDICT

def choose_timeoffset(MAINDICT):
    originalfilename=MAINDICT["originalfilename"]
    userfolder=MAINDICT["userfolder"]
    userinitials=MAINDICT["userinitials"]
    experimentnumber=MAINDICT["experimentnumber"]
    fileletter=MAINDICT["fileletter"]
    treatment=MAINDICT["treatment"]
    layout=MAINDICT["layout"]
    orientation=MAINDICT["orientation"]
    shareddata=MAINDICT["shareddata"]
    #if emptyplate, then default = t-1
    LST=[("t-1 (empty plate before printing)",""),
         ("t+0 (program run immediately after printing)","")]
    LASTOFFSET=0
    DEF=""

    if "emptyplate" in shareddata["platereaderprogram"]:
        DEF=LST[0][0]
    if fileletter=="a":
        DEF=LST[0][0]
    #if after that then probably = t+0
    if fileletter=="b":
        DEF=LST[1][0]
    if fileletter>"b":
        F=Files(userfolder)
        fs=F.query_by_dictionary({"user":userinitials,
                                  "experimentnumber":experimentnumber})
        if fs:
            SRT=[(f["fileletter"].value,f) for f in fs]
            LAST=sorted(SRT)[-1][1]
            lasttime=LAST["experimenttimestamp"].value
            difference=shareddata["exp_datetime"]-lasttime
            HRDIFF=int(difference/3600.0)
            LASTOFFSET=int(LAST["timeoffset"].value)
            newtimeoffset=int(LASTOFFSET+HRDIFF)
            DEF=("t+{} (based on time difference from '{}')"
                 .format(newtimeoffset,LAST["filepath"].value))
            LST.append((DEF,""))
    LST.append(("*other*",""))

    root=tk.Tk()
    TIT="PHENOS: '{}'".format(build_filetitle(**locals().copy()))
    LB7=MultiColumnListbox(root,
                           title=TIT,
                           instruct=("Select time offset.{}"
                                     "(This is the number of hours "
                                     "between printing the plate "
                                     "and the program being run)."
                                     .format(os.linesep)),
                           headers=["Time offset",""],
                           lists=LST,
                           default=DEF)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    TIMEOFFSET=LB7.values[0]
    if TIMEOFFSET is None: return None
    if TIMEOFFSET=="*other*":
        TIMEOFFSET=None
        instruction="Enter offset (>{})".format(LASTOFFSET)
        while not TIMEOFFSET:
            root=tk.Tk()
            EB5=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            TIMEOFFSET=EB5.value
            if TIMEOFFSET is None:
                return None
            try:
                numericalTIMEOFFSET=int(TIMEOFFSET)
            except:
                numericalTIMEOFFSET=False
            if type(numericalTIMEOFFSET)==int:
                if LASTOFFSET<numericalTIMEOFFSET<=255:
                    TIMEOFFSET="t+{}".format(int(numericalTIMEOFFSET))
                else:
                    instruction=("{} not OK. Must be {}-255. Choose again."
                                 .format(LASTOFFSET,numericalTIMEOFFSET))
                    LOG.error(instruction)
                    TIMEOFFSET=None
                    
    else:
        TIMEOFFSET=TIMEOFFSET.split(" ")[0]

    if TIMEOFFSET:
        MAINDICT["timeoffset"]=TIMEOFFSET
        return MAINDICT

def choose_note(MAINDICT):
    notallowed="()[]*\\/\"'!£$~#"
    instruction=("Is there anything special you want "
                 "to note about this experiment?\n"
                 "(Don't bother duplicating earlier information; "
                 "e.g. there's no point\nputting in your name)\n"
                 "N.B. Note must be 100 characters long or less "
                 "and mustn't contain any of these characters:"
                 "          {}\n"
                 "If no note, hit <Return> or <Escape>"
                 .format(notallowed))
    NOTE=False
    while NOTE is False:
        root=tk.Tk()
        EB6=EntryBox(root,title="PHENOS",instruct=instruction)
        root.focus_force()
        root.geometry(windowposition)
        root.mainloop()
        NOTE=EB6.value
        if NOTE is None:
            return None
        if len(NOTE)>100:
            instruction=("Note is too long ({} characters). "
                         "Choose again (<=100 characters)."
                         .format(len(NOTE)))
            LOG.error(instruction)
            NOTE=False
        elif set(notallowed) in set(NOTE):
            instruction=("Note cannot contain the characters "
                         "{}\n"
                         "Choose again."
                         .format(notallowed))
            LOG.error(instruction)
            NOTE=False
    if NOTE:
        MAINDICT["note"]=NOTE
        return MAINDICT
    return False

def handle_file(MAINDICT):
    originalfilename=MAINDICT["originalfilename"]
    userfolder=MAINDICT["userfolder"]
    layout=MAINDICT["layout"]
    filepath=os.path.join(platereader_output,originalfilename)
    targetfilename=build_filetitle(**MAINDICT)
    targetfilepath=os.path.join(LOCS.get_userpath(),
                                targetfilename)
    timeoffset=MAINDICT.get("timeoffset","t+0")
    issurvivor=False
    survivorstart=None
    emptyreading=False
    reorient=False
    if timeoffset.startswith("St"):
        """
        e.g. St50-1, St50+0,St68+13
        """
        issurvivor=True
        parts=timeoffset[2:]
        if "-" in parts:
            cardinality="-"
            parts=parts.split("-")
        elif "+" in parts:
            cardinality="+"
            parts=parts.split("+")
        if len(parts)!=2:
            LOG.error("Unacceptable timeoffset string {}".format(timeoffset))
            return None
        survivorstart=float(parts[0])
        timeoffset="t"+cardinality+parts[1]
    timeoffset=float(timeoffset[1:])
    if timeoffset==-1:
        timeoffset=-100
        emptyreading=True

    if MAINDICT.get("orientation","")=="R":
        reorient=True
    
    INS=("Original filename=    {}\n\n"
         "Final filename=    {}\n\n"
         "About to copy from: '{}'\n\n"
         "to: '{}'?\n\n"
         "Proceed? N.B. This may take a minute. Please wait."
         .format(originalfilename,
                 targetfilename,
                 platereader_output,
                 LOCS.get_userpath()))

    root=tk.Tk()
    OB3=OptionBox(root,
                  title="PHENOS",
                  instruct=INS)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    answer=OB3.value

    if answer=="No":
        return
    elif answer=="Yes":
        try:
            copy_to(filepath,targetfilepath)
            timeout=10
            while True:
                if os.path.exists(targetfilepath): break
                timeout-=1
                if not timeout: break
                time.sleep(1)
        except Exception as e:
            LOG.error("Couldn't copy {} to {} because {} {}"
                      .format(filepath,targetfilepath,e,get_traceback()))
            return MAINDICT
        #wait for copy to complete
        
        #Store File object & Readings
        fo=None
        try:
            fo=File(filepath=str(targetfilename),
                    platelayout=str(layout),
                    dbasenameroot=userfolder,
                    timeoffset=timeoffset,
                    reorient=reorient,
                    emptyreading=emptyreading,
                    issurvivor=issurvivor,
                    survivorstart=survivorstart)
            fo.calculate_all()
            fo.store()
            readingcount=fo.read()
            MAINDICT["fileobject"]=fo
            LOG.info("Created File({}) and added to {}"
                     "along with {} Readings"
                     .format(fo.value,
                             LOCS.get_userpath(),
                             readingcount))
        except Exception as e:
            LOG.error("Unable to create/store File for {}"
                      "because {} {}"
                      .format(targetfilename,e,get_traceback()))
            return MAINDICT

        if fo:
            try:
                LOG.info("drawing if empty")
                PVOB=fo.draw_if_empty(show=False)
                if PVOB:
                    del PVOB
                try:
                    pyplt.close("all")
                except:
                    pass
                LOG.info("drew if empty and deleted Plateview object")
            except Exception as e:
                LOG.error("Couldn't draw_if_empty because {} {}"
                          .format(e,get_traceback()))

        #Store RenamedFile
        try:
            rf=RenamedFile(originalfilename=originalfilename,
                           originalfolder=platereader_output,
                           renamedfilename=targetfilename,
                           renamedfolder=LOCS.get_userpath())
            rf["datecreated"].calculate()
            rf.store()
            MAINDICT["renamedfileobject"]=rf
            LOG.info("Created {}".format(rf))
            return MAINDICT
        except Exception as e:
            LOG.error("Couldn't created RenamedFile because {} {}"
                      .format(e,get_traceback()))
            return MAINDICT

#
def main_rename():
    repeat=True
    #SELECT AND EYEBALL DATA FILE (Autoread info)
    while repeat:
        MAINDICT=choose_file_to_rename()
        if not MAINDICT: return
        repeat=False
        if summarise_file(MAINDICT) is False: repeat=True
    
    #SELECT USER FOLDER (Default to Locations().get_userpath())
    if not choose_user_folder(MAINDICT):
        #OPTION: CONTINUE WITHOUT DATA? (Just generates txt and basic curves)
        output_to_txt(MAINDICT)
        return
    else:
        #SELECT INITIALS (Default to last one in Files())
        if not choose_user_initials(MAINDICT): return
    
    #SELECT EXPERIMENTNUMBER (Default to next highest. If already existing,
    if not choose_experiment_number(MAINDICT): return

    #SELECT FILELETTER (Deduce most likely, e.g. emptyplate program = 'a',
    #                   next highest in folder = 'a'+1 etc)
    if not choose_file_letter(MAINDICT): return
    # then change following defaults)

    #SELECT TREATMENT (Default to YPD, but check temperature too.)
    if not choose_treatment(MAINDICT): return

    #SELECT LAYOUT (Default to e.g. Basic384 if a 384 program. ADVANCED:
    #                suggest from 'fingerprint'?)
    #CHECK THAT LAYOUT MATCHES RESULTS ARRAYDENSITY AND
    #CONSISTENT WITH ANY EARLIER FILE
    if not choose_layout(MAINDICT): return

    #CHECK ORIENTATION
    if not choose_orientation(MAINDICT): return

    #SELECT EXCLUSIONS
    if choose_exclusions(MAINDICT) is None: return

    #SELECT TIMEOFFSET (Deduce from file datetime)
    if not choose_timeoffset(MAINDICT): return

    #SELECT NOTE (Deduce from previous)
    if choose_note(MAINDICT) is None: return

    #NOW RENAME & CREATE FILE OBJECT & READINGS
    if not handle_file(MAINDICT): return
    
    #NOW WHAT?
    lastrenamedfile=MAINDICT.get("renamedfileobject",None)
    if not lastrenamedfile:
        return
    renamedfilename=lastrenamedfile["renamedfilename"].value
    lastfile=MAINDICT["fileobject"]

    root=tk.Tk()
    instruction=("Created:\n\n"
                 "Last RenamedFile    '{}'\n\n"
                 "and   File({})\n\n"
                 "and   {} Readings from {}?\n\n"
                 "What do you wish to do next?"
                 .format(renamedfilename,
                         lastfile.value,
                         lastfile["ncurves"].value,
                         LOCS.currentuserfolder))
    OB5=OptionBox(root,
                  title="PHENOS",
                  instruct=instruction,
                  options=["Rename another","Undo","Combine & display Files","Quit"],
                  default="Combine Files")
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    counter=0
    NEXT=OB5.value
    #For some reason root doesn't reliably destroy, causing problems
    #if "Rename another" is selected.
    #Therefore ensure root is destroyed now.
    try:
        root.destroy()
    except Exception as e:
        print e,get_traceback()

    if NEXT=="Quit" or None:
        return
    elif NEXT=="Rename another":
        return main_rename()
    elif NEXT=="Undo":
        return undo_rename()
    elif NEXT=="Combine & display Files":
        return main_combine()

def delete_renamedfile(renamedfile,checkboxes=True):
    if type(renamedfile)==list:
        renamedfile=renamedfile[0]
    if not renamedfile:
        return None
    if type(renamedfile) in [str,unicode]:
        renamedfile=RenamedFiles()[renamedfile]

    renamedfilename=renamedfile["renamedfilename"].value
    fileob=renamedfile.get_file()
    if fileob is None:
        renamedfile.delete()
        return

    if not checkboxes:
        GOAHEAD="Yes"
    else:
        root=tk.Tk()
        instruction=("ARE YOU SURE YOU WANT TO DELETE\n\n"
                     "Last RenamedFile\t'{}'\n\n"
                     "and\tFile({})\n\n"
                     "and\t{} Readings in {}?"
                     .format(renamedfilename,
                             fileob.value,
                             fileob["ncurves"].value,
                             LOCS.currentuserfolder))
        OB4=OptionBox(root,
                      title="PHENOS",
                      instruct=instruction)
        root.focus_force()
        root.geometry(windowposition)
        root.mainloop()
        GOAHEAD=OB4.value
    if GOAHEAD=="Yes":
        renamedfile.delete()
        delete_files([fileob],checkboxes=False)
        fullpath=os.path.join(renamedfile["renamedfolder"].value,
                              renamedfile["renamedfilename"].value)
        try:
            os.remove(fullpath)
            LOG.info("Removed {}".format(fullpath))
        except:
            LOG.error("Couldn't remove {}".format(fullpath))
        return True
    return False

def undo_rename():
    lastrenamedfile=RenamedFiles()[-1]
    renamedfilename=lastrenamedfile["renamedfilename"].value
    RFN=ReadingFileNameReader(renamedfilename)
    try:
        lastfile=Files()[-1]
    except:
        LOG.error("No Files left in {}".format(LOCS.currentdbase))
        choose_user_folder()
        return undo_rename()
        
    EID="{user}{experimentnumber}{fileletter}".format(**RFN.properties)
    if not lastfile.value==EID:
        LOG.error("Last RenamedFile renamed to {} but last File"
                  "is {}".format(renamedfilename,lastfile.value))
    else:
        root=tk.Tk()
        instruction=("ARE YOU SURE YOU WANT TO DELETE\n\n"
                     "Last RenamedFile\t'{}'\n\n"
                     "and\tFile({})\n\n"
                     "and\t{} Readings in {}?"
                     .format(renamedfilename,
                             lastfile.value,
                             lastfile["ncurves"].value,
                             LOCS.currentuserfolder))
        OB4=OptionBox(root,
                      title="PHENOS",
                      instruct=instruction)
        root.focus_force()
        root.geometry(windowposition)
        root.mainloop()
        GOAHEAD=OB4.value
        if GOAHEAD=="Yes":
            lastrenamedfile.delete()
            lastfile.delete()
            fullpath=os.path.join(lastrenamedfile["renamedfolder"].value,
                                  lastrenamedfile["renamedfilename"].value)
            try:
                os.remove(fullpath)
                LOG.info("Removed {}".format(fullpath))
            except:
                LOG.error("Couldn't remove {}".format(fullpath))
            
            root=tk.Tk()
            OB6=OptionBox(root,
                          title="PHENOS",
                          instruct="What next?",
                          options=["Undo again","Rename another","Combine & display Files","Quit"],
                          default="Undo again")
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            counter=0
            NEXT=OB6.value
            if NEXT=="Quit" or None:
                return
            elif NEXT=="Rename another":
                return main_rename()
            elif NEXT=="Undo again":
                return undo_rename()
            elif NEXT=="Combine & display Files":
                return main_combine()
        else:
            return main_rename()
#
def main_combine():
    F=Files()
    combifiledict=F.get_combifile_dict(save=False,
                                       read=False,
                                       alreadymade=False)
    LST=[cf for cf in combifiledict.values()]
    LST.sort(key=lambda cf:getattr(cf,"timestamp",0),reverse=True)

    def timeconvert(tv):
        if tv:
            try:
                return time.asctime(time.localtime(tv))
            except:
                pass
        return ""

    LST2=[(cf.value,
           cf["treatment"].value,
           cf["platelayout"].value,
           cf.is_control(),
           timeconvert(getattr(cf,"timestamp","")),
           "NO")
          for cf in LST]
    if not LST2:
        LOG.error("No new combifiles to create in {}"
                  .format(Locations().get_userpath()))

    headers=["Files","Treatment","Layout","Is control?",
             "Timestamp of first","Already created?"]
    notselectable=None

    if len(CombiFiles())>0:
        LST3=[]
        for cf in CombiFiles():
            try:
                LST3.append((cf.value,
                             cf["treatment"].value,
                             cf["platelayout"].value,
                             cf.is_control(),
                             timeconvert(cf["timestamp"]),
                             "YES"))
            except Exception as e:
                LOG.error("Can't add combifile {} because {} {}"
                          .format(cf,e,get_traceback()))
        LST2+=[(" ","----","----","")]+LST3
        notselectable=[l[0] for l in LST3]

    root=tk.Tk()
    TIT="PHENOS: '{}'".format(build_filetitle(**locals().copy()))
    instruction=("Select combined file(s) to create and visualize\n"
                 "or <Escape> to quit.\n\n"
                 "Hit <Delete> to remove any combined file(s) already created.\n\n"
                 "PHENOS will close on completion.")
    LB7=MultiColumnListbox(root,
                           title=TIT,
                           instruct=instruction,
                           headers=headers,
                           lists=LST2,
                           default=LST2[0][0],
                           selectmode="extended",
                           notselectable=notselectable,
                           delete_fn=delete_combifiles)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    PICK=LB7.values
    if type(PICK)!=list:
        PICK=[PICK]
    output={}
    for P in PICK:
        if P is None or P==' ':
            return output
        cf=combifiledict.get(P)
        if not cf:
            continue
        cf.save(read=True)

        root=tk.Tk()
        instruction=("Created:\n\n"
                     "'{}'\n\n"
                     "Would you like to create all visualizations\n"
                     "or create only a combined tab file\n"
                     "or move on to create the next CombiFile?"
                     .format(cf))
        OB6=OptionBox(root,
                      title="PHENOS",
                      instruct=instruction,
                      options=["Create visualizations",
                               "Combined data file only",
                               "Continue to next CombiFile"],
                      default="Create visualizations")
        root.focus_force()
        root.geometry(windowposition)
        root.mainloop()
        counter=0
        OPT=OB6.value
        if not OPT:
            return output
        elif OPT=="Create visualizations":
            LOG.info("Illustrating {}".format(cf))
            cf.output_to_txt()
            cf.illustrate()
        elif OPT=="Combined data file only":
            cf.output_to_txt(replace=True)
            cf.open_plots_folder()
        output[P]=cf
        #if Control then give option to store in Controls folder
            
        try:
            root.destroy()
        except:
            pass
        if cf.is_control():
            root=tk.Tk()
            instruction=("Combined file {} appears to be a control "
                         "(no treatment) experiment.\n\n"
                         "Is this a good quality data?\n\nIf so, "
                         "would you like to copy this to the 'Controls' "
                         "database where it will available as a control "
                         "to all users?"
                         .format(cf.value))
            OB7=OptionBox(root,
                          title="PHENOS",
                          instruct=instruction,
                          options=["Yes",
                                   "No"],
                          default="Yes")
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            counter=0
            OPT=OB7.value
            if OPT=="Yes":
                copydatato(cf.value,targetfolder="Controls",
                           datafiles='shortcut',
                           plotfiles='shortcut',
                           dbaseobs='copy')
        else:
            root=tk.Tk()
            instruction=("Combined file {} has been entered.\n\n"
                         "Is this a good quality data?\n\nIf so, "
                         "would you like to copy this to the 'All' "
                         "database where it can be compared with "
                         "experiments by other users?"
                         .format(cf.value))
            OB7=OptionBox(root,
                          title="PHENOS",
                          instruct=instruction,
                          options=["Yes",
                                   "No"],
                          default="Yes")
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            counter=0
            OPT=OB7.value
            if OPT=="Yes":
                copydatato(cf.value,
                           targetfolder="All",
                           datafiles='shortcut',
                           plotfiles='shortcut',
                           dbaseobs='copy')
    return output
#

def delete_files(files,checkboxes=True):
    if type(files)!=list:
        LOG.critical("Should be passed list")
        sys.exit()
    if not files or files==[None]:
        return None
    for f in files:
        if type(f) in [str,unicode]:
            f=Files()[f]

        LOG.info("Deleting File {} from {}".format(str(f),
                                                   f.dbasenameroot))

        if not checkboxes:
            GOAHEAD="Yes"
        else:
            root=tk.Tk()
            instruction=("ARE YOU SURE YOU WANT TO DELETE\n\n"
                         "File ({})\t\n\n"
                         "and\t{} Readings in {}?"
                         .format(f.value,
                                 f["ncurves"].value,
                                 LOCS.currentuserfolder))
            OB4=OptionBox(root,
                          title="PHENOS",
                          instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            GOAHEAD=OB4.value
        if GOAHEAD=="Yes":
            fval=f.value
            exval=f["experimentid"]
            f.delete()
            #Also, delete any CombiFile derived from it
            CF=CombiFiles()
            cfa=CF.query_by_kwargs(experimentid=exval)
            delete_combifiles(cfa,checkboxes=False)
            #Also delete from Controls or All
            fa=Files("All").query_by_kwargs(fileid=fval)
            delete_files(fa,checkboxes=False)
            fc=Files("Controls").query_by_kwargs(fileid=fval)
            delete_files(fc,checkboxes=False)
    return True

def delete_combifiles(combifiles,checkboxes=True,delete_files_too=False):
    if type(combifiles)!=list:
        LOG.critical("Should be passed list")
        sys.exit()
    if not combifiles or combifiles==[None]:
        return None
    for cf in combifiles:
        if type(cf) in [str,unicode]:
            cf=CombiFiles()[cf]

        LOG.info("Deleting Combined file {} from {}".format(str(cf),
                                                            cf.dbasenameroot))

        if delete_files_too:
            delete_files(list(cf.yield_sourcefiles()),checkboxes=checkboxes)

        if not checkboxes:
            GOAHEAD="Yes"
        else:
            root=tk.Tk()
            instruction=("ARE YOU SURE YOU WANT TO DELETE\n\n"
                         "Combined file ({})\t\n\n"
                         "and\t{} CombiReadings in {}?\n\n"
                         "This will also delete any controlled "
                         "experiments based on this combined file"
                         .format(cf.value,
                                 cf["ncurves"].value,
                                 LOCS.currentuserfolder))
            OB4=OptionBox(root,
                          title="PHENOS",
                          instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            GOAHEAD=OB4.value
        if GOAHEAD=="Yes":
            cv=cf.value
            cdbnr=cf.dbasenameroot
            cf.delete()
            #Also remove reference from any other Files referring to this
            F=Files(cdbnr)
            fq=F.query_by_kwargs(combifile=cv)
            for f in fq:
                f.update_atoms(combifile=None)
            #Also delete any ControlledExperiments derived from it
            CE=ControlledExperiments()
            cea=CE.query_by_kwargs(combifile=cv)
            delete_controlledexperiments(cea,checkboxes=False)
            #And any experiments that use this as a control...
            ceac=CE.query_by_kwargs(controlfileid=cv)
            delete_controlledexperiments(ceac,checkboxes=False)
            #Also delete from Controls or All
            cfa=CombiFiles("All").query_by_kwargs(combifileid=cv)
            delete_combifiles(cfa,checkboxes=False,delete_files_too=True)
            cfc=CombiFiles("Controls").query_by_kwargs(combifileid=cv)
            delete_combifiles(cfc,checkboxes=False,delete_files_too=True)
    return True

def delete_controlledexperiments(controlledexperiments,checkboxes=True):
    if type(controlledexperiments)!=list:
        LOG.critical("Should be passed list")
        sys.exit()
    if not controlledexperiments or controlledexperiments==[None]:
        return None
    for ce in controlledexperiments:
        if not ce:
            return None
        if type(ce) in [str,unicode]:
            ce=ControlledExperiments()[ce]

        LOG.info("Deleting ControlledExperiment {}".format(str(ce)))

        if not checkboxes:
            GOAHEAD="Yes"
        else:
            root=tk.Tk()
            instruction=("ARE YOU SURE YOU WANT TO DELETE\n\n"
                         "ControlledExperiment({})\t\n\n"
                         "and\t{} ControlledReadings in {}?"
                         .format(ce.value,
                                 ce["ncurves"].value,
                                 LOCS.currentuserfolder))
            OB4=OptionBox(root,
                          title="PHENOS",
                          instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            GOAHEAD=OB4.value
        if GOAHEAD=="Yes":
            ce.delete()
            #Also delete from Controls or All
            cea=ControlledExperiments("All").query_by_kwargs(controlledexperimentid=ce.value)
            delete_controlledexperiments(cea,checkboxes=False)
            cec=ControlledExperiments("Controls").query_by_kwargs(controlledexperimentid=ce.value)
            delete_controlledexperiments(cec,checkboxes=False)
    return True

#
def main_rqtl():
    CE=ControlledExperiments()
    AlreadyExs=list(CE)
    UncontrolledExs=[CF for CF in CombiFiles()
                     if CF.value
                     not in CE.get_values_of_atom("combifile")]

#    genotypelookup=Strains().get_genotype_dict()
#    LOG.info("Got genotypelookup")
    
    PM=0.5
    LST=[]
    timefocusdict={}
    
    def pick_timefocus(combifile,controlcombifile,plusminus=PM):
        ST=combifile.timevalues()
        if not ST:
            LOG.error("no timevalues found for Combifile "+str(combifile))
            return None,None
        CT=controlcombifile.timevalues()
        if not CT:
            LOG.error("no timevalues found for ControlCombifile "+str(controlcombifile))
            return None,None
        minmax=min(max(ST),max(CT))
        nearest1=ST[closest_index(ST,minmax)]
        nearest2=CT[closest_index(CT,minmax)]
        middle=(nearest1+nearest2)/2.0
        return middle-plusminus,{"timefocus":middle-plusminus,
                                 "plusminus":plusminus,
                                 "cf_timevalues":ST,
                                 "cn_timevalues":CT}

    def timepoints_in_window(timepoints,timefocus,plusminus):
        return [t for t in timepoints
                if (timefocus-plusminus)<=t<=(timefocus+plusminus)]

    def timepoints_to_string(timepoints):
        return ",".join(["{:.1f}".format(t) for t in timepoints])

    def get_CFID(comfil,confil):
        return "{}_{}".format(comfil,confil)

    def get_TFPM(timfoc,plsmin):
            if timfoc:
                return "{:.1f}hrs+-{:.1f}".format(timfoc,plsmin)
            else:
                return ""

    def get_ISGEN(cob):
        if cob["genotyped"].value:
            return "YES"
        else:
            return "no"

    headers=["Controlled Experiment ID",
             "Treatment","Plate layout",
             "Combined file","Control file",
             "Time window","Array size",
             "Is Genotyped?","Already exists?"]
    lookup={}
    #New...
    for cf in UncontrolledExs:
        for cn in cf.return_scored_controls() or []:
            TF,TD=pick_timefocus(cf,cn)
            if TF is None:
                continue
            CFID=get_CFID(cf.value,cn.value)
            L=(CFID,
               cf["treatment"].value,
               cf["platelayout"].value,
               cf.value,
               cn.value,
               get_TFPM(TF,PM),
               cf["ncurves"].value,
               get_ISGEN(cf),
               "no")
            TD.update(dict(zip(headers,L)))
            TD.update({"cf":cf,
                       "controlcf":cn})
            lookup[CFID]=TD
            timefocusdict[cf.value]=TF
            LST.append(L)
    #Already created...
    LST2=[]
    for ce in CE:
        TF=ce["timefocus"].value
        PM2=ce["plusminus"].value
        cf=ce.get_source_combifile()
        cn=ce.get_control_combifile()
        TD={"ce":ce,
            "timefocus":TF,
            "plusminus":PM2,
            "cf":cf,
            "cf_timevalues":cf.timevalues(),
            "controlcf":cn,
            "cn_timevalues":cn.timevalues()}
        L=(ce.value,
           ce["treatment"].value,
           ce["platelayout"].value,
           ce["combifile"].value,
           ce["controlfileid"].value,
           get_TFPM(TF,PM2),
           ce["ncurves"].value,
           get_ISGEN(ce),
           "YES")
        TD.update(dict(zip(headers,L)))
        lookup[ce.value]=TD
        LST2.append(L)
    LST2.reverse()

    root=tk.Tk()
    TIT="PHENOS"
    instruction=("Select new controlled experiment(s) to create and "
                 "visualize\n Or previous controlled experiment(s) "
                 "to view.\n\n"
                 "<Delete> to remove or <Escape> to quit.\n\n"
                 "The time window (within which readings are "
                 "included and averaged) has been selected automatically. "
                 "However if you would like to change it, select and "
                 "hit <Insert> (N.B.: if this is an "
                 "existing controlled experiment, the earlier entry "
                 "will be replaced with the new one).\n\n"
                 "Please wait for completion.")
    if LST and LST2:
        JOINEDLST=LST+[tuple([""]*len(headers))]+LST2
    else:
        JOINEDLST=LST+LST2
    if LST:
        default=[t[0] for t in LST]
    elif LST2:
        default=LST2[0][0]
    else:
        default=None
    
    to_alter=[]
    def alter_timefocus(selections):
        for s in selections:
            to_alter.append(s)

    LB8=MultiColumnListbox(root,
                           title=TIT,
                           instruct=instruction,
                           headers=headers,
                           lists=JOINEDLST,
                           default=default,
                           selectmode="extended",
                           delete_fn=delete_controlledexperiments,
                           insert_fn=alter_timefocus)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    PICK=LB8.values
    #if type(PICK)!=list:
    #    PICK=[PICK]

    PICK2=[]
    if PICK[0]==None:
        for a in to_alter:
            TD=lookup[a]
            if TD["Already exists?"]=='YES':
                extrainstruction=("\n\nThis will replace the existing "
                                  "controlled experiment {}\n\n".format(a))
            else:
                extrainstruction=""
            instruction=("{}({}) has timepoints {}\n\n"
                         "{}(Control) has timepoints {}\n\n"
                         "Enter the time in hours at which the time window "
                         "is centred (the time focus): all time "
                         "points within this window (or equal to the "
                         "edges of it) are included and averaged together.\n"
                         "Optionally: add '+-' and a second number for the "
                         "width of the time window if you wish to change "
                         "this from the default (0.5 hours){}"
                         .format(TD["cf"].value,
                                 TD["cf"]["treatment"].value,
                                 timepoints_to_string(TD["cf_timevalues"]),
                                 TD["controlcf"].value,
                                 timepoints_to_string(TD["cn_timevalues"]),
                                 extrainstruction))

            while True:
                root=tk.Tk()
                EB3=EntryBox(root,title="PHENOS",instruct=instruction)
                root.focus_force()
                root.geometry(windowposition)
                root.mainloop()
                TIMEFOCUS=EB3.value
                if TIMEFOCUS in [None,""]:
                    return
                PLUSMINUS=0.5
                if "+-" in TIMEFOCUS:
                    TIMEFOCUS,PLUSMINUS=TIMEFOCUS.split("+-")
                try:
                    TIMEFOCUS=float(TIMEFOCUS)
                    PLUSMINUS=float(PLUSMINUS)
                except:
                    continue
                tfpm=get_TFPM(TIMEFOCUS,PLUSMINUS)
                LOG.info("Picked timefocus {} for {}"
                         .format(tfpm,a))
                STPs=timepoints_in_window(TD["cf_timevalues"],
                                          TIMEFOCUS,PLUSMINUS)
                CTPs=timepoints_in_window(TD["cn_timevalues"],
                                          TIMEFOCUS,PLUSMINUS)
                if not STPs or not CTPs:
                    instruction=("No timepoints in window {}. "
                                 "Try again. \n\n".format(tfpm)
                                 +instruction)
                    continue
                instruction2=("Treatment file {} timepoints {}\nwill be "
                              "averaged and compared to\n"
                              "Control file {} timepoints {}.\n\n{}"
                              "Are you happy to proceed with this?"
                              .format(TD["cf"].value,
                                      timepoints_to_string(STPs),
                                      TD["controlcf"].value,
                                      timepoints_to_string(CTPs),
                                      extrainstruction))
                root=tk.Tk()
                OB8=OptionBox(root,
                              title="PHENOS",
                              instruct=instruction2,
                              options=["Yes",
                                       "No"],
                              default="Yes")
                root.focus_force()
                root.geometry(windowposition)
                root.mainloop()
                counter=0
                OPT=OB8.value
                if OPT is None:
                    break
                if OPT=="No":
                    continue
                if OPT=="Yes":
                    lookup[a]["timefocus"]=TIMEFOCUS
                    lookup[a]["plusminus"]=PLUSMINUS
                    lookup[a]['Time crossover']=get_TFPM(TIMEFOCUS,PLUSMINUS)
                    if lookup[a]["Already exists?"]=="YES":
                        lookup[a]["Already exists?"]="no"
                        ce=lookup[a]["ce"]
                        LOG.info("Deleting {}".format(ce))
                        ce.delete()
                    PICK2.append(a)
                    break
        PICK=PICK2

    output={}
    
    showdraw=False if len(PICK)>1 else True
    for P in PICK:
        if lookup[P]["Already exists?"]=="YES":
            cf=lookup[P]['cf']
            drawn=cf.draw_ratios(show=True)
        else:
            cf=lookup[P]["cf"]
            cn=lookup[P]["controlcf"]
            Cex=ControlledExperiment.create_from_combifiles(cf,cn,
                                                            rounder="{:.4f}",
                                                            timefocus=lookup[P]["timefocus"],
                                                            plusminus=lookup[P]["plusminus"],
                                                            read=True,
                                                            store=True,
                                                            report=True)
            drawn=Cex.draw_ratios(show=showdraw)
            try:
                Cex.output_to_rQTL()
            except Exception as e:
                LOG.error("Unable to output_to_rqtl {} because {} {}"
                          .format(Cex.value,e,get_traceback()))


    return True

#
def main():
    root=tk.Tk()
    instruction=("What do you want to do?\n\n\n"
                 "(select an option below or hit ESCAPE to quit)")
    OB7=OptionBox(root,
                  title="PHENOS",
                  instruct=instruction,
                  options=["Rename & store platereader files",
                           "Combine/visualize renamed files",
                           "Generate rQTL input for combined files"],
                  default="Create visualizations")
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()

    OPT=OB7.value
    if OPT=="Rename & store platereader files":
        main_rename()
        main()
    elif OPT=="Combine/visualize renamed files":
        if not choose_user_folder({}):
            return
        if main_combine() is False:
            root=tk.Tk()
            instruction=("There are no new files in {} which can be combined"
                         .format(Locations().get_userpath()))
            OB8=OptionBox(root,
                          title="PHENOS",
                          instruct=instruction,
                          options=["OK"],
                          default="OK")
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            if not OB8.value:
                return
        main()
    elif OPT=="Generate rQTL input for combined files":
        if main_rqtl() is False:
            root=tk.Tk()
            instruction=("There are no new combined files in {}"
                         " for which rQTL input can be created"
                         .format(Locations().get_userpath()))
            OB9=OptionBox(root,
                          title="PHENOS",
                          instruct=instruction,
                          options=["OK"],
                          default="OK")
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            if not OB9.value:
                return
        main()
    elif OPT==None:
        return

#
if __name__=="__main__":
    setup_logging("INFO")
    sys.excepthook=log_uncaught_exceptions

    main()



