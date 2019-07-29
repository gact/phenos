#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
"""

################################################################################

import os, sys, string, operator
from phenos import *
import tkFileDialog
from types import MethodType
from collections import defaultdict,Counter
from random import sample
from itertools import groupby, count, izip_longest
from string import uppercase
from pprint import pprint
import csv
import vcf
import gc
from phenos import flatten
import Bio
#from Bio import SeqIO
#from Bio.SeqFeature import SeqFeature, FeatureLocation
#from Bio.Alphabet import generic_dna
from BCBio import GFF


################################################################################

filename = os.path.basename(__file__)
authors = ("David B. H. Barton")
version = "0.1"
#
LOCS=Locations()
windowposition='{}x{}+{}+{}'.format(*LOCS.windowposition)
platereader_output=LOCS.platereader_output

startcodons=["ATG"]
stopcodons=["TAG","TAA","TGA"]
intronstarts=["GT","GC"]
intronends=["AG"]

intronsequences={}
specialcases=[] 

#https://stackoverflow.com/questions/25744059/manipulating-a-gff-file-with-biopython


class AFVCFLocations(object):
    """
    Singleton class that stores key locations and reads/writes them to
    a config file
    """
    _shared_state={}
    _L={"scriptdirectory":scriptdir(),
        "config_filepath":os.path.join(scriptdir(),"afvcfconfig.txt"),
        "gff_filedir":scriptdir(),
        "gff_filepath":None,
        "vcf_filedir":None,
        "vcf_filepath":None,
        "chralias_filedir":None,
        "chralias_filepath":None,
        "stralias_filedir":None,
        "stralias_filepath":None,
        "dnaallelesperstrainfilepath":None,
        "dnaallelesperstrainfiledir":None,
        "proteinallelesperstrainfilepath":None,
        "proteinallelesperstrainfiledir":None,
        "alleledetailsfilepath":None,
        "alleledetailsfiledir":None,
        "outputdir":None}
    _T={"locations":Locations(),
        "userfolder":None,
        "gffreader":None,
        "chrnames":None,
        "strainnames":None,
        "combifileobjects":None,
        "selectedregions":None,
        "plotnames":None,
        "dnaallelestrainsshareddata":None,
        "dnaallelestrainsrowdictionary":None,
        "proteinallelestrainsshareddata":None,
        "proteinallelestrainsrowdictionary":None,
        "savepaths":None,
        "proteinallelestrainsrowdictionary":None}

    def __init__(self):
        self.__dict__ = self._shared_state

        self.CP=ConfigParser.SafeConfigParser()
        self.CP.optionxform = str #prevents section header cases from being changed
        section="Locations"
        if not self.CP.has_section(section): self.CP.add_section(section)

        if not self.update_from_config_file():
            self.update_to_config_file()

    def update_from_config_file(self):
        if not os.path.exists(self.__class__._L["config_filepath"]):
            return
        self.CP.read(self.__class__._L["config_filepath"])

        def safeget(section,defaultheader,defaultcontent):
            if not self.CP.has_section(section):
                return None
            try:
                output=self.CP.get(section,defaultheader,defaultcontent)
                if output=="None":
                    return None
                return output
            except ConfigParser.NoOptionError:
                return defaultcontent

        def getall(section,default):
            if not self.CP.has_section(section):
                return None
            return dict(self.CP.items(section))

        new_L={}
        for k,v in self.__class__._L.items():
            new_L[k]=safeget("Locations",k,None)
        self.__class__._L=new_L
        return new_L

    def update_to_config_file(self):
        for k,v in self.__class__._L.items():
            self.CP.set("Locations",k,str(v))
        with open(self.__class__._L["config_filepath"],'w') as configfile:
            self.CP.write(configfile)
        return self.__class__._L["config_filepath"]

    def open_location(self):
        open_on_Windows(os.path.dirname(self.__class__._L["config_filepath"]))

    def __getitem__(self,key):
        if key in self.__class__._L:
            return self.__class__._L.get(key,None)
        elif key in self.__class__._T:
            return self.__class__._T.get(key,None)

    def get(self,key,defaultvalue):
        if key in self.__class__._L:
            return self.__class__._L[key]
        elif key in self.__class__._T:
            return self.__class__._T[key]
        else:
            return defaultvalue

    def __setitem__(self,key,value):
        if key in self.__class__._L:
            self.__class__._L[key]=value
            self.update_to_config_file()
            return True
        elif key in self.__class__._T:
            self.__class__._T[key]=value
            return True
        return False
#
def fix_savepath(filepath):
    filepath=os.path.normpath(filepath)
    DIR,FNM=os.path.dirname(filepath),os.path.basename(filepath)
    badchars=set(FNM)-set(" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMN"
                          "OPQRSTUVWXYZ0123456789"
                          ".,_+-=;!^~()[]'@&#%$\\/")
    for chartr in badchars:
        FNM=FNM.replace(chartr,"~")
    return os.path.join(DIR,FNM)

class AlleleStrainsReader(DATRecoveryFile):
    """
    """
    include_in_format_search=True
    delimiter="\t"
    checks=[("A1","region",None),
            ("B1","length",None),
            ("C1","N_alleles",None)]
    ranges=[("D1:XFD1","strainnames"),
            ("A2:A1048576","regionnames"),
            ("B2:B1048576","regionlengths"),
            ("C2:C1048576","totalalleles"),
            ("D2:XFD1048576","data")]

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

            SN=self.shareddata["strainorder"]=dataranges["strainnames"]
            GN=self.shareddata["regionnames"]=dataranges["regionnames"]
            self.shareddata["regionlengths"]=dataranges["regionlengths"]
            self.shareddata["totalalleles"]=[int(s) for s in dataranges["totalalleles"]]

            self.rowdata={}

            for i,row in enumerate(dataranges["data"]):
                self.rowdata[GN[i]]={sn:gn for sn,gn
                                     in zip(SN,row)}

            self.shareddata["n_strains"]=len(SN)
            self.shareddata["n_feats"]=i+1

            return self.shareddata,self.rowdata

class CurvesWithoutAgar_Alleles(ViewWrapper):
    def __init__(self,combifileobslist,gapname,colordict,#show=True,
                 suffix="colored by allele",**kwargs):
        ID=",".join([cf.value for cf in combifileobslist])
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=None#get_checked_savepath(combifileob,**kwargs)

        savepath=os.path.join(GDIR,"{}_{}.png".format(ID,gapname))
        savepath=fix_savepath(savepath)
        print ">",savepath

        if savepath!=False or kwargs.get("overwrite",False):
            recs=[]
            for cfo in combifileobslist:
                recs+=list(cfo.yield_records())
            strainnames=[cr["strain"].value for cr in recs]
            colorvals=[colordict.get(sn,"grey") for sn in strainnames]
            
            kwargs2=dict(timevalues=[cr.timevalues() for cr in recs],
                         measurements=[cr["rawmeasuredvaluesminusagar"]
                                       for cr in recs],
                         yaxislabel='OD600 minus agar',
                         colorvalues=colorvals,
                         legendlabel='allele index',
                         title=ID,
                         savepath=savepath,
                         show=True)
            kwargs2.update(kwargs)
            try:
                viewob=CurvePlot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()
                LOG.error("Couldn't plot {},{}".format(combifileob.value,
                                                       e,
                                                       get_traceback()))
        self.__dict__.update(kwargs2)

class CurvesWithoutAgar_Alleles2(ViewWrapper):
    def __init__(self,
                 combifileobslist, #list of combifile objects to be plotted
                 regionnames, #list of the regions for which alleles are being shown
                 regioncolordict,
                 prefix="Growth by allele",#show=True,
                 suffix="",
                 dnaorprotein="dna",
                 savedir=scriptdir(),
                 **kwargs):
        """
        Separate plots for each allele, but multiple experiments
        combined in different colors
        """

        #print list(colordict.items())[:2]

        titlelist=[]
        keyedbyallele=defaultdict(list)
        xlist=[]
        ylist=[]
        cfnames=[]
        trtments=[]
        savepaths=[]
        for cfo in combifileobslist:
            cfnames.append(cfo.value)
            TM=cfo["treatment"].value
            if TM not in trtments: trtments.append(TM)
            cfoID=cfo.value
            for rec in cfo.yield_records():
                #print ">",rec
                for regionname in regionnames:
                    #print ">>",regionname
                    if regionname not in regioncolordict:
                        LOG.warning("Region {} not in selected allele file"
                                    .format(regionname))
                        continue
                    colordict_for_region=regioncolordict[regionname]
                    strain=rec["strain"].value
                    if strain not in colordict_for_region:
                        LOG.warning("Strain {} from {} is not in selected allele file"
                                    .format(strain,cfoID))
                        allelenumber="unknown"
                    else:
                        allelenumber=colordict_for_region[strain]
                    keyedbyallele[(regionname,allelenumber)].append(rec)
        for (regionname,allelenumber),recs in keyedbyallele.items():
            #print regionname,allelenumber,len(recs)
            title=("{} {} allele {} ({} crvs, exp {}, trtmnt {})"
                   .format(regionname,
                           dnaorprotein,
                           allelenumber,
                           len(recs),
                           ",".join(cfnames),
                           ",".join(trtments)))
            savename=("{} {} allele {} ({} {}).png"
                      .format(regionname,
                              dnaorprotein,
                              allelenumber,
                              ",".join(cfnames),
                              ",".join(trtments)))
            savefolder=("{} {}"
                      .format(",".join(cfnames),
                              ",".join(trtments)))
            savepath=os.path.join(savedir,savefolder,savename)
            savepath=fix_savepath(savepath)
            savepaths.append(savepath)
            print savepath
            CV=[cr["combifile"].value for cr in recs]
            TV=[cr.timevalues() for cr in recs]
            MS=[cr["rawmeasuredvaluesminusagar"] for cr in recs]
            kwargs2=dict(timevalues=TV,
                         measurements=MS,
                         yaxislabel='OD600 minus agar',
                         colorvalues=CV,
                         legendlabel='experiment',
                         title=title,
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                print kwargs2.keys()
                viewob=CurvePlot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()
                LOG.error("Couldn't plot {} because {} {}".format(savepath,
                                                                  e,
                                                                  get_traceback()))
        self.savepaths=savepaths

def count_files_in(folder,dig=False,include=[".csv",".DAT"]):
    dm=DirectoryMonitor(folder,dig=dig,include=include,report=False)
    return len(dm)

def unpack(obj):
    print obj.__class__.__name__
    print type(obj)
    for variable in sorted(obj.__dict__.keys()):
        print variable,":",obj.__dict__[variable]
    print "_"*30

def display_align(sequences,start,end,strand,rowlength=60):
    """
    display_align(["ATGAGAATAGTGCCAGAAAAGCTGGTGTTCAAGGCTCCCCTTAATAAACAATCAACAGAGTATATAAAGCTCGAGAACGATGGTGAAAAGAGAGTTATATTTAAAGTGAGGACTAGTGCTCCCACAAAGTATTGTGTGAGGCCCAATGTGGCCATCATAGGTGCTCATGAAAGTGTAAATGTCCAAATTGTTTTCCTTGGATTACCCAAGTCAACCGCTGACGATGAAATGGACCAAAAACGAGACAAATTCTTGATCGTTACACTTCCTATCCCGGCAGCTTACCAAAACGTGGAGGATGGCGAGCTGTTGTCCGATTGGCCTAATCTGGAAGAGCAGTACAAAGATGACATAGTCTTCAAGAAGATCAAAATATTTCACTCCGTGTTACCGAAAAGAAAACCGTCTGGAAACCACGATGCAGAATCAGCAAGAGCGCCATCAGCAGGTAACGGGCAAAGTCTGAGTTCCAGAGCATTGCTTATCATCACCGTTATCGCATTGCTCGTCGGCTGGATATACTACTGA",
                   "ATGAGAATAGTGCCACAAAAGCTGGTGTTCAAGGCTCCCCTTAATAAACAATCAACAGAGTATATAAAGCTCGAGAACGATGGTGAAAAGAGAGTTATATTTAAAGTGAGGACTAGTGCTCCCACAAAGTATTGTGTGAGGCCCAATGTGGCCATCATAGGTGCTCATGAAAGTGTAAATGTCCAAATTGTTTTCCTTGGATTACCCAAGTCAACCGCTGACGATGAAATGGACCAAAAACGAGACAAATTCTTGATCGTTACACTTCCTATCCCGGCAGCTTACCAAAACGTGGAGGATGGCGAGCTGTTGTCCGATTGGCCTAATCTGGAAGAGCAGTACAAAGATGACATAGTCTTCAAGAAGATCAAAATATTTCACTCCGTGTTACCGAAAAGAAAACCGTCTGGAAACCACGATGCAGAATCAGCAAGAGCGCCATCAGCAGGTAACGGGCAAAGTCTGAGTTCCAGAGCATTGCTTATCATCACCGTTATCGCATTGCTCGTCGGCTGGATATACTACTGA"],
                   46564,47058,-1)
    """
    if strand==1:
        bps=range(start,end)
    elif strand==-1:
        bps=range(end-1,start-1,-1)
    maxlen=max([len(s) for s in sequences])
    indices=range(0,maxlen+1,rowlength)
    for S,E in get_kmer_list(indices+[maxlen+1],2):
        bpchunk=[str(bp) for bp in bps[S:E]]
        #stack bp numbers
        maxbpchunklen=max([len(bpc) for bpc in bpchunk])
        zeropadded=[bpc.zfill(maxbpchunklen) for bpc in bpchunk]
        stacked=zip(*zeropadded)
        for stck in stacked:
            print ''.join(stck)
        chunks=[sequence[S:E] for sequence in sequences]
        diffs=[" " if len(set(slice))==1 else "^" for slice in zip(*chunks)]
        diffstring=''.join(diffs)
        predif=diffstring.replace(" ",".")
        predif2=predif.replace("^","V")
        print predif2
        for chnk in chunks:
            print chnk
        print diffstring

def get_kmer_list(iterable,k=2):
    """reduces len of iterable by k-1"""
    return [iterable[x:x+k] for x in range(len(iterable)+1-k)]

def overlap_status(S1,E1,ID1,S2,E2,ID2,report=False):
    """
    S1,E1 generally being the smaller range (e.g. the variant)
    S2,E2 generally being the larger (e.g. the feature)

    possibleresults=["equals","contained within","contains","doesn't overlap","overlaps"]
    """
    #assert E1>=S1
    #assert E2>=S2
    Rng1=set(range(S1,E1))
    if report: print sorted(Rng1)
    Rng2=set(range(S2,E2))
    if report: print sorted(Rng2)
    if Rng1==Rng2:
        if report: print "{}-{} ({}) equals {}-{} ({})".format(S1,E1,ID1,S2,E2,ID2)
        return "equals"
    if Rng1.issubset(Rng2):
        if report: print "{}-{} ({}) contained within {}-{} ({})".format(S1,E1,ID1,S2,E2,ID2)
        return "contained within"
    elif Rng2.issubset(Rng1):
        if report: print "{}-{} ({}) contains {}-{} ({})".format(S1,E1,ID1,S2,E2,ID2)
        return "contains"
    elif not Rng1.intersection(Rng2):
        if report: print "{}-{} ({}) doesn't overlap {}-{} ({})".format(S1,E1,ID1,S2,E2,ID2)
        return "doesn't overlap"
    else:
        if report: print "{}-{} ({}) overlaps {}-{} ({})".format(S1,E1,ID1,S2,E2,ID2)
        return "overlaps"


class IndexingError(Exception):
    pass

class PassThroughDict(dict):
    def __getitem__(self,query):
        return query


def rome(roman_num):
     d = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}
     nl = list(roman_num)
     sum = d[nl[len(nl)-1]]
     for i in range(len(nl)-1,0,-1):
             if d[nl[i]]>d[nl[i-1]]:
                     sum -= d[nl[i-1]]
             else:
                     sum += d[nl[i-1]]
     return sum

def letcode(num):
    """
    1=A,27=AA,28=AB
    """
    assert num>0
    title=''
    while num:
        mod=(num-1) % 26
        num=int((num - mod) / 26)  
        title+=uppercase[mod]
    return title[::-1]

def convert_chrName_to_number(chrName):
    if chrName.startswith("chr"):
        chrName=chrName[3:]
    if chrName=="mt":
        return 100
    return rome(chrName)

def details_summary(listformat):
    """
    e.g. [[156, 'C', T], [182, 'A', G], [191, 'C', 'C'], [699, 'T', C]]
    produces "(156,182,191,699) T.G.c.C"
    """
    indices=[]
    output=[]
    for tup in listformat:
        ind,ref,gen=tup
        gen=str(gen)
        indices.append(ind)
        if gen==ref:
            output.append(gen.lower())
        else:
            output.append(gen)
    return str(tuple(indices))+" "+".".join(output)

def get_chunks(sequence,listformat):
    """
    e.g
    sequence="GGGAAATTTCCC"
    listformat=[[2,3,'G','A'],[6,7,'T','C'],[8,10,'TC','TCC']]
    keepchunks=["GG","AAA","TT","CC"]
    swapchunks=["G","T","TC"]
    """
    sequence=str(sequence)
    keepchunks=[]
    swapchunks=[]
    indexoffset=0
    #print "_"*50
    #print sequence
    #print listformat
    #print "_"*50
    listformat.sort()
    for start,stop,ref,gen in listformat:
        #assert stop-start==len(ref)
        originalstart=start
        originalstop=stop
        #index-=1 #zero-indexing correction
        #print "BEFORE",index
        start+=indexoffset
        stop+=indexoffset
        #print "AFTER",index
        keepchunk=sequence[:start]
        keepchunks.append(keepchunk)
        swapchunk=sequence[start:stop]
        swapchunks.append(swapchunk)
        #print ">",(index,ref,gen),"=",keepchunk,swapchunk
        if swapchunk!=ref:
            print type(sequence),sequence
            print listformat
            raise IndexingError("list says reference is {} but in sequence"
                                 "index {} is {}".format(ref,originalstart,swapchunk))
        sequence=sequence[stop:]
        indexoffset+=-(stop)
        #print "sequence shortened to",sequence,"with offset",indexoffset
    keepchunks.append(sequence)
    return keepchunks,swapchunks

def knitlists(firstlist,secondlist):
    output=flatten(izip_longest(firstlist,secondlist))[:-1]
    return [str(o) for o in output]

def sequence_change(sequence,listformat):
    """
    
    """
    #oldseq=Bio.Seq.Seq(str(sequence))
    keepchunks,swapchunks=get_chunks(sequence,listformat)
    try:
        keepchunks,swapchunks=get_chunks(sequence,listformat)
    except Exception as e:
        error="Problem with sequence_change: {}".format(e)
        return error
        #aise IndexingError(error)
    replacechunks=[str(d) for a,b,c,d in listformat]
    newseqstr=''.join(knitlists(keepchunks,replacechunks))
    return newseqstr

def Xprotein_change_summary(sequence,listformat):
    """
    WIP
    
    """
    #WIP
    oldseq=Bio.Seq.Seq(str(sequence))
    oldprot=oldseq.translate()
    try:
        keepchunks,swapchunks=get_chunks(sequence,listformat)
        print swapchunks
    except Exception as e:
        error="Problem with protein: {}".format(e)
        return error
        #aise IndexingError(error)
    replacechunks=[str(d) for a,b,c,d in listformat]
    newseqstr=''.join(knitlists(keepchunks,replacechunks))
    newseq=Bio.Seq.Seq(newseqstr)
    newprot=newseq.translate()
    print note_changes(str(oldprot),str(newprot))
    sys.exit()
    return note_changes(str(oldprot),str(newprot))

def note_changes(sequence1,sequence2):
    """
    does not smartly align sequences, so can't accurately
    note insertions or deletions
    """
    if sequence1==sequence2: return []
    output=[]
    for i,(a,b) in enumerate(izip_longest(sequence1,sequence2)):
        if a!=b:
            output.append((i,a,b))
    output=compact_adjacent(output)
    return output

def compact_adjacent(listformat):
    """
    Adjacent changes e.g. (275, 'L', 'A'), (276, 'A', 'R')
    should be collapsed to (275, 'LA', 'AR')
    test=[(140, 'L', 'F'),
      (274, 'T', 'N'), (275, 'L', 'A'),
      (278, 'A', 'P'), (279, 'R', 'Y'), (280, 'S', 'P'), (281, 'P', 'G'), (282, 'Y', 'E'), (283, 'P', 'Q'), (284, 'G', 'D'), (285, 'E', 'A'), (286, 'Q', 'L'), (287, 'D', 'G'), (288, 'A', 'Q'),
      (290, 'G', 'N'), (291, 'Q', 'W'), (292, 'L', 'K'),
      (294, 'W', 'Y'), (295, 'K', 'L'), (296, 'N', 'S'),
      (298, 'L', 'G'), (299, 'S', 'W'), (300, 'Y', 'V'), (301, 'G', 'S'), (302, 'W', 'L'), (303, 'V', 'F'), (304, 'S', 'E'), (305, 'L', 'S'),
      (307, 'E', 'K'), (308, 'S', 'H'), (309, 'F', 'A'), (310, 'K', 'R'), (311, 'H', 'L'), (312, 'A', 'L'), (313, 'R', 'K'), (314, 'L', 'D'), (315, 'L', 'V'), (316, 'K', 'M'), (317, 'D', 'I'), (318, 'V', 'F'), (319, 'M', 'L'),
      (321, 'F', 'A'), (322, 'L', 'W'), (323, 'I', 'F'), (324, 'A', 'I'), (325, 'W', 'I'), (326, 'F', 'S'), (327, 'I', 'D'), (328, 'I', 'S'), (329, 'S', 'I'), (330, 'D', 'T'), (331, 'S', 'T'),
      (333, 'T', 'N'), (334, 'T', 'S'), (335, 'I', 'T'), (336, 'N', 'A'), (337, 'S', 'V'), (338, 'T', 'L'), (339, 'A', 'F'), (340, 'V', 'S'), (341, 'L', 'K'), (342, 'F', 'A'), (343, 'S', 'E'), (344, 'K', 'L'), (345, 'A', 'H'), (346, 'E', 'M'), (347, 'L', 'S'), (348, 'H', 'T'), (349, 'M', 'L'), (350, 'S', 'N'), (351, 'T', 'L'), (352, 'L', 'I'), (353, 'N', 'M'), (354, 'L', 'I'), (355, 'I', 'S'), (356, 'M', 'V'), (357, 'I', 'L'), (358, 'S', 'T')]
    """
    output=[]
    laststart=-1
    compacting=None
    for (start1,original1,change1),(start2,original2,change2) in get_kmer_list(listformat,k=2):
        if original1 is None: original1=""
        if original2 is None: original2=""
        if change1 is None: change1=""
        if change2 is None: change2=""

        if start2==start1+1:
            if not compacting:
                compacting=[start1,original1+original2,change1+change2]
            else:
                compacting[1]+=original2
                compacting[2]+=change2
        else:
            if not compacting:
                output.append([start1,original1,change1])
            else:
                output.append(compacting)
                compacting=None
    return output

def revcomp(strseq):
    """
    cuts out sequence objects: input and output are strings.
    """
    seqob=Bio.Seq.Seq(str(strseq),Bio.Alphabet.IUPAC.extended_dna)
    return str(seqob.reverse_complement())

def extract_subsequence(sequence,start,end=None,strand=1,modifications=[]):
    """
    Modifications, e.g. [[1224,1223,'G','A'],[1336,1337,'T','C'],[1488,1489,'TC','TCC']]
    """
    #assert 0<=start<=len(sequence)
    #assert 0<=end<=len(sequence)
    originalstart=start
    originalend=end
    if type(sequence)==str:
        sequence=Bio.Seq.Seq(str(sequence),Bio.Alphabet.IUPAC.extended_dna)
    subseq=sequence.seq[start:end]

    if modifications: #check modifications are coherent
        #print "CHECKING MODIFICATIONS",modifications
        #RngS=set(range(start,end))
        #assert RngS
        checkedmodifications=[]
        nochangemodifications=[]
        for Ms,Me,orig,mod in modifications:
            OST=overlap_status(start,end,"subsequence",
                               Ms,Me,"modification",
                               report=False)
            
            if OST=="doesn't overlap":
                #print "NO OVERLAP",Ms,Me,orig,mod
                continue
            #print ("CHANGE {}-{} {}>{} ({})"
            #       .format(Ms,Me,orig,mod,OST))
            #if len(orig)>1:
            #    print "#.",Ms,Me,orig,mod,strand
            if OST=="overlaps":
                #check if modifications overlap end of sequence
                #and alter start and end accordingly
                if Ms<start:
                    #print ">",subseq
                    warning=("GIVEN FEATURE {}-{}({}), CHANGING "
                             "START {} TO {} BECAUSE OF "
                             "OVERLAPPING MODIFICATION {}-{}"
                             .format(start,end,strand,start,Ms,Ms,Me))
                    #self.problems["start change"]=warning
                    start=Ms
                if Me>end:
                    warning=("GIVEN FEATURE {}-{}({}), CHANGING "
                             "END {} TO {} BECAUSE OF "
                             "OVERLAPPING MODIFICATION {}-{}"
                             .format(start,end,strand,end,Me,Ms,Me))
                    #self.problems["start change"]=warning
                    end=Me

            if orig==mod:
                #print "NO CHANGE",Ms,Me,orig,mod
                nochangemodifications.append([Ms,Me,orig,mod])
                continue

            #if overlaps or contains...
            checkedmodifications.append((Ms,Me,orig,mod))

        #Adjust range if modifications extend beyond it
        if start!=originalstart or end!=originalend:
            subseq=sequence.seq[start:end]
            #ALSO DONT FORGET TO FLAG THAT IT HAS CHANGED, so return start,end

        #Just check no modifications
        for Ms,Me,orig,mod in nochangemodifications:
            Ls=Ms-start-1                    # CORE CONVERSION
            Le=Ls+len(orig)                  # MATHEMATICS

            #Check modification sequences to avoid errors
            if subseq[Ls:Le]!=orig:
                print ("PROBLEM WITH ({},{},{}) "
                       "(ORIGINAL START {} ORIGINAL END {})"
                       "MODIFICATION ({},{},{},{}) "
                       "READING {} at {} {}, NOT {}"
                       .format(start,end,strand,
                               originalstart,originalend,
                               Ms,Me,orig,mod,
                               subseq[Ls:Le],Ms,Me,orig))
                #sys.exit()
            #else:
            #    print ("CHECKING NOMOD (GLOBAL {}-{},{}) "
            #           " {}-{}={},{} "
            #           "(LOCAL {}-{}) "
            #           "FOUND {}"
            #           .format(start,end,strand,
            #                   Ms,Me,orig,mod,
            #                   Ls,Le,
            #                   subseq[Ls:Le]))
        #Now apply modifications
        localmodifications=[]
        for Ms,Me,orig,mod in checkedmodifications:
            
            #if strand==1:                        #
            Ls=Ms-start-1                         # CORE CONVERSION
            Le=Ls+len(orig)                       # MATHEMATICS

            #EXTRA CHECK
            if Ls<0:
                #Sometimes the modification coordinates are off
                #and need correcting
                #print "SHIFTING FEATURE START"
                start+=Ls
                end+=Ls
                Ms+=Ls
                Me+=Ls
                subseq=sequence.seq[start:end]
                Ls=0
                Le=Ls+len(orig)
                #print "newLs {} newMs {} newsubseq {}".format(Ls,Ms,subseq)
                
                #Correct 
            #elif strand==-1:                     #
            #    Ls=Me-end+1                      #
            #    Le=Ls+len(orig)                  #
            #    RCRefSeq=revcomp(orig)
            #Check modification sequences to avoid errors
            #print "LOCAL",Ls,Le
            localmodifications.append([Ls,Le,orig,mod])
            #if subseq[Ls:Le]==orig and len(orig)>1:
            #    print "looked for {} found {}".format(orig,subseq[Ls:Le])
            if subseq[Ls:Le]!=orig:
                print ">",Ls,Le,subseq
                print ("PROBLEM WITH ({},{},{}) "
                       "(ORIGINAL START {} ORIGINAL END {})"
                       "MODIFICATION ({},{},{},{}) "
                       "READING {} at {} {}, NOT {}"
                       .format(start,end,strand,
                               originalstart,originalend,
                               Ms,Me,orig,mod,
                               subseq[Ls:Le],Ms,Me,orig))
                print ">>",sequence.seq[start-1:end+1]
                #sys.exit()
            #else:
            #    print "NO PROBLEM!"
        if localmodifications:
            #print ">SEQUENCE_CHANGE",localmodifications
            subseq=sequence_change(subseq,localmodifications)
            #if strand==-1:
            #    print "STRAND -1",revcomp(subseq)
            #else:
            #    print "STRAND 1",subseq
    if strand==-1:
        return revcomp(subseq),start,end
    else:
        return str(subseq),start,end

#
class GFF_reader(object):
    geneswithintrons=0
    nintrons=0
    """
    N.B. SeqIO converts locations to be list-index based
    rather than the genetic style.
    E.g. a GFF file lists a location as 7235-9016
    When entered as a SeqFeature this becomes [7234:9016]
    
    geneticpositions     = 1234|56|789 i.e. 5-6
    listindexpositions   = 0123[45]678 i.e. 4:6
 
    allftypes=['snRNA_gene', 'telomeric_repeat',
    'Y_prime_element', 'transposable_element_gene',
    'origin_of_replication', 'mating_type_region',
    'LTR_retrotransposon', 'chromosome', 'centromere',
    'matrix_attachment_site', 'pseudogene', 'ncRNA_gene',
    'telomerase_RNA_gene', 'telomere', 'long_terminal_repeat',
    'X_element', 'rRNA_gene', 'ARS_consensus_sequence', 'ARS',
    'region', 'non_transcribed_region', 'tRNA_gene',
    'silent_mating_type_cassette_array', 'blocked_reading_frame',
    'snoRNA_gene', 'gene', 'X_element_combinatorial_repeat']

    """
    def __init__(self,filepath,
                 ftypes=["gene","intron","cds",
                         "chromosome","rRNA_gene",
                         "tRNA_gene","snoRNA_gene",
                         "snRNA_gene"],
                 checks=True,#False,
                 allelesbystrainfilename="",
                 alleledetailsfilename=""):
        self.ftypes=ftypes
        with open(filepath,"rb") as fileob:
            #GEX=GFF.GFFExaminer()
            #GAL=GEX.available_limits(fileob)
            #pprint(GAL)
            if ftypes:
                LI={"gff_type":self.ftypes}
            else:
                LI=None
            self.seqD=Bio.SeqIO.to_dict(GFF.parse(fileob))#,
            #                                  limit_info=LI))
            fileob.close()
        #self.list_by_order=[]
        self.index_by_type=defaultdict(list)
        self.index_by_location={}
        self.allfeatures=[]
        self.allregionwrappers=[]
        self.chrnames=[]
        """
        NB index_by_location uses genetic positions, not
        list indices like SeqIO converts them to.
        """
        self.index_by_name={}
        self.sequences={}
        self.problems={}
        self.RW=""
        for chrname,seq in self.seqD.items():
            self.chrnames.append(chrname)
            CN=convert_chrName_to_number(chrname)
            self.index_by_location[chrname]=defaultdict(list)
            self.sequences[chrname]=seq
            for i,feat in enumerate(seq.features):
                #xfeats=[feat]
                feat.chrname=chrname
                feat.CN=CN
                #unpack(feat)
                #sys.exit()
                if "gene" in feat.type:
                    if checks:
                        self._check_chromosome_is_right(CN,feat)
                    self._check_introns(feat)
                if feat.type!="chromosome":
                    self.allfeatures.append(feat)
                    self.index_by_name[feat.id]=feat
                    #self.list_by_order.append(feat)
                    self.index_by_type[feat.type].append(feat)
                    ST=int(feat.location._start)+1
                    EN=int(feat.location._end)
                    vals=range(ST,EN+1)
                    for l in vals:
                        self.index_by_location[chrname][l].append(feat)
                else:
                    self.index_by_type[feat.type].append(feat)
        if checks:
            self._check_chromosome_lengths_match_sequence()
            self._check_genes()
        #print self.index_by_type.keys()

    def __iter__(self):
        for feat in self.allfeatures:
            yield feat

    def Xget_subsequence(self,chromosome,start,end=None,strand=1):
        """
        start and end are GENETIC POSITIONS not list-index
        """
        if chromosome in getattr(self,"_CAD",{}):
            chromosome=self._CAD[chromosome]
        if chromosome not in self.sequences:
            return None
        if end is None: end=start
        seq=self.sequences[chromosome][start-1:end]
        if strand==1: return seq
        else: return seq.reverse_complement()

    def get_feature(self,lookup=None):
        if lookup is None:
            return sample(self.index_by_name.values(),1)[0]
        elif lookup in self.index_by_type:
            return sample(self.index_by_type[lookup],1)[0]
        else:
            return self.index_by_name.get(lookup,None)

    def get_features_in_range(self,
                              chrname,
                              geneticstart,
                              geneticend,
                              ftype=["gene","intergenic"]):
        overlapping_feats=set([])
        for loc in range(geneticstart,geneticend+1):
            feats=[f for f in self.index_by_location[chrname][loc]
                   if f.type in ftype]
            overlapping_feats.update(set(feats))
        return list(overlapping_feats)

    def _check_chromosome_lengths_match_sequence(self):
        if "chromosome" in self.ftypes:
            for chr_feat in self.index_by_type["chromosome"]:
                seq=self.sequences[chr_feat.id]
                fL,sL=len(chr_feat),len(seq)
                if fL!=sL:
                    k="chromosome length doesn't match"
                    v=("feat length = {} but seq length = {}"
                       .format(fL,sL))
                    self.problems[k]=v

    def _check_genes(self):
        for i,gene in enumerate(self.index_by_type["gene"]):
            STRT,END=gene.location._start,gene.location._end
            #NB END seems to be base after last base so..
            LEN=(END-STRT)
            STRAND=gene.location._strand
            #gene.sequence=gene.extract(chr)

            gl=self._check_gene_length(gene)
            #if not gl:
            #    return
            ss=self._check_start_stop(gene)
            #gene.prot=gene.sequence.seq.translate()
            #self._check_codons(gene)
            if gene.problems:
                if "geneproblems" not in self.problems:
                    self.problems["geneproblems"]={}
                self.problems["geneproblems"][gene.id]=gene.problems
                self._report(gene)

    def _check_chromosome_is_right(self,CN,feat):
        if feat.id[0]=="Q":
            if CN!=100:
                feat.problems["chromosome not right?"]="Gene name={} but chromosome #={}".format(feat.id,CN)
                return False
        else:
            if feat.type=="gene":
                featchrletter=feat.id[1]
                if ord(featchrletter)-64!=CN:
                    feat.problems["chromosome not right?"]="Gene name={} but chromosome #={}".format(feat.id,CN)
                    return False
        return True

    def _check_introns(self,gene):
        gene.codingsequence=[]
        gene.intronseqs=[]
        gene.introns=[]
        gene.exons=[]
        gene.problems={}
        gene.warnings={}
        CHRSEQ=self.sequences[gene.chrname]
        STRAND=gene.location._strand
        if getattr(gene,"sub_features",[]):
            #First, for convenience, repartition introns and exons
            #into FEAT.exons and FEAT.introns variable lists (and
            #self.subsections) rather than FEAT.sub_features[0].subfeatures
            mRNAs=gene.sub_features
            if not mRNAs:
                self.problems["gff problem"]=">NO mRNAs in gene feature"
                return False
            if len(mRNAs)!=1:
                self.problems["gff problem"]=">TOO MANY ({}) mRNAs".format(len(mRNAs))
                return False
            tempintronseqs=[]
            exoncounter=0
            introncounter=0
            for subfeat in mRNAs[0].sub_features:
                START=subfeat.location._start
                END=subfeat.location._end
                subfeat.id=""
                assert subfeat.location._strand==STRAND
                #print "GETTING SUBFEAT IN _check_introns",gene.id
                SUBSEQ,start,end=extract_subsequence(CHRSEQ,START,END,STRAND)
                if subfeat.type=="CDS":
                    exoncounter+=1
                    gene.codingsequence.append(SUBSEQ)
                    subfeat.id="{}_exon_{}".format(gene.id,exoncounter)
                    gene.exons.append(subfeat)
                elif "intron" in subfeat.type:
                    introncounter+=1
                    gene.intronseqs.append(SUBSEQ)
                    subfeat.id="{}_intron_{}".format(gene.id,introncounter)
                    #print subfeat.id,SUBSEQ
                    gene.introns.append(subfeat)
                    if gene.CN==100:
                        gene.warnings["mitochondrial intron"]=SUBSEQ
                        continue #ignore mitochondrial genes
                    if SUBSEQ[:2] not in intronstarts:
                        gene.problems["intron {} start problem".format(subfeat.id)]=SUBSEQ[:2]
                    if SUBSEQ[-2:] not in intronends:
                        gene.problems["intron {} end problem".format(subfeat.id)]=SUBSEQ[-2:]
                elif "plus_1_translational_frameshift" in subfeat.type:
                    gene.warnings["unusual"]="plus_1_translational_frameshift"
                else:
                    gene.problems["unresolved subfeat type"]=subfeat
                #print "^^^THAT WAS ",subfeat.id
            if introncounter>0:
                gene.warnings["introns"]=introncounter
            if STRAND==-1:
                gene.codingsequence.reverse()
                gene.intronseqs.reverse()
            gene.codingsequence="".join(gene.codingsequence)
            

    def _check_gene_length(self,gene):
        if not hasattr(gene,"codingsequence"):
            print "NO CODING SEQUENCE"
            print gene
            sys.exit()
        x,y=divmod(len(gene.codingsequence),3)
        if len(gene.codingsequence)%3!=0:
            cod=("{} codons + {}"
                 .format(x,gene.codingsequence[-y]))
            gene.problems["bad gene length"]=cod
            return False
        return True

    def _check_start_stop(self,gene):
        if gene.CN==100:
            gene.warnings["mitochondrial gene"]=True
        if gene.codingsequence[:3] not in startcodons:
            gene.problems["bad start codon"]=gene.codingsequence[:3]
        if gene.codingsequence[-3:] not in stopcodons:
            gene.problems["bad stop codon"]=gene.codingsequence[-3:]

    def _report(self,gene):
        print ">PROBLEM:",gene.id,gene.problems
        print

    def make_chraliasdict(self,chraliaspath):
        if chraliaspath:
            with open(chraliaspath,"rU") as fileob:
                reader=csv.reader(fileob,delimiter="\t")
                self._CAD={}
                self._CO=[]
                for row in reader:
                    self._CAD[row[1]]=row[0]
                    self._CO.append(row[0])
            fileob.close()
        else:
            self._CAD={k:k for k in seqD.keys()}
            self._CO=self._CAD.keys()[:]
            self._CO.sort()

    def make_strainaliasdict(self,strainaliaspath):
        if strainaliaspath:
            with open(strainaliaspath,"rU") as fileob:
                reader=csv.reader(fileob,delimiter="\t")
                self._SAD={row[2]:"AESW12fc"+row[4] for row in list(reader)[1:]}
                fileob.close()

    def _turn_indices_into_regions(self,indices):
        """
        e.g. [1,2,3,6,7,8,9] becomes [(1,3),(6,9)]
        Solution from https://stackoverflow.com/questions/10987777/python-converting-a-list-of-indices-to-slices
        """
        sind=sorted(indices)
        return [[next(v)]+list(v)[-1:]
                for k,v in
                groupby(sind,lambda x,c=count():x-next(c))]

    def make_intergenic_features(self,
                                 types=['rRNA_gene',
                                        'snRNA_gene',
                                        'tRNA_gene',
                                        'snoRNA_gene',
                                        'gene']):
        """
        Again, must be careful with different indexing systems
        genes 1234 56 789
        inds  0123 45 678
        slices = [0:4],[4:6],[6:9]
        NB
        This function also attaches introns to the genes containing them
        """
        for chrname,seq in self.sequences.items():
            CN=convert_chrName_to_number(chrname)
            allbases=set(range(1,len(seq)+1)) #genetic positions
            flankinglookup=defaultdict(list)
            for feat in seq.features:
                if feat.type in types:
                    ST=int(feat.location._start)+1
                    EN=int(feat.location._end)
                    flankinglookup[ST].append(feat.id)
                    flankinglookup[EN].append(feat.id)
                    featbases=range(ST,EN+1)
                    allbases-=set(featbases)
            for region in self._turn_indices_into_regions(allbases):
                if len(region)==2:
                    a,b=region
                elif len(region)==1:
                    a=b=region[0]
                else:
                    print ">>",region
                    continue
                leftgeneid=flankinglookup.get(a-1,[""])[0] #
                rightgeneid=flankinglookup.get(b+1,[""])[0] #
                rnm="{}><{}".format(leftgeneid,rightgeneid)
                if rnm.startswith(">"): rnm=rnm[1:]
                elif rnm.endswith("<"): rnm=rnm[:-1]
                sf=Bio.SeqFeature.SeqFeature(Bio.SeqFeature.FeatureLocation(a-1,b,strand=1),
                                             type="intergenic",
                                             id=rnm)
                sf.chrname=seq.id
                sf.CN=CN
                #sf.sequence=sf.extract(seq)
                seq.features.append(sf)
                self.allfeatures.append(sf)
                #print sf
                for bs in range(a,b+1):
                    self.index_by_location[chrname][bs].append(sf)
                self.index_by_type["intergenic"].append(sf)
                self.index_by_name[rnm]=sf
        self.allfeatures.sort(key=lambda f: (f.CN,f.location._start))


    def add_vcfs(self,
                 vcfpath,
                 ftype=['rRNA_gene',
                        'snRNA_gene',
                        'tRNA_gene',
                        'snoRNA_gene',
                        "gene",
                        "intergenic"]):
        self.vcfpath=vcfpath
        with open(vcfpath,'rb') as vcfFO:
            vcf_reader=vcf.Reader(vcfFO)
            
            #self.vcfeats=[]
            openfeatures=[]
            self.allelelookup={}
            self.alleledetails={}
            for i,VR in enumerate(vcf_reader):
                #vcfpath chromosome labels take form of e.g. ref|NC_001133|
                #so must be converted, using data from chraliaspath, to
                #e.g. chrI to match sequence names used in gff file
                VR.chrname=getattr(self,"_CAD",
                                   {VR.CHROM:
                                    VR.CHROM}).get(VR.CHROM,
                                                   VR.CHROM)
                chrsequence=self.sequences[VR.chrname]

                #NB---------------------------------------------------
                #pyvcf also uses the zero-based, half-open coordinate system
                #like list indices rather than genetic coordinates.
                #https://pyvcf.readthedocs.io/en/latest/API.html#vcf-reader
                #^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                
                geneticstart,geneticend=VR.POS,VR.POS+len(VR.REF)-1
                slicestart,sliceend=geneticstart-1,geneticend

                #THIS ACTED AS A CHECK THAT SEQUENCES MATCHED:
                #subseq=self.get_subsequence(VR.chrname,
                #                            geneticstart,
                #                            geneticend)
                #if str(subseq.seq)!=str(VR.REF):
                #    print "MISMATCH"

                #Returns all features overlapping current variant
                OFT=self.get_features_in_range(VR.chrname,
                                               geneticstart,
                                               geneticend,
                                               ftype=ftype)

                #THESE ARE ERROR-CHECKING REPORT LINES
                #if i%1000==0:
                #    print i,VR.chrname,VR.POS,VR.REF,[f.id for f in OFT]
                #print "#",[f.id for f in OFT]

                #Then adds the variant to each of those features
                for feat in OFT:
                    if not hasattr(feat,"vcs"):
                        feat.vcs=[]
                    feat.vcs.append(VR)
                    if feat not in openfeatures:
                        openfeatures.append(feat)
                        #print "Adding {}({}) to OF".format(feat.id,len(feat.vcs))
                    #if feat not in self.vcfeats:
                    #    self.vcfeats.append(feat)

                #Now process any features that end before this
                for FOF in openfeatures:
                    if VR.chrname!=FOF.chrname or int(FOF.location._end)<sliceend:
                        chrsequence=self.sequences[FOF.chrname]
                        #featsequence=FOF.extract(chrsequence)._seq
                        #print "PROCESSING OPENFEATURES"
                        #featsequence,newst,newend=extract_subsequence(chrsequence,
                        #                                              FOF.location._start,
                        #                                              FOF.location._end,
                        #                                              FOF.location._strand)
                        #if i%1000==0:
                        #    print ">Now at {} {}".format(VR.chrname,slicestart)
                        #FOF.sequence=featsequence
                        writtenheader=False
                        if RegionWrapper.strainorder:
                            writtenheader=True
                        # ############################################
                        # CREATE A REGIONWRAPPER OBJECT TO HANDLE
                        # PROTEIN CALCULATIONS
                        RW=self.get_region_wrapper(FOF,
                                                   #featsequence,
                                                   chrsequence)
                        # ############################################
                        protvariants=getattr(RW,"proteindetails",None)
                        #if protvariants:
                        #    print ".",RegionWrapper.globcounter,FOF.id,protvariants
                        if not writtenheader:
                            self.headerrow=RW.get_headerrow()
                        self.allelelookup[FOF.id]=RW.get_dna_strainrow()
                        self.alleledetails[FOF.id]=RW.get_alleledetails()
                        global SRW
                        if i%1000==0:
                            SRW=RW
                            #print "BREAK!"
                            #sys.exit()
                        #    print RW
                        #    print "deleting {}({}) from OF".format(FOF.id,len(FOF.vcs))
                        #
                        openfeatures.remove(FOF)
                        del FOF
                        #gc.collect() SUPER SLOW!
                #if i>10:
                #    print "REACHED i THRESHOLD",i
                #    break

            vcfFO.close()
        #delattr(self,"list_by_order")
        #delattr(self,"index_by_type")
        #delattr(self,"index_by_location")

    def get_region_wrapper(self,feat,chrsequence):#featsequence,
        #print ("\nProcessing feature {} "
        #       "on {}({}) with {} vcfs"
        #       .format(feat.id,
        #               feat.chrname,
        #               str(feat.location),
        #               len(feat.vcs)))
        if not hasattr(feat,"vcs"):
            feat.vcs=[]
            #return None
        #PREPARE CLASS VARIABLES IF NOT YET SET
        if not getattr(RegionWrapper,"strainaliasdict",[]):
            SAD=RegionWrapper.strainaliasdict=self._SAD
        else:
            SAD=self._SAD
        if not getattr(RegionWrapper,"strainorder",[]):
            RegionWrapper.strainorder=[SAD[call.sample]
                                       for call
                                       in feat.vcs[0].samples]
        
        RW=RegionWrapper(feature_with_vcs=feat,
                         #featsequence=featsequence,
                         chrsequence=chrsequence)
        self.allregionwrappers.append(RW)
        return RW

    def save_allele_details(self,filepath):
        vcfFN=os.path.basename(self.vcfpath)
        vcfFNB=os.path.splitext(vcfFN)[0]
        outputfilepath=filepath
        header="Alleles derived from {}\n\n".format(vcfFN)
        with open(outputfilepath,"w") as filewriter:
            filewriter.write(header)
            for feat in self.allregionwrappers:
                filewriter.write(str(feat)+"\n")
        print "Saved allele_lookup to",outputfilepath
        return True

    def save_dna_allele_strains(self,filepath):
        print 
        strainheaders=["region","length","N_alleles"]+list(self.allregionwrappers[0]._iter_strains())
        #WIP
        with open(filepath,'wb') as gtstrainFO:
            gtstrain_writer=csv.writer(gtstrainFO,
                                       delimiter='\t',
                                       quotechar='|',
                                       quoting=csv.QUOTE_MINIMAL)
            gtstrain_writer.writerow(strainheaders)
            for rw in self.allregionwrappers:
                row=rw.get_dna_strainrow()
                gtstrain_writer.writerow(row)
        print "Saved dna_allele_strains to",filepath
        return True

    def save_protein_allele_strains(self,filepath):
        strainheaders=["region","length","N_alleles"]+list(self.allregionwrappers[0]._iter_strains())
        with open(filepath,'wb') as gtstrainFO:
            gtstrain_writer=csv.writer(gtstrainFO,
                                       delimiter='\t',
                                       quotechar='|',
                                       quoting=csv.QUOTE_MINIMAL)
            gtstrain_writer.writerow(strainheaders)
            for rw in self.allregionwrappers:
                row=rw.get_protein_strainrow()
                gtstrain_writer.writerow(row)
        print "Saved protein_allele_strains to",filepath
        return True


    def get_sample_data(self):
        output=[]
        bothstrands=[1,-1]*1000
        for gene in self.index_by_type["gene"]:
            strnd=int(gene.location._strand)
            if hasattr(gene,"vcs"):
                if strnd in bothstrands:
                    bothstrands.remove(strnd)
                    #print gene.id,
                    gene1vcs=gene.vcs
                    #print len(gene1vcs),
                    genechr=self.sequences[gene.chrname]
                    #print genechr.id
                    output.append((gene,genechr))
            if not bothstrands:
                break
        return output

#
class RegionWrapper(object):
    strainaliasdict=PassThroughDict()
    strainorder=[]
    repcount=0
    globcounter=0

    @classmethod
    def get_headerrow(cls):
        return ["gap","gap_length","total_alleles"]+cls.strainorder

    def __init__(self,
                 feature_with_vcs,
                 chrsequence=None):
        """
        Order of operations:
        1) extract_variants from self.FEAT.vcs
        2) 
        """

        self.__class__.globcounter+=1
        self.FEAT=feature_with_vcs

        self.id=self.FEAT.id
        self.CN=self.FEAT.CN
        self.description=self.FEAT.qualifiers.get("Note",["(No Note)"])[0]
        self.problems={}

        self.variantdetails_number={"ref":[]}  #k=number, v=[index,ref,genotype]
        self.variantdetails_reverse={} #k=[index,ref,genotype], v=number
        self.variantcalls=defaultdict(list) #k=sample, v=number
        self.variant_proteinletters=defaultdict(list) #k=proteinletter, v=[variantnumbers]
        self.defaultprotein=None
        self.proteindetails={"REF":[]} #k=proteinletter, v=[(protindex,original,changed),..]
        self.proteindetails_reverse={"[]":"REF"} #k==[(protindex,original,changed),..],v=proteinletter

        self.feat_start=self.FEAT.location._start
        self.feat_end=self.FEAT.location._end
        self.strand=self.FEAT.location._strand
        self.chrsequence=chrsequence

        self.coorddict={}
        #self.subsections=[]

        SR=self.define_subregions()
        #for sr in SR:
        #    print sr.id,sr.TYPE
        self.region_check()

        self.group_vcs_into_alleles()

        self.get_protein_alleles()

        if not hasattr(self.FEAT,"problems"):
            self.FEAT.problems={}
        self.FEAT.problems.update(self.problems)

    def extract_variant_coords(self,vcfvariantobject):
        """
        Used to extract key info from vcfvariantobject
        """
        V=vcfvariantobject
        original_string=V.REF
        variant_start=V.POS
        alts=V.ALT
        alleles=list(original_string)+alts
        gVst=int(variant_start)
        gVnd=gVst+len(original_string)
        return (gVst,gVnd,str(original_string))

    def define_subregions(self):
        self.subregions=[]
        self.atypical=False
        if getattr(self.FEAT,"sub_features",[]):
            subfeats=self.FEAT.sub_features
            if not subfeats:
                self.problems["no subfeats"]=True
                return
            if len(subfeats)!=1:
                self.problems["too many subfeats"]=True
            for sf1 in subfeats:
                if not getattr(sf1,"sub_features",[]):
                    sf1.TYPE="special"
                    self.subregions.append(sf1)
                #if sf1.type in ["noncoding_exon","five_prime_UTR_intron"]:
                #    self.atypical=True
                else:
                    for subfeat in sf1.sub_features:
                        if subfeat.type=="CDS":
                            subfeat.TYPE="coding"
                            self.subregions.append(subfeat)
                        elif "intron" in subfeat.type:
                            subfeat.TYPE="intron"
                            self.subregions.append(subfeat)
                        else:
                            self.problems["unusual subfeature"]=subfeat.qualifiers["Name"]
                            self.atypical=True
                            #sys.exit()
                            subfeat.TYPE="special"
                            self.subregions.append(subfeat)
        else:
            if self.FEAT.type=="intergenic":
                self.FEAT.TYPE="noncoding"
                self.subregions.append(self.FEAT)
            else:
                self.problems["unexpected feature"]=self.FEAT
        #Sort by order on strand
        self.subregions.sort(key=lambda sf:sf.location._start)
        if self.strand==-1: self.subregions.reverse()
        #Add IDs
        for n,sub in enumerate(self.subregions):
            if sub.TYPE=="coding":
                label="exon"
            elif sub.TYPE=="intron":
                label="intron"
                sub.id=None
            else:
                label=sub.TYPE
            newid="{}_{}_{}".format(self.FEAT.id,
                                    label,
                                    n)
            if not getattr(sub,"id",""):
                sub.id=newid
            #else:
            #    print ">",sub.id
        #if self.atypical:
        #    print "{} ({}-{}) ATYPICAL".format(self.id,
        #                                       self.feat_start,
        #                                       self.feat_end)
        #    print self.FEAT
        #    for sr in self.subregions:
        #        print "{} {} {} ({}-{})".format(sr.id,
        #                                        sr.type,
        #                                        sr.TYPE,
        #                                        sr.location._start,
        #                                        sr.location._end)
            #sys.exit()
        return self.subregions

    def region_check(self):
        """
        Checks that feature is completely covered by subregions.
        Exceptions made for features containing noncoding exons and
        5' UTR introns
        """
        featrange=set(range(self.feat_start,self.feat_end))
        for sub in self.subregions:
            #print ">",self.id,sub.id,sub.type,type(sub.type),str(sub.type)
            if str(sub.type) in ["noncoding_exon","five_prime_UTR_intron"]:
                return True
            #if sub.type=
            subrange=set(range(sub.location._start,
                               sub.location._end))
            featrange-=subrange
        if featrange:
            print "{} ({}-{}) FAILED REGION CHECK".format(self.id,
                                                         self.feat_start,
                                                         self.feat_end)
            for sr in self.subregions:
                print "{} ({}-{})".format(sr.id,
                                          sr.location._start,
                                          sr.location._end)
            print "UNREGIONED COORDINATES: {}".format(tuple(featrange))
            print self.FEAT
            return False
        return True

    def group_vcs_into_alleles(self):
        """
        Dont worry, yet, about effects of each variant on protein sequence,
        but group them into alleles anyway

         [global start, global end, original_string, variant], e.g.
         [[2,3,'G','A'],[6,7,'T','C'],[8,9,'TC','TCC']]
        """
        if not hasattr(self.FEAT,"vcs"):
            self.problems["no variant calls"]=True
            print "{} has no vcs records".format(self.id)
            return False

        self.variantcalls=defaultdict(list)

        for V in self.FEAT.vcs:
            gVst,gVnd,OS=self.extract_variant_coords(V)
            alts=V.ALT
            alleles=list(OS)+alts

            self.__class__.SAMPLEORDER=[]
            for call in V.samples:
                if getattr(self,"strainaliasdict",[]):
                    key=self.strainaliasdict[call.sample]
                else:
                    key=call.sample
                self.__class__.SAMPLEORDER.append((call,key))
                if call["GT"]==".":
                    #These are monomorphic alleles and can be ignored
                    variant="."
                    continue
                else:
                    variant=alleles[int(call["GT"])]
                if OS!=variant:
                    self.variantcalls[key].append([gVst,gVnd,OS,variant])
                if not self.variantcalls[key]:
                    self.variantcalls[key]=[]

        VDK=1

        #Now save space by converting each unique [gVst,gVnd,original_string,variant]
        #into an index number, and store lookups and reverse lookups for this
        self.variantdetails_number["ref"]=[]
        for strain,gtlist in self.variantcalls.items():
            #print ">!",strain,gtlist
            if not gtlist:
                self.variantcalls[strain]="ref"
                continue
            gtlist.sort()
            if str(gtlist) not in self.variantdetails_reverse:
                self.variantdetails_number[VDK]=gtlist
                self.variantdetails_reverse[str(gtlist)]=VDK
                VDK+=1
            self.variantcalls[strain]=self.variantdetails_reverse.get(str(gtlist),"ref")
        #if self.feat_start>50000:
        #    sys.exit()
        return True
        #allelic variants
        #self.analyze_variants()

    def get_protein_alleles(self):
        self.variant_proteinletters_reverse={}
        if self.FEAT.type=="gene":
            self.defaultprotein=self.translate_allele([],self.FEAT.id,"REF")
            #self.proteindetails["REF"]=[]
            newproteinn=1
            for n,vd in sorted(self.variantdetails_number.items()):
                #print ("translating_allele {} in {} ({})"
                #   .format(n,
                #           self.FEAT.id,
                #           vd))
                pd=self.translate_allele(vd,self.FEAT.id,n)
                proteinchanges=note_changes(self.defaultprotein,pd)
                #print proteinchanges
                if str(proteinchanges) not in self.proteindetails_reverse:
                    L=letcode(newproteinn)
                    #print "new protein allele {} for {}".format(L,proteinchanges)
                    newproteinn+=1
                    self.proteindetails_reverse[str(proteinchanges)]=L
                    self.proteindetails[L]=proteinchanges
                else:
                    L=self.proteindetails_reverse[str(proteinchanges)]
                    #print "{} matches existing protein allele {}".format(proteinchanges,L)
                self.variant_proteinletters[L].append(n)
                self.variant_proteinletters_reverse[n]=L


    def translate_allele(self,variantdetails,geneid,variantletter):
        dna,newstt,newend=self.get_coding_allele(variantdetails,geneid,variantletter)
        try:
            dnaob=Bio.Seq.Seq(dna,Bio.Alphabet.IUPAC.extended_dna)
            return str(dnaob.translate())
        except:
            self.problems["COULDN'T TRANSLATE"]=True
            return None

    def get_coding_allele(self,variantdetails,geneid,variantletter):
        """
        variantdetails=[[gVst,gVnd,VS,genotype],[...]]
        as stored in...
        self.variantdetails_number[N]=variantdetails
        self.variantdetails_reverse[str(variantdetails)]=N
        """
        #print self.id
        codingsequence=""
        #print "_"*20
        #print "TRANSLATING ALLELE {} {} OF {}".format(variantletter,variantdetails,self.id)
        for sr in self.subregions:
            stt=sr.location._start
            end=sr.location._end
            ori=sr.location._strand
            id=sr.id
            #print id,sr.TYPE
            #seq=sr.extract(self.chrsequence).seq
            if sr.TYPE=="coding":
                #print "translate_allele GETTING CODING"
                seq,newstt,newend=extract_subsequence(self.chrsequence,stt,end,ori,variantdetails)
                #print ">>",newstt,newend,ori,variantdetails
                #print ">",seq
                
                if newstt!=stt or newend!=end:
                    self.problems["changed feature start and end "
                                  "due to overlapping modifications"]=(newstt,
                                                                       newend)
                    #sys.exit()
                codingsequence+=seq
            elif sr.TYPE=="noncoding":
                #print "noncoding",sr.id
                pass
        #check coding sequence
        if codingsequence[:3] not in startcodons:
            warning=("bad start codon in allele {} ({})"
                     .format(variantletter,
                             variantdetails))
            self.problems[warning]=codingsequence[:3]
            #print ">",codingsequence
        if codingsequence[-3:] not in stopcodons:
            warning=("bad stop codon in allele {} ({})"
                     .format(variantletter,
                             variantdetails))
            self.problems[warning]=codingsequence[-3:]
            #print ">",codingsequence
        #
        if len(codingsequence)%3!=0:
            self.problems["bad coding sequence length in allele {}"
                          .format(variantletter)]=len(codingsequence)
        #
        return codingsequence,newstt,newend
        #print "FULL CODING SEQUENCE",codingsequence




    def __repr__(self):
        self.feat_startNZI=self.feat_start+1
        return "{id}({feat_startNZI}-{feat_end})".format(**self.__dict__)

    def reverse_variantcalls(self):
        if not hasattr(self,"variantcalls_reverse"):
            self.variantcalls_reverse=defaultdict(list)
            for samplename,code in self.variantcalls.items():
                self.variantcalls_reverse[code].append(samplename)
        return self.variantcalls_reverse

    def reverse_variantcounts(self):
        if not hasattr(self,"variantcounts_reverse"):
            self.variantcounts_reverse={code:len(lst)
                                        for code,lst
                                        in self.reverse_variantcalls().items()}
        return self.variantcounts_reverse

    def count_strains_for_dna_allele(self,allelecode):
        return self.reverse_variantcounts().get(allelecode,0)

    def count_strains_for_protein_allele(self,allelecode):
        return sum([self.count_strains_for_dna_allele(ac)
                    for ac in self.variant_proteinletters.get(allelecode,[])])

    def __str__(self):
        self.feat_startNZI=self.feat_start+1
        output=["{id}({CN};{feat_startNZI}-{feat_end};{strand})".format(**self.__dict__)]
        output.append(str(self.description))
        output.append("DNA ALLELES:")
        output.append("ref ({} strains)"
                      .format(self.count_strains_for_dna_allele("ref")))
        for l,ldet in self.variantdetails_number.items():
            if l=="ref": continue
            #CONVERT FIRST INDICES BACK TO BIOLOGICAL INDEXING
            ldetREINDXD=[]
            for tup in ldet:
                srt,end,ref,var=tup
                ldetREINDXD.append([srt+1,end,ref,var])
            ndstrains=self.count_strains_for_dna_allele(l)
            output.append("{} ({} strains)\t{}".format(l,ndstrains,ldetREINDXD))
        if self.FEAT.type=="gene":
            output.append("PROTEIN ALLELES:")
            refdnaalleles=self.variant_proteinletters.get("REF",[])
            
            
            refdnaalleles=[str(i) for i in refdnaalleles]
            output.append("REF ({} strains; =dna alleles {})"
                          .format(self.count_strains_for_protein_allele("REF"),
                                  ','.join(refdnaalleles)))
            for p,pdet in sorted(self.proteindetails.items()):
                #CONVERT FIRST INDICES BACK TO BIOLOGICAL INDEXING
                pdetREINDXD=[]
                for tup in pdet:
                    srt,ref,var=tup
                    pdetREINDXD.append([srt+1,ref,var])

                dnaalleles=self.variant_proteinletters.get(p,[])
                dnaalleles=[str(i) for i in dnaalleles]
                if p=="REF": continue
                npstrains=self.count_strains_for_protein_allele(p)
                output.append("{} ({} strains; =dna alleles {})\t{}".format(p,
                                                                            npstrains,
                                                                            ",".join(dnaalleles),
                                                                            pdetREINDXD))
                #print "\n".join(output+[""])
        for probheader,probdetails in self.FEAT.problems.items():
            output.append("\t!{}\t{}".format(probheader,probdetails))
        #output.append(str(self.get_strainrow()))
        return "\n".join(output+[""])

    def _iter_strains(self):
        if self.__class__.strainorder:
            for strainname in self.__class__.strainorder:
                yield strainname
        else:
            for strainname in sorted(self.variantcodes.keys()):
                yield strainname

    def __iter__(self):
        for strainname in self._iter_strains():
            yield self.variantcalls[strainname]

    def get_dna_strainrow(self):
        lst=list(self)
        lst=[x if x!=[] else None for x in lst]
        #lst=["=" if x=="ref" else x for x in lst]
        try:
            return [self.id,len(self.FEAT),len(set(lst))]+lst
        except:
            print self.id,self.FEAT,lst
            sys.exit()

    def get_protein_strainrow(self):
        lst=[self.variant_proteinletters_reverse.get(n,None) for n in self]
        #lst=["=" if x=="REF" else x for x in lst]
        try:
            return [self.id,len(self.FEAT),len(set(lst))]+lst
        except:
            print self.id,self.FEAT,lst
            sys.exit()

    def get_alleledetails(self):
        return self.variantdetails_number

    def __getitem__(self,querystrain):
        return self.variantdetails_number[self.variantcodes[querystrain]]

#####
    ####
#####
def choose_file_to_rename():
    RL=RenameLog()
    LST=[(a,b,time.asctime(time.localtime(c)))
         for a,b,c in RenamedFiles().return_platereader_output_list()]
    
    root=tk.Tk()
    LB1=MultiColumnListbox(root,
                           title="AFVCF",
                           instruct=("Select file to rename.\n\n"
                                     "Hit <Delete> to remove any file(s) already created."),
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

def check_already_renamed(MAINDICT):
    originalfilename=MAINDICT["originalfilename"]
    RFNR=ReadingFileNameReader(originalfilename)
    if RFNR.get_is_OK():
        filepath=os.path.join(platereader_output,originalfilename)
        MAINDICT["targetfilename"]=originalfilename
        MAINDICT["userinitials"]=RFNR.properties.get("user",None)
        MAINDICT["experimentnumber"]=RFNR.properties["experimentnumber"]
        MAINDICT["fileletter"]=RFNR.properties["fileletter"]
        MAINDICT["treatment"]=RFNR.properties["treatment"]
        layout=MAINDICT["layout"]=RFNR.properties["layout"]
        MAINDICT["timeoffset"]=RFNR.properties.get("timeoffset",0)
        MAINDICT["note"]=RFNR.properties.get("note","")
        MAINDICT["extension"]=RFNR.properties.get("extension",None)
        MAINDICT["orientation"]=RFNR.properties.get("reorient",None)
        MAINDICT["exclusions"]=RFNR.properties.get("flags",None)
        MAINDICT["survivorstart"]=RFNR.properties.get("survivorstart",None)
        MAINDICT["fileobject"]=File(filepath=filepath,
                                    platelayout=layout)
        MAINDICT["renamedfilename"]=originalfilename
        return MAINDICT
    return False

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
                            title="AFVCF",
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
            EB2=EntryBox(root,title="AFVCF",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            USERINITIALS=EB2.value.strip()
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
            else:
                chars=set(USERINITIALS.lower())
                ok=set("abcdefghijklmnopqrstuvwxyz")
                notok=chars-ok
                if notok:
                    notokstring=", ".join(list(notok))
                    instruction=("The following characters are not valid letters: "
                                 "{} Choose again.".format(notokstring))
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
            EB3=EntryBox(root,title="AFVCF",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            EXPNUMBER=EB3.value.strip()
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
            EB3=EntryBox(root,title="AFVCF",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            FILELETTER=EB3.value.strip()
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
                           headers=["Treatment","Number of files (including in All) with treatment"],
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
            EB4=EntryBox(root,title="AFVCF",instruct=instruction)
            root.focus_force()
            root.geometry(windowposition)
            root.mainloop()
            TREATMENT=EB4.value.strip()
            if len(TREATMENT)>40:
                instruction="{} is too long. Choose again (<=40 characters).".format(TREATMENT)
                LOG.error(instruction)
                TREATMENT=None

    if TREATMENT=="YPD (control)":
        TREATMENT="YPD"
    if TREATMENT:
        MAINDICT["treatment"]=TREATMENT
        return MAINDICT




#
def categorize_alleles(ALOCS):
    ALOCS=choose_gff_file(ALOCS)
    if not ALOCS: return
    ALOCS=choose_vcf_file(ALOCS)
    if not ALOCS: return
    vcfFNB=os.path.splitext(os.path.basename(ALOCS["vcf_filepath"]))[0]
    
    rootdir=ALOCS["outputdir"]
    if not rootdir:
        rootdir=scriptdir()
    
    GR=ALOCS["gffreader"]
    outputFP=os.path.join(rootdir,"AFVCF allele details {}.txt".format(vcfFNB))
    GR.save_allele_details(filepath=outputFP)
    outputFP=os.path.join(rootdir,"AFVCF dna allele per strain {}.tab".format(vcfFNB))
    GR.save_dna_allele_strains(filepath=outputFP)
    outputFP=os.path.join(rootdir,"AFVCF protein allele per strain {}.tab".format(vcfFNB))
    GR.save_protein_allele_strains(filepath=outputFP)
    open_on_Windows(rootdir)
    return ALOCS

def choose_gff_file(ALOCS):
    tit="Locate reference genome .gff file"
    while not ALOCS.get("gffreader",None):
        FILEPATH=ALOCS["gff_filepath"]
        FILEDIR=ALOCS["gff_filedir"]
        if not FILEDIR:
            FILEDIR=ALOCS["scriptdir"]
        root=tk.Tk()
        root.geometry(windowposition)
        root.withdraw()
        filepath=tkFileDialog.askopenfilename(title=tit,
                                              filetypes=[("GFF","*.gff")],
                                              initialdir=FILEDIR,
                                              initialfile=FILEPATH)
        root.destroy()
        if not filepath:
            return
        elif not os.path.exists(filepath):
            continue
        else:
            #open file and check it looks right
            try:
                GR=GFF_reader(filepath)
                GR.make_intergenic_features()
                ALOCS["gff_filepath"]=filepath
                ALOCS["gffreader"]=GR
                ALOCS["chrnames"]=GR.chrnames
                return ALOCS
            except:
                tit="Invalid .gff file. Choose again"
                continue

def check_vcf_file(vcffilepath):
    strainnames=[]
    with open(vcffilepath,'rb') as vcfFO:
        vcf_reader=vcf.Reader(vcfFO)
        for VR in vcf_reader:
            chrname=VR.CHROM
            for call in VR.samples:
                strainnames.append(call.sample)
            break
    return chrname,sorted(strainnames)


def choose_vcf_file(ALOCS):
    tit="Locate .vcf file"
    while not ALOCS.get("vcffilepath",None):
        FILEDIR=ALOCS["vcf_filedir"]
        if not FILEDIR:
            FILEDIR=["gff_filedir"]
        FILEPATH=ALOCS["vcf_filepath"]
        root=tk.Tk()
        root.geometry(windowposition)
        root.withdraw()
        filepath=tkFileDialog.askopenfilename(title=tit,
                                              filetypes=[("VCF","*.vcf")],
                                              initialdir=FILEDIR,
                                              initialfile=FILEPATH)
        root.destroy()
        if not filepath:
            return
        elif not os.path.exists(filepath):
            continue
        else:
            #open file and check it looks right
            #WIP
            try:
                chrname,strainnames=check_vcf_file(filepath)
            except:
                tit="Invalid .vcf file. Choose again"
                continue
            ALOCS["vcf_filepath"]=filepath
            ALOCS["vcf_filedir"]=os.path.dirname(filepath)
            ALOCS["strainnames"]=strainnames
            if chrname not in ALOCS["chrnames"]:
                ALOCS=choose_chralias_file(ALOCS)
            ALOCS=choose_strainalias_file(ALOCS)
            if not ALOCS: return
            ALOCS["gffreader"].add_vcfs(filepath)
            return ALOCS

def choose_chralias_file(ALOCS):
    tit="Locate chromosome alias file"
    while True:
        FILEDIR=ALOCS["chralias_filedir"]
        if not FILEDIR:
            FILEDIR=ALOCS["vcf_filedir"]
        FILEPATH=ALOCS["chralias_filepath"]
        
        root=tk.Tk()
        root.geometry(windowposition)
        root.withdraw()
        filepath=tkFileDialog.askopenfilename(initialdir=FILEDIR,
                                              title=tit,
                                              filetypes=[("TAB DELIMITED","*.tab")],
                                              initialfile=FILEPATH)
        root.destroy()
        if not filepath:
            return
        try:
            GR=ALOCS["gffreader"]
            GR.make_chraliasdict(filepath)
            ALOCS["chralias_filepath"]=filepath
            ALOCS["chralias_filedir"]=os.path.dirname(filepath)
            return ALOCS
        except:
            tit="Not a valid chromosome alias file. "+tit
            continue

def choose_strainalias_file(ALOCS):
    tit="Locate strain alias file"
    while True:
        FILEDIR=ALOCS["stralias_filedir"]
        if not FILEDIR:
            FILEDIR=ALOCS["chralias_filedir"]
        FILEPATH=ALOCS["stralias_filepath"]
        root=tk.Tk()
        root.geometry(windowposition)
        root.withdraw()
        filepath=tkFileDialog.askopenfilename(initialdir=FILEDIR,
                                              title=tit,
                                              filetypes=[("TAB DELIMITED","*.tab")],
                                              initialfile=FILEPATH)
        root.destroy()
        if not filepath:
            return
        print filepath
        try:
            GR=ALOCS["gffreader"]
            GR.make_strainaliasdict(filepath)
            ALOCS["stralias_filepath"]=filepath
            ALOCS["stralias_filedir"]=os.path.dirname(filepath)
            return ALOCS
        except:
            tit="Not a valid strain alias file. "+tit
            continue

#
def visualize_alleles(ALOCS):
    if not ALOCS: return
    ALOCS=choose_userfolder(ALOCS)
    if not ALOCS: return
    ALOCS=choose_combifiles(ALOCS)
    if not ALOCS: return
    ALOCS=choose_allele_files(ALOCS)
    if not ALOCS: return
    ALOCS=choose_regions(ALOCS)
    if not ALOCS: return
    CFs=ALOCS["combifileobjects"]
    RNs=ALOCS["selectedregions"]
    DCD={}
    PNs=ALOCS["plotnames"]=[]
    DASSD=ALOCS["dnaallelestrainsshareddata"]
    DCDFR=ALOCS["dnaallelestrainsrowdictionary"]

    outputdir=ALOCS["outputdir"]
    if not outputdir:
        outputdir=ALOCS["locations"]["genotypes"]
        ALOCS["outputdir"]=outputdir

    CPD=CurvesWithoutAgar_Alleles2(CFs,
                                   RNs,
                                   DCDFR,
                                   savedir=outputdir)
    ALOCS["savepaths"]=CPD.savepaths

    PCDFR=ALOCS["proteinallelestrainsrowdictionary"]
    CPP=CurvesWithoutAgar_Alleles2(CFs,
                                   RNs,
                                   PCDFR,
                                   dnaorprotein="protein",
                                   savedir=outputdir)
    ALOCS["savepaths"]+=CPP.savepaths
    open_on_Windows(os.path.dirname(CPP.savepaths[0]))
    return ALOCS

def choose_userfolder(ALOCS,
                      IGNORE=["All","Controls"]):
    LST,LSTED=[],[]
    LOCS=ALOCS["locations"]
    for p in LOCS.yield_userpaths():
        fp=os.path.basename(p)
        fpc=count_files_in(p)
        if fp not in IGNORE:
            LST.append((fp,fpc))
            LSTED.append(fp)
    LST.sort()
    DEF=LOCS.currentuserfolder
    if DEF in IGNORE or DEF not in LSTED:
        DEF=NF[0]

    root=tk.Tk()
    LB2=MultiColumnListbox(root,
                           title="AFVCF",
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

    if USERFOLDER:
        LOCS.change(USERFOLDER,create=True)
        LOG.info("active folder set to {}".format(USERFOLDER))
        ALOCS["userfolder"]=USERFOLDER
        return ALOCS

def choose_combifiles(ALOCS):
    CF=CombiFiles(ALOCS["userfolder"])
    LST=[cf for cf in CF]
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
           timeconvert(getattr(cf,"timestamp","")))
          for cf in LST]
    if not LST2:
        LOG.error("No new combifiles to create in {}"
                  .format(LOCS.get_userpath()))

    headers=["Files","Treatment","Layout","Is control?",
             "Timestamp of first"]

    root=tk.Tk()
    TIT="AFVCF: '{}'".format(ALOCS["userfolder"])
    instruction=("Select combined file(s) in user folder {}\n"
                 "to visualize alleles for,\n"
                 "or <Insert> to open plots folder,\n"
                 "or <Escape> to quit.\n\n".format(ALOCS["userfolder"]))
    try:
        DEF=LST2[0][0]
    except:
        DEF=None
    LB7=MultiColumnListbox(root,
                           title=TIT,
                           instruct=instruction,
                           headers=headers,
                           lists=LST2,
                           default=DEF,
                           selectmode="extended")
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    PICK=LB7.values
    if type(PICK)!=list:
        PICK=[PICK]
    combifileobs=[]
    for P in PICK:
        if P is None or P==' ':
            return None
        cfo=CombiFiles(ALOCS["userfolder"])[P]
        combifileobs.append(cfo)
    ALOCS["combifilestovis"]=PICK
    ALOCS["combifileobjects"]=combifileobs
    return ALOCS

def choose_allele_files(ALOCS):
    """
    ALOCS["dnaallelesperstrainfilepath"]
    ALOCS["proteinallelesperstrainfilepath"]
    """
    tit="Locate 'dna alleles per strain' file"
    while not ALOCS.get("dnaallelestrainsshareddata",None):
        FILEPATH=ALOCS["dnaallelesperstrainfilepath"]
        FILEDIR=ALOCS["dnaallelesperstrainfiledir"]
        if not FILEDIR:
            FILEDIR=ALOCS["vcf_filedir"]
        
        root=tk.Tk()
        root.geometry(windowposition)
        root.withdraw()
        filepath=tkFileDialog.askopenfilename(title=tit,
                                              filetypes=[("TAB","*.tab")],
                                              initialdir=FILEDIR,
                                              initialfile=FILEPATH)
        root.destroy()
        if not filepath:
            return
        elif not os.path.exists(filepath):
            continue
        else:
            #open file and check it looks right
            #WIP
            readdata=read_allele_file(filepath)
            if not readdata:
                tit="Not a valid dna allele file. Choose again."
                continue
            else:
                SD,RD=readdata
                ALOCS["dnaallelestrainsshareddata"]=SD
                ALOCS["dnaallelestrainsrowdictionary"]=RD
                ALOCS["dnaallelesperstrainfilepath"]=filepath
                ALOCS["dnaallelesperstrainfiledir"]=os.path.dirname(filepath)
                break
                
    tit="Locate 'protein alleles per strain' file"
    while not ALOCS.get("proteinallelestrainsshareddata",None):
        FILEPATH=ALOCS["proteinallelesperstrainfilepath"]
        FILEDIR=ALOCS["proteinallelesperstrainfiledir"]
        if not FILEDIR:
            FILEDIR=ALOCS["dnaallelesperstrainfiledir"]

        root=tk.Tk()
        root.geometry(windowposition)
        root.withdraw()
        filepath2=tkFileDialog.askopenfilename(title=tit,
                                               filetypes=[("TAB","*.tab")],
                                               initialdir=FILEDIR,
                                               initialfile=FILEPATH)
        root.destroy()
        if not filepath2:
            return
        elif not os.path.exists(filepath2):
            continue
        else:
            #open file and check it looks right
            #WIP
            readdata2=read_allele_file(filepath2)
            if not readdata2:
                tit="Not a valid protein allele file. Choose again."
                continue
            else:
                SD2,RD2=readdata2
                ALOCS["proteinallelestrainsshareddata"]=SD2
                ALOCS["proteinallelestrainsrowdictionary"]=RD2
                ALOCS["proteinallelesperstrainfilepath"]=filepath2
                ALOCS["proteinallelesperstrainfiledir"]=os.path.dirname(filepath2)
                break
    
    return ALOCS

def read_allele_file(filepath):
    ASR=AlleleStrainsReader(filepath)
    RD,SD=ASR.parse()
    return RD,SD

def choose_regions(ALOCS):
    DASD=ALOCS["dnaallelestrainsshareddata"]
    print DASD.keys()
    PASD=ALOCS["proteinallelestrainsshareddata"]
    print PASD.keys()
    #assert DA==PA

    LST=zip(DASD["regionnames"],
            DASD["regionlengths"],
            DASD["totalalleles"],
            PASD["totalalleles"])

    root=tk.Tk()
    TIT="AFVCF"
    instruction=("Select gap or gaps to plot curves by allele")
    headers=["region","regionlength","number of dna alleles","number of protein alleles"]
    LB8=MultiColumnListbox(root,
                           title=TIT,
                           instruct=instruction,
                           headers=headers,
                           selectmode="extended",
                           lists=LST)
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()
    PICK=LB8.values
    if type(PICK)!=list:
        PICK=[PICK]
    if PICK in [None,[None]]: return None
    ALOCS["selectedregions"]=PICK
    
    return ALOCS
#
def main(ALOCS):
    root=tk.Tk()
    instruction=("What do you want to do?\n\n\n"
                 "(select an option below or hit ESCAPE to quit)")
    OB7=OptionBox(root,
                  title="AFVCF",
                  instruct=instruction,
                  options=["Generate alleles from a VCF file",
                           "Visualize alleles from combined files"],
                  default="Visualize alleles from combined files")
    root.focus_force()
    root.geometry(windowposition)
    root.mainloop()

    OPT=OB7.value
    if OPT=="Generate alleles from a VCF file":
        ga=categorize_alleles(ALOCS)
        if ga is False:
            return
        main(ALOCS)
    elif OPT=="Visualize alleles from combined files":
        va=visualize_alleles(ALOCS)
        if va is False:
            return
        else:
            print va
        main(ALOCS)

    elif OPT==None:
        return

#
if __name__=="__main__":
    setup_logging("INFO")
    sys.excepthook=log_uncaught_exceptions
    alocs=AFVCFLocations()
    #p="D:/PHENOSN/Genotypes/AFVCF dna allele per strain Filtered_variants4e_DP3_DP100_MISSING_1_H_MAC.recode.tab"
    #a=AlleleStrainsReader(p)
    #sd,rd=a.parse()
    #print
#    rootdir="D:/YeastGenomicData"
#    bamfiles="AESW12fc/166_Bam_files_from_Matt"
#    vcf1="Filtered_variants4e_DP3_DP40_MISSING_1_H_MAC.recode.vcf" #Most stringently filtered, smallest
#    vcf2="Filtered_variants4e_DP3_DP100_MISSING_1_H_MAC.recode.vcf" #Middling
    #vcf3="Filtered_variants4e_DP3_DP40_MISSING_0.8_H_MAC.recode.vcf" #TOO HUGE
#    vcf4="Filtered_variants4e_DP3_DP100_MISSING_0.8_H_MAC.recode.vcf" #Least stringently filtered, biggest
#    vcfpath=os.path.join(rootdir,bamfiles,vcf2)
#    print check_vcf_file(vcfpath)
    main(alocs)


