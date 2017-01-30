#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-
"""
N.B. 'platedmass' has been renamed 'printedmass' in filenames and
graphical legends, but the underlying variable hasn't been changed
as this would break existing databases.
"""
#STANDARD LIBRARY
import os,sys,shutil,colorsys
from itertools import izip
#OTHER
import brewer2mpl
import numpy as np
from matplotlib import animation,colors,patches,ticker
import matplotlib.cm as clrmap
import matplotlib.pyplot as pyplt
import matplotlib.pylab as pylab
import gc
from scipy.stats import norm
#phenos
from core import LOG,setup_logging,log_uncaught_exceptions,flatten,filterdict,get_traceback,get_config_dict,smooth_series,delta_series,antimirror_before_zero

# #############################################################################

filename = os.path.basename(__file__)
authors = ("David B. H. Barton")
version = "2.7"

# ###########################################################################
def display_image(filepath,figsize=(14,9),aspect=1):
    im=pyplt.imread(filepath)
    fig,ax=pyplt.subplots(figsize=figsize)
    implot=ax.imshow(im,aspect=aspect)
    pyplt.axis('off')
    pyplt.tight_layout()
    pyplt.show()
    try:
        mngr=ax.get_current_fig_manager()
        GEOs='+{}+{}'.format(100,100)
        mngr.window.wm_geometry(GEOs)
    except Exception as e:
        LOG.error("Couldn't resize window because {} {}"
                  .format(e,get_traceback()))
    pyplt.close()

def split_text(txt,maxwidth,split_preferences=["-","/"]):
    if len(txt)<=maxwidth: return txt
    output=[]
    linecounter=0
    for char in txt:
        output.append(char)
        linecounter+=1
        if linecounter==maxwidth:
            output.append("\n")
            linecounter=0
    return "".join(output)

def get_checked_savepath(graphicobject,**kwargs):
    savepath=kwargs.get("savepath",
                        graphicobject.get_graphicspath(**kwargs))
    if not savepath:
        LOG.error("no savepath ({}) returned by {}({})"
                  .format(savepath,
                          type(graphicobject),
                          graphicobject.value))
        return None
    if os.path.exists(savepath):
        if not kwargs.get("overwrite",False):
            LOG.warning("savepath ({}) already exists"
                        .format(savepath))
            if kwargs.get("show",False):
                display_image(savepath)
            return False
    return savepath

def scale_to_proportional(valueslist,confines=None,failvalue=0.0):
    """
    returns scaled values between 0 and 1.
    values are scaled to be fractions of the distance between confines
    (if not specified, confines = min & max values)
    value equal to low confine (or min value) = 0.0
    value half way between confines = 0.5
    value equal to high confine (or max value) = 1.0
    =((v-lowconfine)/(highconfine-lowconfine))
    i.e. [(v-lowconfine)/(highconfine-lowconfine) for v in valueslist]
    """
    if confines is None:
        lowconfine,highconfine=min(valueslist),max(valueslist)
    else:
        lowconfine,highconfine=confines
    output=[]
    for v in valueslist:
        try:
            output.append((v-lowconfine)/float(highconfine-lowconfine))
        except ZeroDivisionError as e:
            LOG.debug("confine problem: highconfine ({}) "
                      "- lowconfine ({}) gives ZeroDivisionError"
                      .format(highconfine,lowconfine))
            output.append(failvalue)
    return output

def scale_from_proportional(valueslist,bounds):
    """
    The opposite of _scale_to_proportional: returns values scaled between bounds
    NB if values are not first scaled to between 0 and 1, the results are confusing...
    """
    lowbound,highbound=bounds
    return [((highbound-lowbound)*v) +lowbound for v in valueslist]

def clip_to_limits(valueslist,floor=0,ceiling=None):
    """
    Clips values below floor to floor and above ceiling to ceiling
    """
    if ceiling is None:
        ceiling=max(valueslist)
    if floor is None:
        floor=min(valueslist)
    output=[]
    for v in valueslist:
        if v<floor:
            output.append(floor)
        elif v>ceiling:
            output.append(ceiling)
        else:
            output.append(v)
    return output

def flagargs(flagslist):
    """
    creates formatting arguments to be passed to PlateView.draw_markers()
    based on the flagvalues argument
    """
    output=[]
    for shouldignorevalue in flagslist:
        if not shouldignorevalue:
            output.append({})
        elif shouldignorevalue=="ignore based on is_blank":
            output.append(dict(marker="s",
                               markersize=14,
                               markeredgecolor='orange',
                               markerfacecolor=u'none'))
        elif shouldignorevalue=="ignore based on strain":
            output.append(dict(marker="x",
                               markersize=10,
                               markeredgecolor='black',
                               markerfacecolor=u'none'))
        elif shouldignorevalue.startswith("ignore based on errorrecord "):
            output.append(dict(marker="x",
                               markersize=10,
                               markeredgecolor='red',
                               markerfacecolor=u'none'))
    return output

def get_graphicstype():
    return get_config_dict()["graphicstype"]

def update_with_named_kwargs(kwargs,namedkwargs):
    output=kwargs.copy()
    output.update({k:v for k,v in namedkwargs.items() if k!="self"})
    return output
#

#GENERAL ####################################################################
class Inker(object):
    """
    Performs operations to convert values to color values (applying colorvaluebounds and limits,
    or putting values into bins when requested), and even choose optimal color schemes
    to suit a particular background color.
    """
    brewer2colordict = dict(flatten([[(k2,k1)
                                      for k2 in v1.keys()]
                                      for k1,v1 in brewer2mpl.COLOR_MAPS.items()]))
    matplotcolormaps = sorted(m for m in pyplt.cm.datad
                              if not m.endswith("_r"))
    htmlcolornames = colors.cnames.keys()
    #assert set(brewer2colordict.keys()).issubset(set(matplotcolormaps))

    def __init__(self,
                 colorvalues=[],
                 colorvaluebounds=None,
                 nbins=None,
                 colorscheme=None,
                 colorschemebounds=(0.0,1.0),
                 backgroundcolor='white',
                 defaults={None:'grey','b':'grey','':(0,0,0,0)},
                 posneg=None,
                 **kwargs):
        """
        colorvaluebounds: if not defined, colorvaluebounds are equal to the minimum and maximum values.
        If sequential coloring is requested (i.e. no binning), then Inker scales numerical
        values so that minimum confine > 0 and maximum confine > 1.
        
        nbins: if specified, Inker splits numerical values into bins for use with a
        qualitative color scheme, rather than a sequential scheme. May be scaled
        according to colorvaluebounds first.
        
        colormap: if specified, then Inker uses that colormap rather than choosing one
        
        colorschemebounds: scalar values, whatever colorvaluebounds they have been scaled within,
        will finally be scaled so that the minimum and maximum values equal the
        colorschemebounds (so that, for example, only a portion of a colormap can be used).

        background: used by Inker to select the foreground colors with the best contrast.
        
        defaults: values matching keys in defaults are automatically converted to the
        color specified in the matching value.


        >>> print Inker([2,8,5,3.5,7.9])
        Inker([2,8...],colorvaluebounds=None,nbins=None)
        colormap: rainbow  defaults: {'b': 'grey', None: 'grey'}
        colorvalues: (0.50,0.00,1.00,1.00),(1.00,0.00,0.00,1.00)...

        >>> print Inker([0.1,0.15,0.13,0.33,0.24,0.11,0.45],nbins=3)
        Inker([0.10,0.15...],colorvaluebounds=None,nbins=3)
        colormap: Dark2  defaults: {'b': 'grey', None: 'grey'}
        colorvalues: (0.85,0.37,0.01,1.00),(0.85,0.37,0.01,1.00)...

        >>> print Inker([0.1,0.15,0.13,0.33,0.24,0.11,0.45],nbins=4,colorvaluebounds=(0,1))
        Inker([0.10,0.15...],colorvaluebounds=(0, 1),nbins=4)
        colormap: Dark2  defaults: {'b': 'grey', None: 'grey'}
        colorvalues: (0.85,0.37,0.01,1.00),(0.85,0.37,0.01,1.00)...

        >>> print Inker([0.1,0.15,0.13,None,None,0.33,0.24,0.11,0.45],colorvaluebounds=(0,1))
        Inker([0.10,0.15...],colorvaluebounds=(0, 1),nbins=None)
        colormap: rainbow  defaults: {'b': 'grey', None: 'grey'}
        colorvalues: (0.30,0.30,0.99,1.00),(0.20,0.45,0.97,1.00)...

        >>> print Inker([-1,0,1],colorvaluebounds=(-1,1),posneg=("Greens","Reds"))
        Inker([-1,0...],colorvaluebounds=(-1, 1),nbins=None)
        colormap: Greens  defaults: {'b': 'grey', None: 'grey'}
        colorvalues: (0.40,0.00,0.05,1.00),(0.97,0.99,0.96,1.00)...
        """
        self.__dict__.update(locals().copy()) #ignore unspecified kwargs
        self.originalvalues=self.colorvalues[:]
        LOG.debug(self.__dict__.keys())
        LOG.debug(kwargs)
        self.check_variables()
        self.convert_values()

    def __call__(self,colorvalues=[],**kwargs):
        if colorvalues:
            self.colorvalues=colorvalues
            return self.convert_values()
        else:
            return self.colors

    def check_variables(self):
        if self.colorscheme is not None:
            if self.colorscheme not in self.matplotcolormaps:
                if not issubclass(self.colorscheme.__class__,colors.Colormap):
                    LOG.error("SPECIFIED COLORMAP {} NOT IN MATPLOTLIB"
                              .format(self.colorscheme))
                    return
            else:
                try:
                    self.colorscheme=self._get_matplotcolormap(self.colorscheme)
                except:
                    LOG.warning("SPECIFIED COLORMAP {} NOT IN MATPLOTLIB; "
                                "SHOULDNT GET THIS ERROR."
                                .format(self.colorscheme))
        else:
            try:
                self.colorscheme=self._get_matplotcolormap(self.colorscheme)
            except:
                LOG.warning("SPECIFIED COLORMAP {} NOT IN MATPLOTLIB; "
                            "SHOULDNT GET THIS ERROR."
                            .format(self.colorscheme))

        if self.backgroundcolor not in self.htmlcolornames:
            LOG.error("SPECIFIED BACKGROUND {} NOT IN MATPLOTLIB"
                      .format(self.backgroundcolor))

        for defaultcolor in self.defaults.values():
            if type(defaultcolor)==tuple:
                pass
            elif defaultcolor not in self.htmlcolornames:
                LOG.error("SPECIFIED DEFAULT COLOR {} NOT IN MATPLOTLIB"
                          .format(defaultcolor))

    def convert_values(self):
        """
        
        """
        #create mixedtypevaluedict of the form:
        #{'float': [[1.0, 2.0, 3.0, 5.0, 8.0], [0, 1, 2, 4, 8]],
        # 'colorstring': [['white', 'gray', 'limegreen', 'grey'], [3, 5, 6, 9]],
        # 'str': [['any old string'], [7]]}
        self.MTVD=self._split_valuetypes(self.colorvalues)

        if "NoneType" in self.MTVD:
            #Convert Nones to default colors
            LOG.debug("NoneType in Inker.MTVL")
            self.MTVD["NoneType"][0]=[default]*len(self.MTVD["NoneType"][0])

        if "float" in self.MTVD:
            floatvalues=self.MTVD["float"][0]
            if self.nbins:
                #if nbins then convert floats into binnedvalue strings
                BI,self.binlabels=self._get_bin_values(floatvalues,
                                                       self.nbins,
                                                       self.colorvaluebounds)
                self.binnedvalues=[self.binlabels[bi] for bi in BI]
                #Now recategorize these as strings
                if "str" not in self.MTVD:
                    self.MTVD["str"]=[[],[]]
                self.MTVD["str"][0]+=self.binnedvalues
                self.MTVD["str"][1]+=self.MTVD["float"][1]
                del self.MTVD["float"]
            
        #if strings AND floats, mix them together and treat all as strings
        if "str" in self.MTVD and "float" in self.MTVD:
            MTVL0=self.MTVD["str"][0]+self.MTVD["float"][0]
            MTVL1=self.MTVD["str"][1]+self.MTVD["float"][1]
            self.MTVD["str"]=[[str(v) for v in MTVL0],MTVL1]
            del self.MTVD["float"]

        #NOW ACTUALLY CONVERT TO COLOR VALUES
        #if strings (or mixed), count categories & generate qualitative colors
        if "str" in self.MTVD:
            self.MTVD["str"][0]=self._get_qualitative_colors(self.MTVD["str"][0],
                                                             colorscheme=self.colorscheme,
                                                             backgroundcolor=self.backgroundcolor,
                                                             pick=1)

        #for floats, scale within colorvaluebounds & get sequential colors
        if "float" in self.MTVD:
            #Now scale to proportional, or sclae pos,neg separately
            f=self.MTVD["float"][0]
            if getattr(self,"colorvaluebounds",None):
                self.legendbounds=self.colorvaluebounds
            else:
                self.legendbounds=(min(f),max(f))
            if self.posneg:
                #then scale pos neg separately
                self.MTVD["float"][0]=self._scale_posneg_to_proportional(self.MTVD["float"][0],
                                                                         colorvaluebounds=self.colorvaluebounds)
                self.MTVD["float"][0]=self._get_posneg_colors(self.MTVD["float"][0],
                                                              posneg=posneg)
                
            else:
                self.MTVD["float"][0]=scale_to_proportional(self.MTVD["float"][0],
                                                            confines=self.colorvaluebounds)
                #NOW GET COLORS:
                self.MTVD["float"][0]=self._get_sequential_colors(self.MTVD["float"][0],
                                                                  colorscheme=self.colorscheme,
                                                                  colorschemebounds=self.colorschemebounds,
                                                                  backgroundcolor=self.backgroundcolor)

        #PUT ALL BACK TOGETHER AGAIN:
        self.colors=self._recombine_valuetypes(self.MTVD)
        return self.colors

    def display(self,printit=True):
        def formatter(v):
            if type(v)==float: return "{:.2f}".format(v)
            else: return str(v)
        vs=",".join([formatter(v) for v in self.colorvalues[:2]])
        output="Inker([{}...],colorvaluebounds={},nbins={})\n".format(vs,self.colorvaluebounds,self.nbins)
        #
        extra=""
        if hasattr(getattr(self,"colorscheme",None),"name"):
            extra+="colorscheme: {}".format(self.colorscheme.name)
        if hasattr(self,"defaults"):
            extra+="  defaults: {}".format(str(self.defaults))
        if extra:
            output+=extra+"\n"
        #
        def colorformatter(c):
            if type(c)==tuple:
                return "({:.2f},{:.2f},{:.2f},{:.2f})".format(*c)
            else: return str(c)

        cvs=",".join([colorformatter(c) for c in self.colors[:2]])
        output+="colorvalues: {}...\n".format(cvs)
        if output.endswith("\n"): output=output[:-1]
        if printit:
            print output
        else:
            return output

    def __str__(self):
        return self.display(printit=False)

    def plot(self,width=15,height=1):
        """
        WIP
        """
        LOG.critical("function needs fixing"); sys.exit()
        self.figure=pyplt.figure(figsize=(width,height))
        self.axes=self.figure.add_subplot(111)
        self.axes.patch.set_facecolor(self.backgroundcolor)
        self.axes.axis((0,width,0,height))
        self.axes.xaxis.set_major_locator(pyplt.NullLocator())
        self.axes.yaxis.set_major_locator(pyplt.NullLocator())
        xcoords=np.linspace(0,width,len(self.colorvalues)+1)[:-1]
        patchwidth=xcoords[1]
        for o,v,x in zip(self.originalvalues,self.colors,xcoords):
            r=pyplt.Rectangle((x,0),
                              width=patchwidth,
                              height=height*0.9,
                              facecolor=v,edgecolor=v)
            t=pyplt.Text(x+(patchwidth/2.),
                         height/2.,str(o),fontsize=8,
                         horizontalalignment='center',
                         verticalalignment='center')
            self.axes.add_artist(r)
            self.axes.add_artist(t)
        pyplt.show()
        pyplt.close()

    def _split_valuetypes(self,mixedtypevaluelist):
        """
        returns dictionary where each type is a key, and each value
        is a 2D list comprising the values and their original indices.
        NB ints are automatically converted to floats and
        put in the dictionary as such.

        >>> mixedtypevaluelist=[1,2,3,"white",5,"gray","limegreen","any old string",8,None]
        >>> d=Inker()._split_valuetypes(mixedtypevaluelist)
        >>> print d
        {'float': [[1.0, 2.0, 3.0, 5.0, 8.0], [0, 1, 2, 4, 8]], 'colorstring': [['white', 'gray', 'limegreen', 'grey'], [3, 5, 6, 9]], 'str': [['any old string'], [7]]}

        >>> for k,v in d.items():
        ...     print k,"\t",v
        float         [[1.0, 2.0, 3.0, 5.0, 8.0], [0, 1, 2, 4, 8]]
        colorstring         [['white', 'gray', 'limegreen', 'grey'], [3, 5, 6, 9]]
        str         [['any old string'], [7]]
        """
        dictionary={}
        for i,v in enumerate(mixedtypevaluelist):
            if v in self.defaults:
                v=self.defaults[v]
                typename="colorstring"
            else:
                typename=type(v).__name__
                if typename in ["int","int32","int64"]:
                    v=float(v)
                    typename="float"
                if typename in ['float32','float64']:
                    typename="float"
                if typename in ['str','string_','unicode']:
                    typename="str"
                    if v in self.htmlcolornames:
                        typename="colorstring"
            if typename not in dictionary:
                dictionary[typename]=[[v],[i]]
            else:
                dictionary[typename][0]+=[v]
                dictionary[typename][1]+=[i]
        return dictionary

    def _recombine_valuetypes(self,splitvaluetypes):
        """
        Recombines the product of the _split_valuetypes() function
        
        >>> mixedtypevaluelist=[1,2,3,"white",5,"gray","limegreen","any old string",8,None]
        >>> d=Inker(defaults={})._split_valuetypes(mixedtypevaluelist)
        >>> print Inker()._recombine_valuetypes(d)
        [1.0, 2.0, 3.0, 'white', 5.0, 'gray', 'limegreen', 'any old string', 8.0, None]
        """
        nestedpairs=[zip(indices,vals)
                     for vals,indices in splitvaluetypes.values()]
        flattenedpairs=flatten(nestedpairs)
        sortedpairs=sorted(flattenedpairs)
        return list(zip(*sortedpairs)[1])

    def _clip_to_bounds(self,valueslist,bounds):
        """
        values clipped so that...
        lower than lowbound => lowbound
        higher than highbound => highbound

        >>> valueslist=[0.1,0.2,0.3,0.4,0.5,0.6]
        >>> print Inker()._clip_to_bounds(valueslist,bounds=(0.2,0.5))
        [0.2, 0.2, 0.3, 0.4, 0.5, 0.5]
        """
        bounds=list(bounds)
        return [sorted(bounds+[v])[1] for v in valueslist]

    def _scale_posneg_to_proportional(self,valueslist,colorvaluebounds):
        """
        >>> valueslist=[-0.1,0.2,-0.3,0.4,-0.5,0.6]
        >>> print Inker()._scale_posneg_to_proportional(valueslist,colorvaluebounds=[-1.0,+2.0])
        [-0.1, 0.1, -0.3, 0.2, -0.5, 0.3]
        """
        assert colorvaluebounds[0]<0 and colorvaluebounds[1]>0
        def cm(v):
            if v<0: return -v/colorvaluebounds[0]
            elif v>=0: return v/colorvaluebounds[1]
        return [cm(v) for v in valueslist]

    def _get_bin_values(self,valueslist,nbins,colorvaluebounds=None):
        """
        Sequential numbers are put into bins for matching to a quantitative colormap

        >>> valueslist=[0.1,0.2,0.3,0.4,0.5,0.6]
        >>> print Inker()._get_bin_values(valueslist,nbins=3)
        ([0, 0, 1, 1, 2, 2], ['0.10-0.27', '0.27-0.43', '0.43-0.60'])
        
        >>> print Inker()._get_bin_values(valueslist,nbins=3,colorvaluebounds=[0.0,1.0])
        ([0, 0, 0, 1, 1, 1], ['0.00-0.33', '0.33-0.67', '0.67-1.00'])
        """
        if colorvaluebounds:
            valueslist=scale_to_proportional(valueslist,
                                             confines=colorvaluebounds)
            lowconfine,highconfine=colorvaluebounds
        else:
            lowconfine,highconfine=min(valueslist),max(valueslist)
        binboundaries=list(np.linspace(lowconfine,highconfine,nbins+1))
        binlabels=["{:.2f}-{:.2f}".format(b1,b2)
                   for b1,b2 in zip(binboundaries,binboundaries[1:])]
        def binindex(v):
            for i,b in enumerate(binboundaries[1:]):
                if v<b: return i
            return i
        binnedvalues=[binindex(v) for v in valueslist]
        return binnedvalues,binlabels

    def _label_as_bins(self,valueslist,nbins):
        """
        >>> valueslist=[0.1,0.2,0.3,0.4,0.5,0.6]
        >>> print Inker()._label_as_bins(valueslist,nbins=3)
        ['0.10-0.27', '0.10-0.27', '0.27-0.43', '0.27-0.43', '0.43-0.60', '0.43-0.60']

        >>> valueslist=[0.1,0.15,0.1,0.55,0.5,0.6]
        >>> print Inker()._label_as_bins(valueslist,nbins=5)
        ['0.10-0.20', '0.10-0.20', '0.10-0.20', '0.50-0.60', '0.50-0.60', '0.50-0.60']
        """
        binnedvalues,binlabels=self._get_bin_values(valueslist,nbins)
        return [binlabels[bv] for bv in binnedvalues]

    def _get_category_values_and_dict(self,valueslist):
        """
        >>> valueslist=[0.1,"purple",0.3,0.1,"purple",None]

        >>> print Inker()._get_category_values_and_dict(valueslist)
        ([1, 3, 2, 1, 3, 0], {'purple': 3, 0.3: 2, None: 0, 0.1: 1})
        """
        dictionary={v:i for i,v in enumerate(sorted(set(valueslist)))}
        return [dictionary[v] for v in valueslist],dictionary
#
    def _get_sequential_colors(self,
                               valueslist,
                               colorscheme,
                               colorschemebounds=(0.0,1.0),
                               backgroundcolor="white"):
        """
        >>> print Inker()._get_sequential_colors([0,0.5,1],colorscheme="rainbow")
        [(0.5, 0.0, 1.0, 1.0), (0.50392156862745097, 0.99998102734872685, 0.70492554690614717, 1.0), (0.49215686274509807, 0.012319659535238442, 0.99998102734872685, 1.0)]
        """
        if colorschemebounds is None or colorschemebounds==(0.0,1.0):
            pass
        else:
            valueslist=scale_from_proportional(valueslist,
                                                     colorschemebounds)

        if type(colorscheme)==str:
            colorscheme=self._get_matplotcolormap(colorscheme)
        #what about sequential bounds for when colors are too close to
        #background or ends of scales are too similar?
        self.colorscheme=colorscheme
        return [colorscheme(v) for v in valueslist]

    def _get_posneg_colors(self,rvalues,posneg=("Greens","Reds")):
        """
        #>>> print Inker()._get_posneg_colors([-1,0,1])
        #[(0.99987697040333468, 0.95820069453295542, 0.93748558619443112, 1.0), (0.9686274528503418, 0.98823529481887817, 0.96078431606292725, 1.0), (0.96641292011036595, 0.9873740876422209, 0.95820069453295542, 1.0)]
        """
        pos_color_map=self._get_matplotcolormap(posneg[0])
        neg_color_map=self._get_matplotcolormap(posneg[1])
        #NEED TO PROPERLY COMBINE
        self.colorscheme=pos_color_map
        return [neg_color_map(-v) if v<0 else pos_color_map(v) for v in rvalues]

    def _get_qualitative_colors(self,values,colorscheme=None,
                                backgroundcolor="white",pick=1):
        """
        Categorical colors (works best if there are no more than 13 colors)

        >>> print Inker()._get_qualitative_colors(['a','b','c','c'])
        [(0.10588235294117647, 0.6196078431372549, 0.4666666666666667, 1.0), (0.4588235294117647, 0.4392156862745098, 0.7019607843137254, 1.0), (0.8509803921568627, 0.37254901960784315, 0.00784313725490196, 1.0), (0.8509803921568627, 0.37254901960784315, 0.00784313725490196, 1.0)]
        """
        if self.nbins is None:
            nb=len(set(values))
        else:
            nb=self.nbins

        if nb>13:
            #Too many categories so use sequential coloring
            #BUT force class variables 'legendcats' and 'legendbounds'
            #so that add_legend() still works.
            category_values,category_dict=self._get_category_values_and_dict(values)
            rvalues=scale_to_proportional(category_values)
            category_colors=self._get_sequential_colors(rvalues,
                                                        colorscheme=colorscheme,
                                                        backgroundcolor=backgroundcolor)
            reverse_category_dict={v:k for k,v in category_dict.items()}
            self.legendcats={}
            for v,c in zip(category_values,category_colors):
                if v not in self.legendcats:
                    self.legendcats[reverse_category_dict[v]]=c
            return category_colors
            
        if colorscheme is None:
            colorscheme=self._pick_best_brewermap(colorbyschemetype="Qualitative",
                                                  nbins=nb,
                                                  background=backgroundcolor,
                                                  pick=pick)
        elif type(colorscheme)=="str":
            colorscheme=self._get_brewermap(colorscheme)
            if colorscheme is not None:
                pass
            else:
                colorscheme=self._get_matplotcolormap(colorscheme)
                if colorscheme is not None:
                    pass
                else:
                    LOG.error("UNKNOWN COLORSCHEME {}".format(colorscheme))
                    return

        self.colorscheme=colorscheme
        output=self._get_qualcolorvalues_from_colormap(colorscheme,values)
        return output

    def _get_colormap_type(self,colormap_object):
        """
        >>> bm=Inker()._get_brewermap("Set3",colorbyschemetype="Qualitative",n_colors=11)
        >>> mm=Inker()._get_matplotcolormap("rainbow")

        >>> print Inker()._get_colormap_type(bm)
        Brewermap
        >>> print Inker()._get_colormap_type(mm)
        Matplotcolormap
        """
        if issubclass(colormap_object.__class__,
                      brewer2mpl.brewer2mpl.BrewerMap):
            return "Brewermap"
        elif issubclass(colormap_object.__class__,
                        colors.Colormap):
            return "Matplotcolormap"
        else:
            LOG.critical("UNKNOWN COLORMAP {}"
                         .format(colormap_object))
            sys.exit()

    def _get_qualcolorvalues_from_colormap(self,colormap_object,values):
        """
        >>> cm=Inker()._pick_best_brewermap(nbins=3,background="white")
        >>> print Inker()._get_qualcolorvalues_from_colormap(cm,['a','b','b','c'])
        [(0.10588235294117647, 0.6196078431372549, 0.4666666666666667, 1.0), (0.4588235294117647, 0.4392156862745098, 0.7019607843137254, 1.0), (0.4588235294117647, 0.4392156862745098, 0.7019607843137254, 1.0), (0.8509803921568627, 0.37254901960784315, 0.00784313725490196, 1.0)]

        >>> cm=Inker()._get_matplotcolormap("rainbow")
        >>> print Inker()._get_qualcolorvalues_from_colormap(cm,['a','b','b','c'])
        [(0.0019607843137254902, 0.0, 0.0039215686274509803, 0.0039215686274509803), (0.0039215686274509803, 4.8025364672445228e-19, 2.4012682336222614e-19, 0.0039215686274509803), (0.0039215686274509803, 4.8025364672445228e-19, 2.4012682336222614e-19, 0.0039215686274509803), (0.001976163014225298, 0.0039214942248969684, 0.0027644139094358711, 0.0039215686274509803)]
        """
        t=self._get_colormap_type(colormap_object)
        CV,CD=self._get_category_values_and_dict(values)
        if t=="Brewermap":
            colormap_colors=[self._rgb255_to_rgbR(*c)
                             for c in colormap_object.colors]
        elif t=="Matplotcolormap":
            spacervalues=np.linspace(0.0,1.0,num=len(CD))
            colormap_colors=[colormap_object(v) for v in spacervalues]
        self.legendcats=dict(zip(CD.keys(),colormap_colors))
        return [self.legendcats[v] for v in values]

#
    def _htmlcolornamelist_to_rgb255(self,htmlcolornamelist):
        """
        >>> colornames=["white","black","limegreen","indigo"]
        >>> for rgb255 in Inker()._htmlcolornamelist_to_rgb255(colornames):
        ...     print rgb255
        (255, 255, 255)
        (0, 0, 0)
        (50, 205, 50)
        (75, 0, 130)
        >>> print Inker()._htmlcolornamelist_to_rgb255(["Gray"])
        [(128, 128, 128)]
        """
        assert type(htmlcolornamelist)==list
        return [self._rgbR_to_rgb255(*colors.colorConverter.to_rgb(name.lower())) for name in htmlcolornamelist]

    def _rgb255_to_rgbR(self,r,g,b,a=255.0):
        """
        >>> print Inker()._rgb255_to_rgbR(0,0,0) #black
        (0.0, 0.0, 0.0, 1.0)
        >>> print Inker()._rgb255_to_rgbR(255,255,255) #white
        (1.0, 1.0, 1.0, 1.0)
        >>> print Inker()._rgb255_to_rgbR(50,205,50) #limegreen
        (0.19607843137254902, 0.803921568627451, 0.19607843137254902, 1.0)
        """
        return r/255.0,g/255.0,b/255.0,a/255.0

    def _rgbR_to_rgb255(self,r,g,b,a=None):
        """
        >>> print Inker()._rgbR_to_rgb255(1.0, 1.0, 1.0) #white
        (255, 255, 255)
        """
        return (int(255*r),int(255*g),int(255*b))

    def _brightness_difference(self,foreground255,background255):
        """
        Should be greater than 125
        Ref: http://www.had2know.com/technology/color-contrast-calculator-web-design.html

        >>> background_rgb255=(255,255,255) #white
        >>> foreground_rgb255=(50,205,50) #limegreen
        >>> print Inker()._brightness_difference(foreground_rgb255,background_rgb255)
        114.015
        >>> foreground_rgb255=(75, 0, 130) #indigo
        >>> print Inker()._brightness_difference(foreground_rgb255,background_rgb255)
        217.755
        """
        brightness_func=lambda r,g,b:((299*r)+(587*g)+(114*b))/1000.0
        difference=abs(brightness_func(*foreground255) - brightness_func(*background255))
        return difference

    def _hue_difference(self,foreground255,background255):
        """
        Should be greater than 500
        Ref: http://www.had2know.com/technology/color-contrast-calculator-web-design.html

        >>> background_rgb255=(255,255,255) #white
        >>> foreground_rgb255=(50,205,50) #limegreen
        >>> print Inker()._hue_difference(foreground_rgb255,background_rgb255)
        460
        >>> foreground_rgb255=(75, 0, 130) #indigo
        >>> print Inker()._hue_difference(foreground_rgb255,background_rgb255)
        560
        """
        difference=sum([abs(f-b) for f,b in zip(foreground255,background255)])
        return difference
        
    def _difference_score(self,foreground255,background255):
        """
        Should be greater than 0
        Ref: http://www.had2know.com/technology/color-contrast-calculator-web-design.html

        >>> background_rgb255=(255,255,255) #white
        >>> foreground_rgb255=(50,205,50) #limegreen
        >>> print Inker()._difference_score(foreground_rgb255,background_rgb255)
        -250.985
        >>> foreground_rgb255=(75, 0, 130) #indigo
        >>> print Inker()._difference_score(foreground_rgb255,background_rgb255)
        152.755
        """
        penalty=0
        bd=self._brightness_difference(foreground255,background255)-125
        if bd<0: penalty+=100
        hd=self._hue_difference(foreground255,background255)-500
        if hd<0: penalty+=100
        if hd<-400: penalty+=500
        return bd+hd-penalty

    def _get_brewermap(self,colormapname,colorbyschemetype=None,n_colors=None):
        """
        >>> print Inker()._get_brewermap("Accent").name
        Accent
        >>> print Inker()._get_brewermap("Accent").type
        Qualitative
        >>> print Inker()._get_brewermap("Accent").number
        8
        >>> print Inker()._get_brewermap("Accent").colors
        [[127, 201, 127], [190, 174, 212], [253, 192, 134], [255, 255, 153], [56, 108, 176], [240, 2, 127], [191, 91, 23], [102, 102, 102]]
        """
        if colormapname not in self.brewer2colordict:
            return None
        if colorbyschemetype is None:
            colorbyschemetype=self.brewer2colordict[colormapname]
        if n_colors is None:
            n_colors=sorted([int(n) for n in brewer2mpl.COLOR_MAPS[colorbyschemetype][colormapname]])[-1]
        return brewer2mpl.get_map(colormapname,colorbyschemetype,n_colors)

    def _get_matplotcolormap(self,colormapname):
        """
        >>> print Inker()._get_matplotcolormap("rainbow").__class__.__name__
        LinearSegmentedColormap
        """
        if colormapname not in self.matplotcolormaps:
            return None
        return clrmap.get_cmap(colormapname)

    def _pick_best_brewermap(self,colorbyschemetype="Qualitative",
                             nbins=9,background="white",pick=1):
        """
        Returns the [pick]th best ColorBrewer map of the given type, containing
        the specified number of colors, which between them have the highest
        possible overall brightness and hue differences from the background
        Ref: http://www.had2know.com/technology/color-contrast-calculator-web-design.html

        >>> print Inker()._pick_best_brewermap(nbins=7,background="white",pick=1).name
        Dark2
        >>> print Inker()._pick_best_brewermap(nbins=7,background="white",pick=2).name
        Set1
        >>> print Inker()._pick_best_brewermap(nbins=11,background="tan",pick=1).name
        Set3
        """
        if type(background)==str:
            background=self._htmlcolornamelist_to_rgb255([background])[0]

        n_colors=nbins if nbins>3 else 3

        all_suitable=[mapname for mapname,mapset in brewer2mpl.COLOR_MAPS[colorbyschemetype].items() if str(n_colors) in mapset]
        all_maps=[self._get_brewermap(alsu,colorbyschemetype,n_colors) for alsu in all_suitable]

        all_scores=[sum([self._difference_score(col,background) for col in colorbyscheme.colors]) for colorbyscheme in all_maps]
        scoredpairs=sorted(zip(all_scores,all_maps))

        winningscore,winningmap=scoredpairs[-pick]
        return winningmap
#

#GRAPHICS TYPES #############################################################
class PlateView(object):
    def __init__(self,
                 coords=[],
                 scalevalues=[],
                 colorvalues='white',
                 colorvaluebounds=None,
                 nbins=None,
                 labels=None,
                 title=None,
                 titleloc='left',
                 titlefontsize=11,
                 savepath=None,
                 extension=get_graphicstype(),
                 copyto=None,
                 show=False,
                 figsize=(15,10),
                 icon=None,

                 xbounds=(0,127.76),    #standard plate breadth
                 ybounds=(0,85.48),     #standard plate width
                 radiusbounds=(0,2.25), #standard 384 maxradius
                 scalevaluebounds=None,
                 colorscheme='rainbow',
                 colorschemebounds=(0,1),
                 backgroundcolor='tan',
                 labelfontsize=None,
                 labelfontcolor='white',
                 labelfontalpha=1.0,
                 labeldepth=0.0,
                 flagvalues=None,
                 legendlabel='',
                 legendloc='lower right',
                 legendcol=None,
                 legendfontsize=7,
                 legendfontcolor='black',
                 invertcolorbar=False,
                 **kwargs):
        self.__dict__.update(locals().copy())
        LOG.debug("unexpected kwargs {}".format(kwargs.keys()))

        self.figure=pyplt.figure(figsize=self.figsize)
        self.axes=self.figure.add_subplot(111)
        self.axes.patch.set_facecolor(self.backgroundcolor)
        self.axes.axis(list(self.xbounds)+list(self.ybounds))
        self.axes.xaxis.set_major_locator(pyplt.NullLocator())
        self.axes.yaxis.set_major_locator(pyplt.NullLocator())
        self.axes.invert_yaxis()

        self.main_sequence()

    def __call__(self,**kwargs):
        """
        Meant to save time by preventing constant redrawing
        DOESN'T CURRENTLY WORK
        http://bastibe.de/2013-05-30-speeding-up-matplotlib.html
        """
        if 'coords' in kwargs:
            self.coords=kwargs["coords"]
        if 'scalevalues' in kwargs:
            self.scalevalues=kwargs["scalevalues"]
            self.transform_scalevalues()
        if 'colorvalues' in kwargs:
            self.colorvalues=kwargs["colorvalues"]
            self.transform_colorvalues()
        if 'labels' in kwargs:
            self.labels=kwargs["labels"]
        if 'savepath' in kwargs:
            self.savepath=kwargs["savepath"]
        if 'title' in kwargs:
            self.title=kwargs["title"]

        self.blank_canvas()
        self.main_sequence()

    def __del__(self):
        LOG.debug("closing pyplt")
        pyplt.close()

    def __exit__(self,type=None,value=None,traceback=None):
        self.__del__()

    def main_sequence(self):
        self.nunits=len(self.coords)
        if self.scalevalues:
            self.transform_scalevalues()
            self.transform_colorvalues()
            if self.icon!="square":
                self.draw_circles()
            else:
                self.draw_squares()
        elif self.colorvalues:
            self.transform_colorvalues()
            self.draw_squares()
        if self.flagvalues:
            self.draw_markers()
        if self.labels:
            self.draw_labels()
        self.draw_legend()
        self.axes.set_title(self.title or self.__class__.__name__,
                            loc=self.titleloc,
                            fontsize=self.titlefontsize)
        pyplt.tight_layout()
        self.showsavecopy()

    def transform_colorvalues(self,colorvalues=[],**kwargs):
        changeattribute=False
        if not colorvalues:
            colorvalues=self.colorvalues
            changeattribute=True
        if not kwargs:
            kwargs=self.__dict__.copy()

        allowedkeys=["colorvaluebounds","nbins",
                     "colorscheme","colorschemebounds",
                     "backgroundcolor","defaults","posneg"]
        passedkwargs=filterdict(kwargs,allowedkeys)

        if type(colorvalues)==str:
            self.needlegend=False
            colorvalues=[colorvalues]*self.nunits
        else:
            self.needlegend=True
            if not hasattr(self,"inker"):
                self.inker=Inker(colorvalues,**passedkwargs)
                colorvalues=self.inker.colors
            else:
                colorvalues=self.inker(colorvalues,**passedkwargs)
        
        if changeattribute:
            self.colorvalues=colorvalues
        return colorvalues

    def transform_scalevalues(self,scalevalues=[],
                              tobounds=None,
                              frombounds=None,
                              **kwargs):
        changeattribute=False
        if not scalevalues:
            scalevalues=self.scalevalues
            changeattribute=True
        if type(scalevalues) in [int,float]:
            scalevalues=[scalevalues]*self.nunits
            
        else:
            if not tobounds:
                if getattr(self,"scalevaluebounds",None):
                    tobounds=self.scalevaluebounds
                else:
                    tobounds=(min(scalevalues),max(scalevalues))
            if not frombounds:
                frombounds=self.radiusbounds

            scalevalues=scale_to_proportional(scalevalues,confines=tobounds)
            scalevalues=scale_from_proportional(scalevalues,frombounds)

        if changeattribute:
            self.scalevalues=scalevalues
        return scalevalues

    def draw_circles(self):
        """
        circles
        """
        self.icons=[]
        for xy,r,c in zip(self.coords,self.scalevalues,self.colorvalues):
            pyob=pyplt.Circle(xy,
                              r,
                              facecolor=c,
                              edgecolor=c)
            self.icons.append(pyob)
            self.axes.add_artist(pyob)

    def draw_squares(self):
        scalevalues=self.scalevalues or [self.radiusbounds[1]]*len(self.coords)
        self.icons=[]
        for xy,r,c in zip(self.coords,scalevalues,self.colorvalues):
            if type(r)==tuple:
                rw,rh=r*2
            else:
                rw,rh=r*2,r*2
            xy=(xy[0]-(rw/2.0),xy[1]-(rh/2.0))
            pyob=pyplt.Rectangle(xy,
                                 width=rw,
                                 height=rh,
                                 facecolor=c,
                                 edgecolor=c)
            self.icons.append(pyob)
            self.axes.add_artist(pyob)

    def draw_labels(self):
        if self.labelfontsize is None:
            self.labelfontsize=(self.radiusbounds[1]/4.5)*6
        self.label_objects=[]
        for xy,l in zip(self.coords,self.labels):
            pyob=pyplt.Text(xy[0],xy[1]+self.labeldepth,
                            split_text(str(l),6),
                            fontsize=self.labelfontsize,
                            color=self.labelfontcolor,
                            alpha=self.labelfontalpha,
                            horizontalalignment='center',
                            verticalalignment='center')
            self.label_objects.append(pyob)
            self.axes.add_artist(pyob)

    def draw_markers(self):
        if not hasattr(self,"flagformatdicts"):
            self.flagformatdicts=flagargs(self.flagvalues)
        self.marker_objects=[]
        for xl,fv,fa in zip(self.coords,self.flagvalues,self.flagformatdicts):
            if fv:
                xs,ys=[xl[0]],[xl[1]]
                pyob=pyplt.Line2D(xs,ys,**fa)
                self.marker_objects.append(pyob)
                self.axes.add_artist(pyob)

    def draw_legend(self):
        """"
        create a colorbar legend
        This cludgy method of creating a colorbar comes from
         http://stackoverflow.com/questions/8342549/matplotlib-add-colorbar-to-a-sequence-of-line-plots
         & https://datasciencelab.wordpress.com/2013/12/21/beautiful-plots-with-pandas-and-matplotlib/
        """
        if getattr(self,"needlegend",False):
            if hasattr(self.inker,"defaults"):
                cats={k:v for k,v in self.inker.defaults.items() if k in self.colorvalues}
            else:
                cats={}

            if hasattr(self.inker,"legendcats"):
                cats.update(self.inker.legendcats)

            if hasattr(self.inker,"legendbounds"):
                v1,v2=self.inker.legendbounds
                cm1,cm2=self.colorschemebounds
                if cm1>cm2:
                    invert=True
                    cm1,cm2=cm2,cm1
                else:
                    invert=False

                #UGLY HACK...
                if self.legendloc=="lower right": # [left, bottom, width, height]
                    cbaxes = self.figure.add_axes([0.94, 0.09, 0.01, 0.25])
                elif self.legendloc=="upper left":
                    cbaxes = self.figure.add_axes([0.146, 0.615, 0.01, 0.25])
                elif type(self.legendloc)==list:
                    cbaxes = self.figure.add_axes(self.legendloc)
                #
                colorscheme=self.inker.colorscheme
                #Don't even TRY to understand why I had to do this...
                cb1,cb2=scale_from_proportional([cm1,cm2],(v1,v2))
                sm=pyplt.cm.ScalarMappable(cmap=colorscheme,
                                           norm=pyplt.Normalize(vmin=cb1,
                                                                vmax=cb2))
                sm._A = []
                #print [sm(r/10.0) for r in range(11)]
                cbar = pyplt.colorbar(sm, cax = cbaxes,
                                      alpha=1.0,
                                      orientation=u'vertical')
                if invert:
                    cbar.ax.invert_yaxis()
                    
                #Effectively there is an invisible colorbar which contains all the
                #colors in color_map, tied to a Normalizer which maps values (e.g. 0.23455-1.364125)
                #to the cb1-cb2 range, e.g. 0.23455-1.13821
                #setting clim to e.g. 0.23455-1.364125 means that only part of the
                #colorbar gets shown, a part which corresponds to cm1-cm2 on a scale of 0-1
                #(e.g. 0.0-0.8)
                cbar.set_clim(v1,v2)

                cbar.solids.set_edgecolor("face")
                #Remove colorbar container frame..
                cbar.outline.set_visible(False)
                #Fontsize for colorbar ticklabels..
                cbar.ax.tick_params(labelsize=self.legendfontsize,
                                    labelcolor=self.legendfontcolor) 
                
                #NB when tick values are assigned to the colorbar, their positions
                #are determined as spanning the whole 'invisible colorbar' mentioned above
                #but of course we only see part of that, so tick values and tick labels need
                #to be different. Tick labels need to start at cb1 and end at cb2, with even
                #intervals inbetween. However the labels need to correspond to v1-v2.
                mytks = np.linspace(cb1,cb2,5)
                if invert:
                    v1,v2=v2,v1
                mytklabels = np.linspace(v1,v2,5)

                #Customize colorbar tick labels
                cbar.set_ticks(mytks) 
                cbar.ax.set_yticklabels(["{:.2f}".format(a)
                                         for a in mytklabels], alpha=1)

                #Colorbar label, customize fontsize and distance to colorbar
                
                cbar.set_label(self.legendlabel,
                               alpha=1,
                               rotation=270,
                               fontsize=self.legendfontsize,
                               color=self.legendfontcolor,
                               labelpad=-32)
                cbarytks = pyplt.getp(cbar.ax.axes, 'yticklines') # Remove color bar tick lines, while keeping the tick labels
                pyplt.setp(cbarytks, visible=False)
                return

            if cats:
                hs,ks=[],[]
                for k in sorted(cats.keys()):
                    col=cats[k]
                    hs.append(patches.Patch(color=col, label=k))
                    ks.append(k)
                #NB Various attempts to shift the legend to the right
                #not working:
                #pyplt.subplot(122)
                #cbaxes = self.figure.add_axes([0.85, 0.15, 0.01, 0.25])
                ncol=getattr(self,"legendcol",None)
                extrakwargs={}
                if ncol: extrakwargs["ncol"]=ncol

                pyplt.legend(hs,ks,
                             #bbox_to_anchor=(1, 1),
                             #bbox_transform=pyplt.gcf().transFigure,
                             title=self.legendlabel,
                             frameon=False,
                             loc=self.legendloc,
                             **extrakwargs)
                return

    def blank_canvas(self):
        """
        Leaves axes, background etc unaltered. Meant to save time
        when calling this object with new data, therefore plotting
        more quickly
        """
        self.axes.clear()
        self.axes.patch.set_facecolor(self.backgroundcolor)
        self.axes.axis(list(self.xbounds)+list(self.ybounds))
        self.axes.xaxis.set_major_locator(pyplt.NullLocator())
        self.axes.yaxis.set_major_locator(pyplt.NullLocator())
        self.axes.invert_yaxis()

    def showsavecopy(self):
        if self.savepath:
            directory=os.path.dirname(self.savepath)
            if not os.path.exists(directory): os.makedirs(directory)
            pyplt.savefig(self.savepath,format=self.extension)
            LOG.info("{} created".format(self.savepath))
        if self.copyto:
            directory=os.path.dirname(self.savepath)
            if not os.path.exists(directory): os.makedirs(directory)
            shutil.copy(self.savepath,self.copyto)
            LOG.info("copied to {}".format(self.copyto))
        if self.show:
            pyplt.show()
        #pyplt.close('all')

class PlateAnimation(PlateView):
    def __init__(self,
                 coords=[],
                 scaleseries=[],
                 timeseries=[],
                 colorseries='white',
                 colorvaluebounds=None,
                 nbins=None,
                 labels=None,
                 title=None,
                 titleloc='left',
                 titlefontsize=11,
                 savepath=None,
                 extension="mp4",
                 copyto=None,
                 show=False,
                 figsize=None,
                 icon='circle',

                 xbounds=(0,127.76),    #standard plate breadth
                 ybounds=(0,85.48),     #standard plate width
                 radiusbounds=(0,2.25), #standard 384 maxradius
                 scalevaluebounds=(0,5.0),
                 colorscheme='RdBu',
                 colorschemebounds=(1,0),
                 backgroundcolor='tan',
                 labelframes=30,
                 finalframes=20,
                 timetextfontsize=12,
                 timetextformatter='t={:.1f}hrs',
                 timetextfontcolor='white',
                 timetextlocation=(10,5),
                 labelfontsize=None,
                 labelfontcolor='white',
                 labelfontalpha=1.0,
                 labeldepth=0.0,
                 legendlabel='',
                 legendloc='lower right',
                 legendcol=None,
                 legendfontsize=7,
                 legendfontcolor='black',
                 invertcolorbar=False,
                 **kwargs):
        self.__dict__.update(locals().copy())
        if not self.colorseries: self.colorseries='white'
        LOG.debug(self.__dict__.keys())
        LOG.debug("unexpected kwargs {}".format(kwargs.keys()))

        self.capacity=len(self.coords)
        LF=self.labelframes
        TF=len(self.timeseries)
        FF=self.finalframes

        if not hasattr(self,"nframes"):
            if self.labels:
                self.nframes=LF+TF+FF
            else:
                self.nframes=TF+FF
        self.cursor=-self.labelframes or 0
        self.nunits=len(self.coords)

        if self.capacity==1536:
            if not self.labelfontsize: self.labelfontsize=6
            if not self.figsize: self.figsize=(21,14)
        elif self.capacity==384:
            if not self.labelfontsize: self.labelfontsize=8
            if not self.figsize: self.figsize=(18,12)
        else:
            if not self.labelfontsize: self.labelfontsize=10
            if not self.figsize: self.figsize=(15,10)

        self.figure=pyplt.figure(figsize=self.figsize)
        self.axes=self.figure.add_subplot(111)
        self.axes.patch.set_facecolor(self.backgroundcolor)
        self.axes.axis(list(self.xbounds)+list(self.ybounds))
        self.axes.xaxis.set_major_locator(pyplt.NullLocator())
        self.axes.yaxis.set_major_locator(pyplt.NullLocator())
        self.axes.invert_yaxis()
        
        self.axes.set_title(self.title or self.__class__.__name__,
                            loc=self.titleloc,
                            fontsize=self.titlefontsize)
        self.animator=animation.FuncAnimation(self.figure,
                                              self.update_animation,
                                              init_func=None,
                                              frames=self.nframes,
                                              interval=1,
                                              blit=True)
        pyplt.tight_layout()
        self.showsavecopy()

    def update_values(self):
        self.timevalue=self.timeseries[self.cursor]
        if self.scaleseries:
            self.scalevalues=[recvalues[self.cursor]
                              for recvalues in self.scaleseries]
            self.transform_scalevalues()
        else:
            self.scalevalues=[self.radiusbounds]*len(self.coords)

        if type(self.colorseries)==list:
            if type(self.colorseries[0])==list:
                self.colorvalues=[recvalues[self.cursor]
                                  for recvalues in self.colorseries]
            else:
                self.colorvalues=[self.colorseries[self.cursor]]*len(self.coords)
            self.transform_colorvalues()
        elif type(self.colorseries)==str:
            self.colorvalues=self.colorseries
            self.transform_colorvalues()

    def update_animation(self,*args,**kwargs):
        if self.cursor==-self.labelframes:
            self.draw_labels()
            self.draw_timetext("Layout")
        
        elif self.cursor==0:
            for label in getattr(self,"label_objects",[]):
                label.remove()
            self.update_values()
            if self.icon=="circle":
                self.draw_circles()
            elif self.icon=="square":
                self.draw_squares()
            self.draw_timetext()
            self.draw_legend()
        
        elif 0<self.cursor<len(self.timeseries):
            self.update_values()
            self.draw_timetext()
            for i in range(len(self.coords)):
                if self.icon=="circle":
                    self.icons[i].set_radius(self.scalevalues[i])
                elif self.icon=="square":
                    self.icons[i].set_height(self.scalevalues[i])
                    self.icons[i].set_width(self.scalevalues[i])
                try:
                    self.icons[i].set_color(self.colorvalues[i])
                except:
                    pass
        print self.cursor,
        self.cursor+=1

    def draw_timetext(self,text=None):
        x,y=self.timetextlocation
        if text is None:
            text=self.timetextformatter.format(self.timevalue)
        if hasattr(self,"timetext"):
            self.timetext.set_text(text)
        else:
            self.timetext=pyplt.Text(x,y,
                                     text,
                                     fontsize=self.timetextfontsize,
                                     color=self.timetextfontcolor,
                                     horizontalalignment='right',
                                     verticalalignment='bottom',
                                     animated=True)
            self.axes.add_artist(self.timetext)

    def showsavecopy(self):
        if self.savepath:
            directory=os.path.dirname(self.savepath)
            if not os.path.exists(directory): os.makedirs(directory)
            if self.extension=="mp4":
                self.animator.save(self.savepath,
                                   writer=animation.FFMpegWriter(fps=20,
                                                                 bitrate=10000))
            elif self.extension=="gif":
                LOG.warning("not working on Windows")
                self.animator.save(self.savepath,
                                   writer='imagemagick',fps=60)
            LOG.info("{} created".format(self.savepath))
        if self.copyto:
            directory=os.path.dirname(self.savepath)
            if not os.path.exists(directory): os.makedirs(directory)
            shutil.copy(self.savepath,self.copyto)
            LOG.info("copied to {}".format(self.copyto))
        if self.show:
            pyplt.show()
        try:
            pyplt.close('all')
        except Exception as e:
            LOG.debug("couldn't shut down pyplt because {} {}"
                      .format(e,get_traceback()))

class CurvePlot(PlateView):
    def __init__(self,
                 timevalues=[], #xvalues
                 measurements=[], #yvalues
                 colorvalues='black',
                 colorvaluebounds=None,
                 linewidth=1,
                 nbins=None,
                 labels=None,
                 title=None,
                 titleloc='left',
                 titlefontsize=11,
                 savepath=None,
                 extension=get_graphicstype(),
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
                 xgridlines=None,
                 labelfontsize=None,
                 labelfontcolor='grey',
                 labelfontalpha=1.0,
                 labelcount=20,
                 labelcutoffpercentiles=None,
                 labelbandstart=0.14,
                 labelbandheight=0.5,
                 legendlabel='',
                 legendloc='lower right',
                 legendcol=None,
                 legendfontsize=7,
                 legendfontcolor='black',
                 invertcolorbar=False,
                 extramarkers=None,
                 extramarkercolorvalues=None,
                 extramarkerstyle="*",
                 extramarkersize=20,
                 **kwargs):
        self.__dict__.update(locals().copy())


        LOG.debug(self.__dict__.keys())
        LOG.debug("unexpected kwargs {}".format(kwargs.keys()))

        self.figure=pyplt.figure(figsize=self.figsize)
        self.axes=self.figure.add_subplot(111)
        self.figure.patch.set_facecolor(self.backgroundcolor)
        self.check_bounds()
        
        self.main_sequence()

    def __call__(self,**kwargs):
        """
        Meant to save time by preventing constant redrawing
        http://bastibe.de/2013-05-30-speeding-up-matplotlib.html
        """
        if 'measurements' in kwargs:
            self.measurements=kwargs["measurements"]
        if 'timevalues' in kwargs:
            self.timevalues=kwargs["timevalues"]
            self.transform_timevalues()
        if 'colorvalues' in kwargs:
            self.colorvalues=kwargs["colorvalues"]
            self.transform_colorvalues()
        if 'labels' in kwargs:
            self.labels=kwargs["labels"]
        if 'savepath' in kwargs:
            self.savepath=kwargs["savepath"]
        if 'title' in kwargs:
            self.title=kwargs["title"]

        self.blank_canvas()
        self.main_sequence()

    def check_bounds(self):
        self.transform_timevalues()
        if not self.xbounds:
            self.xbounds=(self.minLx,self.maxLx+1)
        if not self.ybounds:
            flaty=flatten(self.measurements)
            self.ybounds=(min(flaty),max(flaty))

    def transform_timevalues(self):
        if type(self.timevalues[0]) in [list,tuple]:
            flatx=flatten(self.timevalues)
        else:
            flatx=self.timevalues[:]
            self.timevalues=[self.timevalues for x in self.measurements]
        self.minLx,self.maxLx=min(flatx),max(flatx)

    def main_sequence(self):
        self.axes.axis(list(self.xbounds)+list(self.ybounds))
        self.axes.set_xlabel(self.xaxislabel)
        self.axes.set_ylabel(self.yaxislabel)
        self.axes.set_xscale(self.xaxisscale)
        self.axes.set_yscale(self.yaxisscale)

        self.nunits=len(self.measurements)
        if len(self.timevalues)!=self.nunits:
            self.timevalues=self.timevalues[0]
            self.transform_timevalues()
        if self.colorvalues:
            self.transform_colorvalues()
        if self.xgridlines:
            self.draw_xgridlines()
        self.draw_lines()
        self.draw_extramarkers()
        if self.labels:
            self.draw_labels()
        self.draw_legend()
        self.axes.set_title(self.title or self.__class__.__name__,
                            loc=self.titleloc,
                            fontsize=self.titlefontsize)
        pyplt.tight_layout()
        self.showsavecopy()

    def draw_lines(self):
        allowedkeys=["linestyle","marker","markersize","markeredgewidth",
                     "markeredgecolor","markerfacecolor",
                     "markerfacecoloralt","fillstyle","antialiased",
                     "dash_capstyle","solid_capstyle","dash_joinstyle",
                     "solid_joinstyle","pickradius","drawstyle","markevery"]
        largs=filterdict(self.__dict__,allowedkeys)
        if type(self.linewidth) in [list,tuple]:
            LW=self.linewidth
        else:
            LW=[self.linewidth for x in self.measurements]
        for xs,ys,c,lw in izip(self.timevalues,
                               self.measurements,
                               self.colorvalues,
                               LW):
            if len(ys)==1:
                pyob=pyplt.Line2D(xdata=xs,ydata=ys,
                                  marker="o",
                                  markeredgecolor=c,
                                  markerfacecolor=u'none')
            else:
                pyob=pyplt.Line2D(xdata=xs,ydata=ys,
                                  linewidth=lw,
                                  color=c,
                                  **largs)
            self.axes.add_artist(pyob)

    def draw_xgridlines(self):
        for xval in self.xgridlines:
            if xval:
                xs=[xval,xval]
                ys=[0,100]
                pyob=pyplt.Line2D(xdata=xs,ydata=ys,
                                  linewidth=1.0,
                                  linestyle=":",
                                  color='grey',
                                  alpha=1.0)
                self.axes.add_artist(pyob)

    def draw_extramarkers(self):
        if self.extramarkers:
            if len(self.extramarkercolorvalues)==1:
                self.extramarkercolorvalues=[self.extramarkercolorvalues]*len(self.extramarkers)
            for c,(xs,ys) in zip(self.extramarkercolorvalues,self.extramarkers):
                pyob=pyplt.Line2D(xdata=[xs],ydata=[ys],
                                  marker=self.extramarkerstyle,
                                  markersize=self.extramarkersize,
                                  markeredgecolor='black',
                                  markerfacecolor=c)
                self.axes.add_artist(pyob)

    def draw_labels(self):
        """
        
        """
        minx,maxx=self.minLx,self.maxLx
        miny,maxy=self.ybounds
        mingled=[(ys[-1],l,xs,ys) for l,xs,ys in zip(self.labels,
                                                     self.timevalues,
                                                     self.measurements)]
        mingled.sort()
        if len(mingled)>self.labelcount:
            lowestN,highestN=int(self.labelcount/2.0),-int(self.labelcount/2.0)
            if self.labelcutoffpercentiles: # e.g. (0.005,0.005)
                lowestN=int(len(mingled)*(self.labelcutoffpercentiles[0]))
                highestN=-int(len(mingled)*(self.labelcutoffpercentiles[1]))
            lowest=mingled[:lowestN]
            highest=mingled[highestN:]
            select=lowest+highest
            nlabels=len(select)
        else:
            nlabels=len(mingled)
            select=mingled
        labelTxspacings=list(np.linspace(minx+(self.labelbandstart*maxx),
                                         maxx,nlabels+3))[1:-1]
        #make gap between lowest and highest ranking labels:
        labelTxspacings.pop(int(((len(labelTxspacings)-1)/2)))
        labelTyspacings=list(np.linspace(maxy,maxy-self.labelbandheight,7)[1:-1])*nlabels
        labelLxspacings=np.linspace(self.minLx,self.maxLx,nlabels+2)[1:-1]
        
        for (y,l,xs,ys),Tx,Ty,Lx in zip(select,labelTxspacings,
                                        labelTyspacings,labelLxspacings):
            #Now find Ly, the closest y in ys, corresponding to
            #the x in xs that is closest to Lx:
            closest_index=min(range(len(xs)), key=lambda i: abs(xs[i]-Lx))
            Lx,Ly=xs[closest_index],ys[closest_index]
            self.axes.annotate(l,
                               xy=(Lx,Ly),
                               xytext=(Tx,Ty),
                               textcoords='data',
                               color=self.labelfontcolor,
                               ha='center',
                               va='bottom',
                               #bbox = dict(boxstyle = 'round,pad=0.5', fc = 'yellow', alpha = 0.5),
                               arrowprops=dict(arrowstyle='->',
                                               facecolor=self.labelfontcolor,
                                               edgecolor=self.labelfontcolor,
                                               connectionstyle='arc3,rad=0'))

    def blank_canvas(self):
        """
        Leaves axes, background etc unaltered. Meant to save time
        when calling this object with new data, therefore plotting
        more quickly
        """
        self.axes.clear()

class Histogram(PlateView):
    def __init__(self,
                 values=[],
                 nbins=30,
                 orientation='horizontal',
                 xbounds=(0,2.5),
                 ybounds=(0,3.5),  #standard measurement range
                 title=None,
                 titleloc='left',
                 titlefontsize=11,
                 savepath=None,
                 extension=get_graphicstype(),
                 copyto=None,
                 show=False,
                 figsize=(15,10),
                 xaxislabel='n',
                 yaxislabel='Maximum change in OD600',
                 axislabelfontsize=10,
                 xaxisscale='linear', #could be 'log' or 'symlog'
                 barcolor='green',
                 lowlightcolor='red',
                 barwidth=0.8,
                 barlinewidth=0.4,
                 distcolor='yellow',
                 distlinewidth=2.0,
                 distlinestyle='-',
                 backgroundcolor='white',
                 
                 labelfontsize=None,
                 labelfontcolor='grey',
                 labelfontalpha=1.0,
                 labelcount=20,
                 labelcutoffpercentiles=None,
                 labelbandstart=0.14,
                 labelbandheight=0.5,
                 legendlabel='',
                 legendloc='lower right',
                 legendcol=None,
                 legendfontsize=7,
                 legendfontcolor='black',
                 invertcolorbar=False,
                 **kwargs):
        self.__dict__.update(locals().copy())

        LOG.debug(self.__dict__.keys())
        LOG.debug("unexpected kwargs {}".format(kwargs.keys()))

        self.figure=pyplt.figure(figsize=self.figsize)
        self.axes=self.figure.add_subplot(111)
        self.figure.patch.set_facecolor(self.backgroundcolor)
        self.axes.axis(list(self.xbounds)+list(self.ybounds))
        self.axes.set_xlabel(self.xaxislabel)
        self.axes.set_ylabel(self.yaxislabel)
        self.axes.set_xscale(self.xaxisscale)
        self.axes.set_title(self.title or self.__class__.__name__,
                            loc=self.titleloc,
                            fontsize=self.titlefontsize)
        self.main_sequence()

    def main_sequence(self):
        self.draw_columns()
        pyplt.tight_layout()
        self.showsavecopy()

    def draw_columns(self):
        kwargs=dict()
        miny,maxy=self.ybounds
        n,bins,patches=self.axes.hist(self.values,
                                      self.nbins,
                                      normed=1,
                                      #histtype='stepfilled',
                                      histtype='bar',
                                      orientation=self.orientation,
                                      rwidth=self.barwidth,
                                      linewidth=self.barlinewidth,
                                      label="")
        pyplt.setp(patches,'facecolor',self.barcolor,'alpha',0.75)
        #highlight lowest bar
        pyplt.setp(patches[0],'facecolor',self.lowlightcolor,'alpha',0.75)
        #Set the ticks to be at the edges of the bins.
        self.axes.set_yticks(bins)
        #Set the xaxis's tick labels to be formatted with 1 decimal place...
        F=ticker.FormatStrFormatter('%0.1f')
        self.axes.yaxis.set_major_formatter(F)

        #Now add normal distribution line
        nonzerovalues=[v for v in self.values if v>0.2]
        fit=norm.pdf(nonzerovalues,np.mean(nonzerovalues),
                     np.std(nonzerovalues))
        a,b=zip(*sorted(zip(nonzerovalues,fit)))
        self.axes.add_line(pyplt.Line2D(b,
                                        a,
                                        linewidth=self.distlinewidth,
                                        linestyle=self.distlinestyle,
                                        color=self.distcolor))

class Scatterplot(PlateView):
    def __init__(self,
                 xvalues=[],
                 yvalues=[],
                 scalevalues=50,
                 radiusbounds=(0,10),
                 facecolorvalues='red',
                 edgecolorvalues=None,
                 colorscheme='rainbow',
                 alphavalues=1.0,
                 xbounds=(0,2.5),
                 ybounds=(0,3.5),  #standard measurement range
                 title=None,
                 titleloc='left',
                 titlefontsize=11,
                 savepath=None,
                 extension=get_graphicstype(),
                 copyto=None,
                 show=False,
                 figsize=(10,10),
                 xaxislabel='',
                 yaxislabel='',
                 axislabelfontsize=10,
                 xaxisscale='linear', #could be 'log' or 'symlog'
                 yaxisscale='linear', #could be 'log' or 'symlog'
                 markeredgecolor='green',
                 markerfillcolor='green',
                 markerstyle='o',
                 backgroundcolor='white',
                 
                 labelfontsize=None,
                 labelfontcolor='grey',
                 labelfontalpha=1.0,
                 labelcount=20,
                 labelcutoffpercentiles=None,
                 labelbandstart=0.14,
                 labelbandheight=0.5,
                 legendlabel='',
                 legendloc=[0.9, 0.09, 0.01, 0.25],
                 legendcol=None,
                 legendfontsize=7,
                 legendfontcolor='black',
                 invertcolorbar=False,
                 **kwargs):
        self.__dict__.update(locals().copy())

        LOG.debug(self.__dict__.keys())
        LOG.debug("unexpected kwargs {}".format(kwargs.keys()))

        self.figure=pyplt.figure(figsize=self.figsize)
        self.axes=self.figure.add_subplot(111)
        self.figure.patch.set_facecolor(self.backgroundcolor)
        self.check_bounds()
        self.axes.axis(list(self.xbounds)+list(self.ybounds))
        self.axes.set_xlabel(self.xaxislabel)
        self.axes.set_ylabel(self.yaxislabel)
        self.axes.set_xscale(self.xaxisscale)
        self.axes.set_yscale(self.yaxisscale)
        self.axes.set_title(self.title or self.__class__.__name__,
                            loc=self.titleloc,
                            fontsize=self.titlefontsize)
        self.main_sequence()

    def check_bounds(self):
        if not self.xbounds:
            self.xbounds=(min(self.xvalues),max(self.xvalues))
        if not self.ybounds:
            self.ybounds=(min(self.yvalues),max(self.yvalues))

    def main_sequence(self):
        self.nunits=max([len(self.xvalues),len(self.yvalues)])
        if self.scalevalues:
            self.scalevalues=self.transform_scalevalues(self.scalevalues)
        if self.alphavalues:
            self.alphavalues=self.transform_scalevalues(self.alphavalues,
                                                        tobounds=(0.,1.),
                                                        frombounds=(0.,1.))
        colorargs=self.__dict__.copy()
        del colorargs["self"]
        if self.facecolorvalues:
            self.facecolorvalues=self.transform_colorvalues(self.facecolorvalues)
            self.colorvalues=self.facecolorvalues
            if not hasattr(self,"colorschemebounds"):
                self.colorschemebounds=self.inker.colorschemebounds
            self.needlegend=True
        if self.edgecolorvalues:
            self.edgecolorvalues=self.transform_colorvalues(self.edgecolorvalues,
                                                            **colorargs)
        else:
            self.edgecolorvalues=self.facecolorvalues

        self.draw_markers()
        self.draw_legend()
        pyplt.tight_layout()
        self.showsavecopy()

    def draw_markers(self):
        for x,y,s,ec,fc,a in zip(self.xvalues,
                                 self.yvalues,
                                 self.scalevalues,
                                 self.edgecolorvalues,
                                 self.facecolorvalues,
                                 self.alphavalues):
            self.axes.scatter([x],[y],
                              s, #radius
                              marker=self.markerstyle,
                              alpha=a,
                              edgecolor=ec,
                              facecolor=fc)
#

#DBTYPE FUNCTIONS ###########################################################
def curveplot_allstrains(combireadingstab,
                         strainstab,
                         pathformatter="{plotfolder}/{userfolder}/"
                         "_StrainPlots/{prefix}{graphicsnameroot}"
                         "{suffix}.{extension}",
                     **kwargs):

    namedkwargs=locals().copy()
    unnamedkwargs=kwargs.copy()
    kwargs.update(namedkwargs)

    strainslist=sorted(combireadingstab.get_values_of_atom("strain"))
    strainobs=[]
    for strain in strainslist:
        if strain in ['b','','-']:
            strainob=strainstab.recordclass("b")
        else:
            strainob=strainstab[strain]
        if strainob:
            strainobs.append(strainob)
        else:
            LOG.error("No strain called {} in strains.csv so ignoring"
                      .format(strain))

    #check for existing
    firststrain=strainobs[0]
    folder=os.path.dirname(firststrain.get_graphicspath(**kwargs))
    if os.path.exists(folder):
        filecount=len([name for name in os.listdir(folder)
                       if os.path.isfile(os.path.join(folder,name))])
        if filecount==len(strainobs):
            LOG.warning("found correct number of strainplots for {} "
                        "already"
                        .format(folder))
            return True
    else:
        os.makedirs(folder)

    curveplotobject=None
    for strainob in strainobs:
        recs=list(strainob.yield_records())
        savepath=get_checked_savepath(strainob,**kwargs)
        title=strainob.get_graphicstitle(**kwargs)
        if curveplotobject is None:
            ncpkwargs=dict(timevalues=[cr.timevalues() for cr in recs],
                           measurements=[cr["rawmeasuredvaluesminusagar"]
                                         for cr in recs],
                           colorvalues=[cr["treatment"].value
                                        for cr in recs],
                           yaxislabel='OD600 minus agar',
                           legendlabel='treatment',
                           labels=["{}({})".format(cr["experimentid"].value,
                                                   cr["wellname"].value)
                                   for cr in recs],
                           title=strainob.get_graphicstitle(**kwargs),
                           savepath=savepath)
            ncpkwargs.update(kwargs)
            curveplotobject=CurvePlot(**ncpkwargs)
            nstrainplots=1
        else:
            ncpkwargs=dict(timevalues=[cr.timevalues() for cr in recs],
                           measurements=[cr["rawmeasuredvaluesminusagar"]
                                         for cr in recs],
                           colorvalues=[cr["treatment"].value
                                        for cr in recs],
                           labels=["{}({})".format(cr["experimentid"].value,
                                                   cr["wellname"].value)
                                   for cr in recs],
                           title=strainob.get_graphicstitle(**kwargs),
                           savepath=savepath)
            ncpkwargs.update(unnamedkwargs)
            curveplotobject(**ncpkwargs)
            nstrainplots+=1
    pyplt.close('all')
    del curveplotobject
    gc.collect()
    return nstrainplots

def curveplot_strain(strainob,
                     suffix="",
                     pathformatter="{plotfolder}/{userfolder}/_StrainPlots/"
                     "{prefix}{graphicsnameroot}"
                     "{suffix}.{extension}",
                     **kwargs):
    namedkwargs=locals().copy()
    unnamedkwargs=kwargs.copy()
    kwargs.update(namedkwargs)
    savepath=get_checked_savepath(strainob,**kwargs)

    if savepath!=False or kwargs.get("overwrite",False):
        recs=list(strainob.yield_records())
        ncpkwargs=dict(timevalues=[cr.timevalues() for cr in recs],
                       measurements=[cr["rawmeasuredvaluesminusagar"]
                                     for cr in recs],
                       colorvalues=[cr["treatment"].value
                                    for cr in recs],
                       yaxislabel='OD600 minus agar',
                       legendlabel='treatment',
                       labels=["{}({})".format(cr["experimentid"].value,
                                               cr["wellname"].value)
                               for cr in recs],
                       title=strainob.get_graphicstitle(**kwargs),
                       savepath=savepath)
        ncpkwargs.update(kwargs)
        try:
            cp=CurvePlot(**ncpkwargs)
            return True
        except Exception as e:
            return False

#

#VIEW WRAPPERS ##########################################################
class ViewWrapper(object):
    pass

class AgarThickness(ViewWrapper):
    def __init__(self,combifileob,
                 extension=get_graphicstype(),
                 **kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            CV=[cr["emptymeasure"].value for cr in recs]
            maxrad=combifileob["platedx"].value/2.2
            kwargs2=dict(coords=combifileob.get_coords(),
                         scalevalues=CV,
                         icon="square",
                         radiusbounds=(maxrad/2,maxrad),
                         colorvalues=CV,
                         colorvaluebounds=(0.1,0.5),
                         legendlabel='absorbance of unprinted agar',
                         colorscheme="Oranges",
                         colorschemebounds=(0.2,0.8),
                         labels=[cr["wellname"].value for cr in recs],
                         labelfontsize=8,
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateView(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class LayoutView(ViewWrapper):
    def __init__(self,
                 obwithlayout,
                 **kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(obwithlayout,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(obwithlayout.yield_records())
            kwargs2=dict(coords=obwithlayout.get_coords(),
                         scalevalues=None,
                         colorvalues=None,
                         legendlabel=None,
                         labels=[cr["strain"].value for cr in recs],
                         labelfontsize=8,
                         title=obwithlayout.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateView(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class PrintingQuality(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="scaled by printedmass local min-max "
                        "colored by printedmass (scale=0-0.6)",
                 extension=get_graphicstype(),
                 **kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            PMV=[cr["platedmass"].value for cr in recs] #in the database, it is 'platedmass' for legacy reasons
            kwargs2=dict(coords=combifileob.get_coords(),
                         scalevalues=clip_to_limits(PMV,floor=0),
                         radiusbounds=(0,combifileob["platedx"].value/2.0),
                         colorvalues=PMV,
                         colorvaluebounds=(0,0.6),
                         colorschemebounds=(1.0,0.0),
                         invertcolorbar=True,
                         legendlabel='printedmass',
                         labels=[cr["strain"].value for cr in recs],
                         labelfontsize=6,
                         labelfontalpha=0.75,
                         labeldepth=1.2,
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateView(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class FinalGrowth(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="scaled by maximumwithoutagar",
                 extension=get_graphicstype(),
                 **kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(coords=combifileob.get_coords(),
                         scalevalues=[cr["maximumwithoutagar"] for cr in recs],
                         radiusbounds=(0,combifileob["platedx"].value/2.0),
                         scalevaluebounds=(0,5.0),
                         colorvalues='white',
                         flagvalues=[cr.should_ignore() for cr in recs],
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateView(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class FinalGrowth_PrintedMass(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="scaled by maximumwithoutagar, colored by printedmass",
                 extension=get_graphicstype(),
                 **kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(coords=combifileob.get_coords(),
                         scalevalues=[cr["maximumwithoutagar"] for cr in recs],
                         radiusbounds=(0,combifileob["platedx"].value/2.0),
                         scalevaluebounds=(0,5.0),
                         colorvalues=[cr["platedmass"].value for cr in recs],
                         colorscheme="rainbow",
                         legendlabel='printedmass',
                         labels=[cr["strain"].value for cr in recs],
                         labelfontsize=8,
                         flagvalues=[cr.should_ignore() for cr in recs],
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateView(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class FinalGrowth_Lag(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="scaled by maximumwithoutagar, colored by lag",
                 extension=get_graphicstype(),
                 **kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(coords=combifileob.get_coords(),
                         scalevalues=[cr["maximumwithoutagar"] for cr in recs],
                         radiusbounds=(0,combifileob["platedx"].value/2.0),
                         scalevaluebounds=(0,5.0),
                         colorvalues=[cr.get_lag() for cr in recs],
                         colorscheme="rainbow",
                         legendlabel='lag',
                         labels=[cr["strain"].value for cr in recs],
                         labelfontsize=8,
                         flagvalues=[cr.should_ignore() for cr in recs],
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateView(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class FinalGrowth_MaxSlope(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="scaled by maximumwithoutagar, colored by maxslope",
                 extension=get_graphicstype(),
                 **kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(coords=combifileob.get_coords(),
                         scalevalues=[cr["maximumwithoutagar"] for cr in recs],
                         radiusbounds=(0,combifileob["platedx"].value/2.0),
                         scalevaluebounds=(0,5.0),
                         colorvalues=[cr.get_maxslope() for cr in recs],
                         colorscheme="rainbow",
                         legendlabel='maxslope',
                         labels=[cr["strain"].value for cr in recs],
                         labelfontsize=8,
                         flagvalues=[cr.should_ignore() for cr in recs],
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateView(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class Animation(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="measures without agar",
                 extension="mp4",**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(show=False,
                         coords=combifileob.get_coords(),
                         labels=[cr["strain"].value for cr in recs],
                         labelframes=40,
                         scaleseries=[cr["rawmeasuredvaluesminusagar"]
                                      for cr in recs],
                         colorseries='white',
                         finalframes=30,
                         timeseries=combifileob.timevalues(),
                         xbounds=(0,127.76),    #standard plate breadth
                         ybounds=(0,85.48),     #standard plate width
                         radiusbounds=(0,2.25), #standard 384 maxradius
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateAnimation(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class Animation_Temp(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="measures without agar, colored by temperature",
                 extension="mp4",**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(show=False,
                         coords=combifileob.get_coords(),
                         labels=[cr["strain"].value for cr in recs],
                         labelframes=40,
                         scaleseries=[cr["rawmeasuredvaluesminusagar"]
                                      for cr in recs],
                         colorseries=combifileob.tempvalues() or 'white',
                         colorvaluebounds=(25.0,35.0),
                         finalframes=30,
                         timeseries=combifileob.timevalues(),
                         xbounds=(0,127.76),    #standard plate breadth
                         ybounds=(0,85.48),     #standard plate width
                         radiusbounds=(0,2.25), #standard 384 maxradius
                         colorscheme="RdBu",
                         colorschemebounds=(1.0,0.0),
                         legendlabel='Temperature (C)',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateAnimation(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class CurvesWithoutAgar_PrintedMass(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="colored by printedmass",**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(timevalues=combifileob.timevalues(),
                         measurements=[cr["rawmeasuredvaluesminusagar"]
                                       for cr in recs],
                         yaxislabel='OD600 minus agar',
                         colorvalues=[cr["platedmass"].value
                                      for cr in recs],
                         colorvaluebounds=(0.0,0.6),
                         colorschemebounds=(1.0,0.0),
                         invertcolorbar=True,
                         legendlabel='printedmass',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=CurvePlot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class CurvesWithoutAgar_Groups(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="colored by groupname",**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(timevalues=combifileob.timevalues(),
                         measurements=[cr["rawmeasuredvaluesminusagar"]
                                       for cr in recs],
                         yaxislabel='OD600 minus agar',
                         colorvalues=[cr["readinggroup"].value
                                      for cr in recs],
                         legendlabel='groupname',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=CurvePlot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class CurvesWithoutAgar_Slopes(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="colored by maxslope",**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(timevalues=combifileob.timevalues(),
                         measurements=[cr["rawmeasuredvaluesminusagar"]
                                       for cr in recs],
                         yaxislabel='OD600 minus agar',
                         colorvalues=[cr.get_maxslope()
                                      for cr in recs],
                         colorschemebounds=(1.0,0.0),
                         invertcolorbar=True,
                         legendlabel='slope',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=CurvePlot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class CurvesWithoutAgar_Lags(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="colored by lag",**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(timevalues=combifileob.timevalues(),
                         measurements=[cr["rawmeasuredvaluesminusagar"]
                                       for cr in recs],
                         yaxislabel='OD600 minus agar',
                         colorvalues=[cr.get_lag()
                                      for cr in recs],
                         colorschemebounds=(1.0,0.0),
                         invertcolorbar=True,
                         legendlabel='slope',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=CurvePlot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class CurvesNormalized_PrintedMass(ViewWrapper):
    def __init__(self,combifileob,**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(timevalues=combifileob.timevalues(),
                         measurements=[cr["measuredvalues"]
                                       for cr in recs],
                         yaxislabel='change in OD600 from minimum',
                         colorvalues=[cr["platedmass"].value
                                      for cr in recs],
                         colorvaluebounds=(0.0,0.6),
                         colorschemebounds=(1.0,0.0),
                         invertcolorbar=True,
                         legendlabel='printedmass',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=CurvePlot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class Histogram_MaxWithoutAgar(ViewWrapper):
    def __init__(self,combifileob,**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(values=[rec["maximumwithoutagar"] for rec in recs],
                         nbins=11,
                         color='green',
                         orientation='horizontal',
                         xbounds=(0,2.5),
                         ybounds=(0,3.5),  #standard measurement range
                         yaxislabel='Maximum OD600  minus agar',
                         xaxislabel='n',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=Histogram(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class Histogram_MaxChange(ViewWrapper):
    def __init__(self,combifileob,**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            kwargs2=dict(values=[rec["maximumchange"] for rec in recs],
                         nbins=11,
                         color='green',
                         orientation='horizontal',
                         xbounds=(0,2.5),
                         ybounds=(0,3.5),  #standard measurement range
                         yaxislabel='Maximum change in OD600',
                         xaxislabel='n',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=Histogram(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class Scatterplot_PrintedMass_Lag(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="scaled by maximumwithoutagar",**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combifileob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(combifileob.yield_records())
            XV=[rec["get_lag"] for rec in recs]
            if set(XV)==set([False]):
                LOG.error("No lag calculations possible for {} "
                          "with timepoints {}"
                          .format(combifileob.value,
                                  str(combifileob.timevalues())))
                return False
            if max(XV)>max(combifileob.timevalues()):
                XBOUNDS=(0,max(combifileob.timevalues()))
            else:
                XBOUNDS=None
            YV=[rec["platedmass"].value for rec in recs]
            SV=[rec["maximumwithoutagar"] for rec in recs]
            FCV=[rec["get_maxslope"] for rec in recs]
            #ECV=[str(rec["isborder"].value) for rec in recs]

            kwargs2=dict(xvalues=XV,
                         yvalues=YV,
                         scalevalues=SV,
                         scalevaluebounds=(0,2),
                         radiusbounds=(10,60),
                         facecolorvalues=FCV,
                         legendlabel='maximum slope (OD change/hr)',
                         #edgecolorvalues=ECV,
                         alphavalues=1.0,
                         colorscheme='rainbow',
                         xbounds=XBOUNDS,#
                         ybounds=None,  #
                         #colorvaluebounds=None,
                         xaxislabel='lag (hrs)',
                         yaxislabel='printed mass',
                         title=combifileob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=Scatterplot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class ReplicatePlots(ViewWrapper):
    def __init__(self,combifileob,
                 suffix="measures without agar",
                 pathformatter="{plotfolder}/{userfolder}/"
                               "{experimentfolder}/ReplicatePlots/"
                               "{prefix}{graphicsnameroot}"
                               "{suffix}.{extension}",
                 **kwargs):
        unnamedkwargs=kwargs.copy()
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs["number"]=None
        #check for existing
        RFP=os.path.join(combifileob.get_plotssubfolderpath(),
                         "ReplicatePlots")
        if os.path.exists(RFP):
            filecount=len([name for name in os.listdir(RFP)
                           if os.path.isfile(os.path.join(RFP,name))])
            if filecount==combifileob["platelayout"].nstrains():
                LOG.warning("found correct number of replicateplots for {} "
                            "already"
                            .format(combifileob.value))
                return True
        else:
            os.makedirs(RFP)

        #if it got this far: tally strains in combifileob
        straindict={}
        for record in combifileob.yield_records():
            if record["strain"].value not in straindict:
                straindict[record["strain"].value]=[record]
            else:
                straindict[record["strain"].value].append(record)
        curveplotobject=None
        self.nreplicateplots=0
        for strainname,recs in straindict.items():
            kwargs["prefix"]=strainname
            #savepath=combifileob.get_graphicspath(**kwargs)
            savepath=get_checked_savepath(combifileob,**kwargs)
            title=combifileob.get_graphicstitle(**kwargs)
            if curveplotobject is None:
                #print "FIRST PLOT"+"_"*50
                ncpkwargs=dict(timevalues=combifileob.timevalues(),
                               measurements=[cr["rawmeasuredvaluesminusagar"]
                                             for cr in recs],
                               colorvalues=[cr["platedmass"].value
                                            for cr in recs],
                               yaxislabel='OD600 minus agar',
                               legendlabel='printedmass',
                               colorscheme="rainbow",
                               colorvaluebounds=(0.0,0.6),
                               colorschemebounds=(1.0,0.0),
                               invertcolorbar=True,
                               labels=[cr["wellname"].value
                                       for cr in recs],
                               title=title,
                               savepath=savepath)
                ncpkwargs.update(kwargs)
                curveplotobject=CurvePlot(**ncpkwargs)
                self.nreplicateplots+=1
            else:
                #print "SECOND PLOT"+"_"*50
                ncpkwargs=dict(timevalues=combifileob.timevalues(),
                               measurements=[cr["rawmeasuredvaluesminusagar"]
                                             for cr in recs],
                               colorvalues=[cr["platedmass"].value
                                            for cr in recs],
                               labels=[cr["wellname"].value
                                       for cr in recs],
                               title=title,
                               savepath=savepath)
                ncpkwargs.update(unnamedkwargs)
                curveplotobject(**ncpkwargs)
                self.nreplicateplots+=1
        
        pyplt.close('all')
        del curveplotobject
        gc.collect()

class ControlledRatios(ViewWrapper):
    def __init__(self,controlexpob,
                 extension=get_graphicstype(),**kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        kwargs.setdefault("suffix",
                          "at {:.1f}+-{:.1f}hrs "
                          "scaled by finalaverage"
                          .format(controlexpob["timefocus"].value,
                                  controlexpob["plusminus"].value))
        savepath=get_checked_savepath(controlexpob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            recs=list(controlexpob.yield_records())
            kwargs2=dict(coords=controlexpob.get_coords(),
                         scalevalues=[cr["finalaverage"].value for cr in recs],
                         radiusbounds=(0.5,controlexpob["platedx"].value/2.0),
                         scalevaluebounds=(0,3.0),
                         colorvalues=[cr["ratio"].value for cr in recs],
                         colorscheme="RdYlGn",
                         colorvaluebounds=(0.0,1.5), #fixed color scale
                         colorschemebounds=(0.0,1.0),
                         legendlabel='growth ratio (treatment/control)',
                         labels=[cr["strain"].value for cr in recs],
                         labelfontsize=8,
                         labelfontcolor='CadetBlue',
                         title=controlexpob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=PlateView(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

class CurveAnalysis(ViewWrapper):
    def __init__(self,combireadingob,
                 suffix="measures without agar",
                 smoothing=15,
                 **kwargs):
        kwargs=update_with_named_kwargs(kwargs,locals())
        kwargs.setdefault("prefix",self.__class__.__name__)
        savepath=get_checked_savepath(combireadingob,**kwargs)
        if savepath!=False or kwargs.get("overwrite",False):
            cr=combireadingob
            RM=cr.rawmeasuredvaluesminusagar()
            T=cr.timevalues()
            smoothedRM=smooth_series(RM,k=smoothing)
            smoothedT=smooth_series(T,k=smoothing)
            deltaRM=delta_series(smoothedRM)
            interT=smooth_series(smoothedT,k=2)

            iM,iT=cr.get_inflection(smoothing=smoothing)
            lg=cr.get_lag()
            kwargs2=dict(smoothing=smoothing,
                         timevalues=[T,smoothedT,interT],
                         measurements=[RM,smoothedRM,deltaRM],
                         colorvalues=["black","red","green"],
                         yaxislabel='OD600 minus agar',
                         xgridlines=[iT,lg],
                         colorvaluebounds=(0.0,0.6),
                         colorschemebounds=(1.0,0.0),
                         invertcolorbar=True,
                         legendlabel='printedmass',
                         title=combireadingob.get_graphicstitle(**kwargs),
                         savepath=savepath)
            kwargs2.update(kwargs)
            try:
                viewob=CurvePlot(**kwargs2)
                del viewob
                self.worked=True
            except Exception as e:
                self.worked=False
                self.error=e,get_traceback()

if __name__=="__main__":
    setup_logging("INFO")
    sys.excepthook=log_uncaught_exceptions
    
    from dbtypes import *

#    import doctest
#    doctest.testmod()

