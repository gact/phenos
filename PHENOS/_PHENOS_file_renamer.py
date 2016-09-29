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
authors = ("Dave B. H. Barton")
version = "0.1"
#
platereader_output="C:\Users\localadmin1\Desktop\Platereader output"
LOCS=Locations()
FALL=Files("All")
PLO=PlateLayouts()

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
                           lst=LST,
                           default=LST[0][0],
                           delete_function=delete)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop() #waits for selection/cancel
    FILETORENAME=LB1.value
    LOG.info("user selected file {} to rename".format(FILETORENAME))
    return FILETORENAME

def summarise_file(filename):
    filepath=os.path.join(platereader_output,filename)
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
                            lst=LST,
                            default=default)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop() #waits for selection/cancel
    if LB1b.value:
        return shareddata,rowdata
    else:
        return False

def count_files_in(folder,dig=False,include=[".csv",".DAT"]):
    dm=DirectoryMonitor(folder,dig=dig,include=include,report=False)
    return len(dm)

def choose_user_folder(IGNORE=["Software Test","All","Controls"]):
    LST=[]
    for p in LOCS.datpaths:
        fp=os.path.basename(p)
        fpc=count_files_in(p)
        if fp not in IGNORE:
            LST.append((fp,fpc))
    LST.sort()
    DEF=os.path.basename(LOCS.currentdirectory)

    root=tk.Tk()
    LB2=MultiColumnListbox(root,
                           title="PHENOS",
                           instruct=("Select user folder.{}"
                                     "Or ESCAPE/<close> to save as tab "
                                     "file without further analysis"
                                     .format(os.linesep)),
                           headers=["User folder",
                                    "Number of files in folder"],
                           lst=LST,
                           default=DEF)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    USERFOLDER=LB2.value
    LOG.info("user selected folder {}".format(USERFOLDER))

    if USERFOLDER=="New folder":
        USERFOLDER=None
        instruction="Enter name for new folder"
        while not USERFOLDER:
            root=tk.Tk()
            EB1=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
            root.mainloop()
            USERFOLDER=EB1.value
            fullpath=os.path.join(LOCS["datafiles"],USERFOLDER)
            if os.path.exists(fullpath):
                instruction="{} already exists. Choose again.".format(USERFOLDER)
                LOG.error(instruction)
                USERFOLDER=None
            else:
                try:
                    LOCS.add_new_datafolder(USERFOLDER)
                except Exception as e:
                    instruction=("Can't create {} because {}. Choose again."
                                 .format(fullpath,e,get_traceback()))
                    LOG.error(instruction)
                    USERFOLDER=None
    elif USERFOLDER:
        LOCS.set_datpath(USERFOLDER)
        LOG.info("active folder set to {}".format(USERFOLDER))
    return USERFOLDER

def output_to_txt(sourcefilename,shareddata=None,rowdata=None,
                  extension="tab",
                  delimiter="\t",
                  spacer="\t",
                  ask=False,
                  replace=False,
                  **kwargs):
    headers=["well","isborder","minimum","maximum","measurements:"]

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

def choose_user_initials(userfolder):
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
                               lst=LST,
                               default=DEF)
        root.focus_force()
        root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
        root.mainloop()
        USERINITIALS=LB3.value

    if USERINITIALS=="*new*":
        USERINITIALS=None
        instruction="Enter new user initials (<=5 letters)"
        while not USERINITIALS:
            root=tk.Tk()
            EB2=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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

    return USERINITIALS

def choose_experiment_number(userfolder,userinitials):
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
                           lst=LST,
                           default=DEF)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    EXPNUMBER=LB4.value

    if EXPNUMBER=="*new* (other)":
        EXPNUMBER=None
        instruction="Enter new experiment number (0-255)"
        while not EXPNUMBER:
            root=tk.Tk()
            EB3=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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
    return EXPNUMBER

def choose_file_letter(userfolder,
                       userinitials,
                       experimentnumber):
    ok="abcdefghijklmnopqrstuvwxyz"
    FLST=Files(userfolder).get(user=userinitials,
                               experimentnumber=experimentnumber)
    if not FLST:
        FILELETTER="a"
        LST=[("*new* (a)",""),
             ("*new* (other)","")]
        INI={}
    else:
        INI={}
        if type(FLST)!=list:
            FLST=[FLST]
        for FL in FLST:
            INI[FL["fileletter"].value]=FL["filepath"].value
        LST=sorted(INI.items(),reverse=True)
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
                           lst=LST,
                           default=DEF,
                           notselectable=INI.keys())
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    FILELETTER=LB4.value

    if FILELETTER=="*new* (other)":
        FILELETTER=None
        instruction="Enter new file letter (a-z)"
        while not FILELETTER:
            root=tk.Tk()
            EB3=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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

    if not FILELETTER:
        return None
    if FILELETTER.startswith("*new* "):
        FILELETTER=FILELETTER[7:-1]
    return FILELETTER

def choose_treatment(userfolder,userinitials,experimentnumber,fileletter):
    FAd=FALL.get_values_of_atom("treatment")
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
                           lst=LST2,
                           default=DEF)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    TREATMENT=LB5.value

    if TREATMENT=="*new*":
        TREATMENT=None
        instruction="Enter new treatment name"
        while not TREATMENT:
            root=tk.Tk()
            EB4=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
            root.mainloop()
            TREATMENT=EB4.value
            if len(TREATMENT)>40:
                instruction="{} is too long. Choose again (<=40 characters).".format(TREATMENT)
                LOG.error(instruction)
                TREATMENT=None

    if TREATMENT=="YPD (control)":
        TREATMENT="YPD"
    return TREATMENT

def choose_layout(filename,userfolder,userinitials,
                  experimentnumber,fileletter,treatment,shareddata):
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
                                     "and save it under a new name."),
                           headers=["Layouts ({})".format(arraysize),
                                    "Number of files in All with layout"],
                           lst=LST,
                           default=DEF)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    LAYOUT=LB6.value

    if LAYOUT=="*browse*":
        LOC=LOCS["layouts"]
        INS="Select layout file, or <escape> to exit and create one"
        LAYOUT=None
        while not LAYOUT:
            root=tk.Tk()
            root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
            root.withdraw()
            filename=tkFileDialog.askopenfilename(initialdir=LOC,
                                                  title=INS)
            root.destroy()
            if not filename:
                return
            else:
                LAYOUT=os.path.splitext(os.path.basename(filename))[0]
            if LAYOUT in PL:
                INS=("{} already in PlateLayouts. Choose again."
                     .format(LAYOUT))
                LOG.error(INS)
                LAYOUT=None
            else:
                newpl=PlateLayout(filepath=os.path.basename(filename),
                                  layoutstring=LAYOUT)
                try:
                    newpl.read(store=True)
                    CAP=newpl["capacity"].value
                    if CAP!=arraysize:
                        INS=("Platelayout {} has size {}, "
                             "whereas {} has size {}. Choose again."
                             .format(newpl.get_fullpath(),
                                     CAP,
                                     filepath,
                                     arraysize))
                        LOG.error(INS)
                        LAYOUT=None
                except:
                    INS=("Couldn't read platelayout {}. Choose again."
                         .format(newpl.get_fullpath()))
                    LOG.error(INS)
                    LAYOUT=None

    return LAYOUT

def choose_orientation():
    root=tk.Tk()
    OB1=OptionBox(root,
                  title="PHENOS",
                  instruct=("Was the plate correctly oriented, "
                            "with well A1 at the back left,\nand the "
                            "word 'Singer' on the PlusPlate lid\n "
                            "facing you and the correct way up?"))
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    ORIENT=OB1.value
    if ORIENT=="Yes":
        return ""
    elif ORIENT=="No":
        LOG.error("Plate was incorrectly oriented. Will proceed on the "
                  "assumption that it was rotated 180 degrees from normal.")
        return "R"
    else:
        return ""

def choose_exclusions(userinitials,experimentnumber,fileletter,
                      treatment,layout,
                      shareddata,rowdata):
    if "emptyplate" in shareddata["platereaderprogram"]:
        return
    if fileletter=="a":
        return
    root=tk.Tk()
    OB2=OptionBox(root,
                  title="PHENOS",
                  instruct=("Are there any wells or samples you wish to "
                            "exclude from analysis, e.g. because of "
                            "contamination?"),
                  default="No")
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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
        if len(measures)>4:
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
                           lst=LST)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    EXCLUSIONS=LB7.value

    if not EXCLUSIONS:
        return None
    
    #format exclusions
    #first find any cases where all of a given strain have been selected
    
    ALLSTRAINS=LOOKUP.values()
    for well in EXCLUSIONS:
        strain=LOOKUP[well]
        if strain in ALLSTRAINS:
            ALLSTRAINS.remove(strain)
    
    watchlist={}
    for well in EXCLUSIONS:
        strain=LOOKUP[well]
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
        root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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
    return EXCLUSIONS

def choose_timeoffset(filename,userfolder,userinitials,
                      experimentnumber,fileletter,treatment,
                      layout,orientation,shareddata):
    #if emptyplate, then default = t-1
    LST=[("t-1 (empty plate)",""),
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
                           lst=LST,
                           default=DEF)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    TIMEOFFSET=LB7.value
    
    if TIMEOFFSET=="*other*":
        TIMEOFFSET=None
        instruction="Enter offset (>{})".format(LASTOFFSET)
        while not TIMEOFFSET:
            root=tk.Tk()
            EB5=EntryBox(root,title="PHENOS",instruct=instruction)
            root.focus_force()
            root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
            root.mainloop()
            TIMEOFFSET=EB5.value
            if TIMEOFFSET is None:
                return None
            try:
                TIMEOFFSET=int(TIMEOFFSET)
            except:
                instruction=("{} not a number. Choose again.")
                LOG.error(instruction)
                TIMEOFFSET=None
            if not LASTOFFSET<TIMEOFFSET<=255:
                instruction=("{} not OK. Must be {}-255. Choose again."
                             .format(LASTOFFSET,TIMEOFFSET))
                LOG.error(instruction)
                TIMEOFFSET=None
        TIMEOFFSET="t+{}".format(TIMEOFFSET)
    else:
        TIMEOFFSET=TIMEOFFSET.split(" ")[0]
    return TIMEOFFSET


def choose_note():
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
        root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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
    return NOTE

def handle_file(filename,userfolder,userinitials,
                experimentnumber,fileletter,treatment,
                layout,orientation,exclusions,timeoffset,
                note,extension):
    kwargs=locals().copy()
    filepath=os.path.join(platereader_output,filename)
    targetfilename=build_filetitle(**kwargs)
    targetfilepath=os.path.join(LOCS.currentdirectory,
                                targetfilename)
    
    INS=("Original filename=    {}\n\n"
         "Final filename=    {}\n\n"
         "Copy from {} to {}?\n"
         "N.B. This may take a minute. Please wait."
         .format(filename,
                 targetfilename,
                 platereader_output,
                 LOCS.currentdirectory))

    root=tk.Tk()
    OB3=OptionBox(root,
                  title="PHENOS",
                  instruct=INS)
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    answer=OB3.value
    
    if answer=="Yes":
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
            return
        #wait for copy to complete
        
        #Store File object & Readings
        try:
            fo=File(filepath=str(targetfilename),
                    platelayout=str(layout),
                    dbasenameroot=userfolder)
            fo.calculate_all()
            fo.store()
            readingcount=fo.read()
            fo.draw_if_empty()
            LOG.info("Created File({}) and added to {}"
                     "along with {} Readings"
                     .format(fo.value,
                             LOCS.currentdbasepath,
                             readingcount))
        except Exception as e:
            LOG.error("Unable to create/store File for {}"
                      "because {} {}"
                      .format(targetfilename,e,get_traceback()))
            return
        #Store RenamedFile
        try:
            rf=RenamedFile(originalfilename=filename,
                           originalfolder=platereader_output,
                           renamedfilename=targetfilename,
                           renamedfolder=LOCS.currentdirectory)
            rf["datecreated"].calculate()
            rf.store()
            LOG.info("Created {}".format(rf))
        except Exception as e:
            LOG.error("Couldn't created RenamedFile because {} {}"
                      .format(e,get_traceback()))
            return
        return 

#
def main_rename():
    repeat=True
    #SELECT AND EYEBALL DATA FILE (Autoread info)
    while repeat:
        FILETORENAME=choose_file_to_rename()
        if not FILETORENAME:
            return
        answer=summarise_file(FILETORENAME)
        if answer is False:
            repeat=True
        else:
            SHAREDDATA,ROWDATA=answer
            repeat=False
    #SELECT USER FOLDER (Default to Locations().currentdirectory)
    USERFOLDER=choose_user_folder()
    if not USERFOLDER:
        #OPTION: CONTINUE WITHOUT DATA? (Just generates txt and basic curves)
        output_to_txt(FILETORENAME,SHAREDDATA,ROWDATA)
        return
    else:
        #SELECT INITIALS (Default to last one in Files())
        USERINITIALS=choose_user_initials(USERFOLDER)
    
    #SELECT EXPERIMENTNUMBER (Default to next highest. If already existing,
    EXPNUMBER=choose_experiment_number(USERFOLDER,USERINITIALS)
    if EXPNUMBER is None:
        return

    #SELECT FILELETTER (Deduce most likely, e.g. emptyplate program = 'a',
    #                   next highest in folder = 'a'+1 etc)
    FILELETTER=choose_file_letter(USERFOLDER,USERINITIALS,EXPNUMBER)
    if not FILELETTER:
        return
    # then change following defaults)

    #SELECT TREATMENT (Default to YPD, but check temperature too.)
    TREATMENT=choose_treatment(USERFOLDER,USERINITIALS,EXPNUMBER,FILELETTER)
    if not TREATMENT:
        return

    #SELECT LAYOUT (Default to e.g. Basic384 if a 384 program. ADVANCED:
    #                suggest from 'fingerprint'?)
    #CHECK THAT LAYOUT MATCHES RESULTS ARRAYDENSITY AND CONSISTENT WITH
    #ANY EARLIER FILE

    LAYOUT=choose_layout(FILETORENAME,USERFOLDER,USERINITIALS,
                         EXPNUMBER,FILELETTER,TREATMENT,SHAREDDATA)
    if not LAYOUT:
        return


    ORIENT=choose_orientation()
    if ORIENT is None:
        return

    #SELECT EXCLUSIONS
    EXCLUSIONS=choose_exclusions(USERINITIALS,EXPNUMBER,FILELETTER,
                                 TREATMENT,LAYOUT,SHAREDDATA,ROWDATA)

    #SELECT TIMEOFFSET (Deduce from file datetime)
    TIMEOFFSET=choose_timeoffset(FILETORENAME,USERFOLDER,USERINITIALS,
                                 EXPNUMBER,FILELETTER,TREATMENT,
                                 LAYOUT,ORIENT,SHAREDDATA)
    if not TIMEOFFSET:
        return

    #SELECT NOTE (Deduce from previous)
    NOTE=choose_note()
    if not type(NOTE)==str:
        print "NOT A STRING"
        NOTE=""

    CONCLUSION=handle_file(filename=FILETORENAME,
                           userfolder=USERFOLDER,
                           userinitials=USERINITIALS,
                           experimentnumber=EXPNUMBER,
                           fileletter=FILELETTER,
                           treatment=TREATMENT,
                           layout=LAYOUT,
                           orientation=ORIENT,
                           exclusions=EXCLUSIONS,
                           timeoffset=TIMEOFFSET,
                           note=NOTE,
                           extension=SHAREDDATA["extension"])
    #NOW WHAT?
    lastrenamedfile=RenamedFiles()[-1]
    renamedfilename=lastrenamedfile["renamedfilename"].value
    lastfile=Files()[-1]

    root=tk.Tk()
    instruction=("Created:\n\n"
                 "Last RenamedFile    '{}'\n\n"
                 "and   File({})\n\n"
                 "and   {} Readings from {}?\n\n"
                 "What do you wish to do next?"
                 .format(renamedfilename,
                         lastfile.value,
                         lastfile["ncurves"].value,
                         os.path.basename(LOCS.currentdbasepath)))
    OB5=OptionBox(root,
                  title="PHENOS",
                  instruct=instruction,
                  options=["Rename another","Undo","Combine & display Files","Quit"],
                  default="Combine Files")
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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

def delete(renamedfile,checkboxes=True):
    if not renamedfile:
        return None
    if type(renamedfile) in [str,unicode]:
        renamedfile=RenamedFiles()[renamedfile]

    renamedfilename=renamedfile["renamedfilename"].value
    fileob=renamedfile.get_file()

    if not checkboxes:
        CF=fileob["combifile"]
        if CF.is_valid():
            CF.delete()
        if CF in CombiFiles("All"):
            CombiFiles
        if fileob:
            fileob.delete()
        
        renamedfile.delete()
    else:
        root=tk.Tk()
        instruction=("ARE YOU SURE YOU WANT TO DELETE\n\n"
                     "Last RenamedFile\t'{}'\n\n"
                     "and\tFile({})\n\n"
                     "and\t{} Readings in {}?"
                     .format(renamedfilename,
                             fileob.value,
                             fileob["ncurves"].value,
                             os.path.basename(LOCS.currentdbasepath)))
        OB4=OptionBox(root,
                      title="PHENOS",
                      instruct=instruction)
        root.focus_force()
        root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
        root.mainloop()
        GOAHEAD=OB4.value
        if GOAHEAD=="Yes":
            renamedfile.delete()
            fileob.delete()
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
                             os.path.basename(LOCS.currentdbasepath)))
        OB4=OptionBox(root,
                      title="PHENOS",
                      instruct=instruction)
        root.focus_force()
        root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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
            root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
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


def main_combine():
    F=Files()
    combifiledict=F.get_combifile_dict(save=False,
                                       read=False,
                                       alreadymade=False)
    """
    NEW=defaultdict(list)
    OLD=defaultdict(list)
    for f in F:
        cf=f["combifile"].value
        if cf:
            OLD[cf].append(f)
        else:
            NEW[f["experimentid"].value].append(f)
    sortable=[]
    filelookup={}
    for eid,fobs in NEW.items():
        CD=combidict(*fobs)
        cfid=CombiFileID.create_from_files(fobs,**CD)
        filelookup[cfid]=fobs
        trtmnts=CD["treatment"]
        assert len(trtmnts)==1
        trtmnt=trtmnts[0]
        tmstmps=CD["experimenttimestamp"]
        tmstmp=min(CD["experimenttimestamp"])
        tmstmpTXT=time.asctime(time.localtime(tmstmp))
        sortable.append(([cfid,trtmnt,tmstmpTXT],
                        tmstmp))
        sortable.sort(key=lambda t:t[1],reverse=True)
    LST=[tuple(l) for l,t in sortable]
    """
    LST=[cf for cf in combifiledict.values()]
    LST.sort(key=lambda cf:getattr(cf,"timestamp",0),reverse=True)

    def timeconvert(tv):
        if tv:
            return time.asctime(time.localtime(tv))
        return ""

    LST2=[(cf.value,
           cf["treatment"].value,
           timeconvert(getattr(cf,"timestamp","")))
          for cf in LST]
    if not LST2:
        LOG.error("No combifiles to create in {}"
                  .format(Locations().currentdirectory))
        return None

    headers=["Files","Treatment","Timestamp of first"]
    
    root=tk.Tk()
    TIT="PHENOS: '{}'".format(build_filetitle(**locals().copy()))
    instruction=("Select combifile(s) to create and visualize\n"
                 "or <Escape> to quit.\n\n"
                 "PHENOS will close on completion.")
    LB7=MultiColumnListbox(root,
                           title=TIT,
                           instruct=instruction,
                           headers=headers,
                           lst=LST2,
                           default=LST2[0][0],
                           selectmode="extended")
    root.focus_force()
    root.geometry('{}x{}+{}+{}'.format(1100,800,100,100))
    root.mainloop()
    PICK=LB7.value
    if type(PICK)!=list:
        PICK=[PICK]
    output={}
    for P in PICK:
        CF=combifiledict[P]
        CF.save(read=True)
        print CF
        LOG.info("Illustrating {}".format(CF))
        CF.illustrate()
        output[P]=CF
    return output

#
if __name__=="__main__":
    setup_logging("INFO")
    sys.excepthook=log_uncaught_exceptions
    
    main_rename()
    #main_combine()
    



