#!/usr/bin/env python -tt
# -*- coding: utf-8 -*-

#STANDARD LIBRARY
import os,sys
import Tkinter as tk
import tkFont
import ttk
import tkFileDialog

# #############################################################################

filename = os.path.basename(__file__)
authors = ("David B. H. Barton")
version = "2.5"

"""
Here the TreeView widget is configured as a multi-column listbox
with adjustable column width and column-header-click sorting.
"""

def browse(root=None,
           startingdirectory=None,
           title="Choose File"):
    SD=startingdirectory
    if SD is None:
        SD=os.path.dirname(os.path.realpath(sys.argv[0]))
    if root is None:
        root=tk.Tk()
        root.withdraw()
    filename=tkFileDialog.askopenfilename(initialdir=SD,
                                              title=title)
    root.destroy()
    return filename

class MultiColumnListbox(object):
    """
    Use a ttk.TreeView as a multicolumn ListBox
    
    http://stackoverflow.com/questions/5286093/display-listbox-with-columns-using-tkinter
    """

    def __init__(self,
                 root=None,
                 title="MultiColumnListbox",
                 instruct="Double click on item to select, or single click "
                 "and hit Enter.\nClick on header to sort by column",
                 buttontext="Select",
                 headers=["1","2"],
                 lists=[(a**20,str(a)*a) for a in range(100)],
                 default=[],
                 height=None,
                 selectmode="browse",
                 notselectable=[],
                 linkedselectionindices=[],
                 delete_fn=None,
                 insert_fn=None):
        self.__dict__.update(locals().copy())
        self.values=[None]

        if type(self.default) not in [list,tuple]:
            self.default=[self.default]
        if self.height is None:
            self.height=min(len(self.lists),30)
        
        if root is None:
            self.root=tk.Tk()
        self.root.title(self.title)
        self.tree=None
        self._setup_widgets()
        self._build_tree()
        if root is None:
            self.root.mainloop()

    def _setup_widgets(self):
        msg=ttk.Label(wraplength="4i",
                      justify="left",
                      anchor="n",
                      padding=(10,2,10,6),
                      foreground="red",
                      text=self.instruct)
        msg.pack(fill='x')
        container=ttk.Frame()
        container.pack(fill='both',
                       expand=True)
        # create a treeview with dual scrollbars
        self.tree=ttk.Treeview(columns=self.headers,
                               show="headings",
                               selectmode=self.selectmode,
                               height=self.height)
        vsb=ttk.Scrollbar(orient="vertical",
                          command=self.tree.yview)
        hsb=ttk.Scrollbar(orient="horizontal",
                          command=self.tree.xview)
        slb=ttk.Button(text=self.buttontext,command=self.choose)
        self.tree.configure(yscrollcommand=vsb.set,
                            xscrollcommand=hsb.set)#,
                            #selectcommand=self.select)
        self.tree.grid(column=0,row=0,sticky='nsew',in_=container)
        vsb.grid(column=1,row=0,sticky='ns',in_=container)
        hsb.grid(column=0,row=1,sticky='ew',in_=container)
        slb.grid(column=0,row=2,sticky='sw',in_=container)
        container.grid_columnconfigure(0,weight=1)
        container.grid_rowconfigure(0,weight=1)
        
        self.tree.bind('<Double-1>',self.choose)
        self.tree.bind("<Return>",self.choose)
        self.tree.bind('<Control-a>',self.selectall)
        self.tree.bind("<Button-1>",self.extraselect)
        self.tree.bind("<Escape>",self.quit)
        self.tree.bind("<Delete>",self.delete)
        self.tree.bind("<Insert>",self.insert)
        self.tree.bind("<MouseWheel>",
                       lambda event: self.tree.xview_scroll(-1*(event.delta/120),
                                                            "units"))
        self.tree.bind("<Left>",
                       lambda event: self.tree.xview_scroll(-30, "units"))
        self.tree.bind("<Right>",
                       lambda event: self.tree.xview_scroll(30, "units"))
        self.tree.bind("<Control-Left>",
                       lambda event: self.tree.xview_moveto(-1))
        self.tree.bind("<Control-Right>",
                       lambda event: self.tree.xview_moveto(1))

    def _build_tree(self):
        for col in self.headers:
            self.tree.heading(col,text=col.title(),
                command=lambda c=col:self._sortby(self.tree,c,0))
            # adjust the column's width to the header string
            self.tree.column(col,
                             width=tkFont.Font().measure(col.title()))

        self.lookup_IO={}
        self.lookup_index={}
        for i,item in enumerate(self.lists):
            IO=self.tree.insert('','end',values=item)
            self.lookup_IO[item[0]]=IO
            self.lookup_index[item[0]]=i
            #adjust column's width if necessary to fit each value
            for ix,val in enumerate(item):
                col_w=tkFont.Font().measure(val)
                #ADJUST HEIGHT?
                #https://groups.google.com/forum/#!topic/comp.lang.tcl/dv2urOQTeUA
                if self.tree.column(self.headers[ix],
                                    width=None)<col_w:
                    self.tree.column(self.headers[ix],
                                     width=col_w)
        #self.tree.configure(rowheight=40)
        #preselect default or defaults
        self.autoselect_items(self.default)

    def autoselect_items(self,itemnames=None,itemindices=None):
        self.focus_indices=[]
        if not itemnames:
            if not itemindices:
                return
            itemnames=[self.lists[i] for i in itemindices]
        if type(itemnames)!=list:
            itemnames=[itemnames]
        IO=None
        for itemname in itemnames:
            if self.notselectable is None:
                self.notselectable=[]
            if itemname not in self.notselectable:
                if itemname in self.lookup_IO:
                    IO=self.lookup_IO[itemname]
                    self.tree.selection_add(IO)
                    self.focus_indices.append(self.lookup_index[itemname])
        self.tree.focus_set()
        if IO:
            self.tree.focus(IO)

    def focus_set(self):
        if self:
            self.container.focus_set()
            if not self.values:
                self.autoselect_items(self.default)
            else:
                self.autoselect_items(self.values)

    def find_linkedselections(self,itemname):
        if not self.linkedselectionindices:
            return []
        else:
            if len(self.linkedselectionindices)!=len(self.lists):
                LOG.error("MultiColumnListbox argument "
                          "'linkedselectionindices' must "
                          "be a list of numbers the same "
                          "length as the items in lists")
                return []
            #create lookup if not already done
            if not hasattr(self,"lookup_linkindex"):
                self.lookup_linkindex={}
                for l,li in zip(self.lists,
                                self.linkedselectionindices):
                    self.lookup_linkindex[l[0]]=li
            #
            #return all itemnames stored under the same lookup_linkindex
            LI=self.lookup_linkindex.get(itemname,None)
            if LI:
                O=[k for k,v in self.lookup_linkindex.items() if v==LI]
                return O
            else:
                return [itemname]

    def _sortby(self,tree,col,descending):
        """sort tree contents when a column header is clicked on"""
        # grab values to sort
        data=[(tree.set(child,col),child)
              for child in tree.get_children('')]
        # if the data to be sorted is numeric change to float
        try:
            data=self._change_numeric(data)
        except:
            pass
        # now sort the data in place
        data.sort(reverse=descending)
        for ix,item in enumerate(data):
            tree.move(item[1],'',ix)
        # switch the heading so it will sort in the opposite direction
        CMD=lambda col=col: self._sortby(tree, col, int(not descending))
        tree.heading(col,command=CMD)

    def change_numeric(self,lst):
        return [(float(v),o) for v,o in lst]

    def changeindex(self,change=None,addition=None):
        itemindices=self.focus_indices or [0]
        if change:
            itemindices=[itemindices[-1]+change]
        if addition:
            if addition<0:
                itemindices+=[min(itemindices)+addition]
            elif addition>0:
                itemindices+=[max(itemindices)+addition]
        self.autoselect_items(itemindices=itemindices)
        return 'break'

    def extraselect(self,event=None):
        self.tree.event_generate("<<TreeviewSelect>>")
        self.choose(close=False)
        return

    def selectall(self,event=None):
        self.autoselect_items(self.lookup_IO.keys())
        

    def choose(self,event=None,close=True,byindices=None):
        if byindices:
            selectedvalues=[self.lists[i][0] for i in byindices]
        else:
            selectedvalues=[self.tree.item(item)['values'][0]
                            for item in self.tree.selection()]
        self.values=[]
        for value in selectedvalues:
            if self.linkedselectionindices:
                linkeditems=self.find_linkedselections(value)
                for item in linkeditems:
                    if item not in self.values:
                        if item not in self.notselectable:
                            self.values.append(item)
            else:
                if value not in self.values:
                    if value not in self.notselectable:
                        self.values.append(value)
            self.autoselect_items(self.values)
        if close:
            if self.values:
                self.quit()
        
    def quit(self,event=None):
        self.root.destroy()

    def delete(self,event=None):
        NS=self.notselectable
        self.notselectable=[]
        self.choose(event)
        self.notselectable=NS
        if self.delete_fn:
            self.delete_fn(self.values)
        self.values=[None]

    def insert(self,event=None):
        NS=self.notselectable
        self.notselectable=[]
        self.choose(event)
        self.notselectable=NS
        if self.insert_fn:
            self.insert_fn(self.values)
        self.values=[None]


class EntryBox(object):
    def __init__(self,
                 root=None,
                 title="EntryBox",
                 instruct="Enter a value",
                 default=None,
                 allowed='ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
        self.__dict__.update(locals().copy())
        
        if root is None:
            self.root=tk.Tk()
        self.root.title(self.title)
        self._setup_widgets()
        self.value=None
        if root is None:
            self.root.mainloop()

    def _setup_widgets(self):
        msg=ttk.Label(wraplength="4i",
                      justify="left",
                      anchor="n",
                      foreground="red",
                      padding=(10,2,10,6),
                      text=self.instruct)
        msg.pack(fill='both')
        #vcmd=(self.root.register(self.validate),
              #'%d','%i','%P','%s','%S','%v','%V','%W')
        self.ent=ttk.Entry(justify="left")#,validate='key',validatecommand=vcmd)
        if self.default:
            self.ent.insert(0,self.default)
        self.ent.pack(fill='both')
        self.ent.focus_set()
        container=ttk.Frame(width=300)
        container.pack(fill='both',
                       expand=True)
        self.ent.bind("<Return>",self.quit)
        self.ent.bind("<Escape>",self.quit)

    def validate(self,action,index,value_if_allowed,
                 prior_value,text,validation_type,trigger_type,widget_name):
        """
        From http://stackoverflow.com/questions/8959815/restricting-the-value-in-tkinter-entry-widget
        Doesn't work properly.
        """
        if text in self.allowed:
            try:
                float(value_if_allowed)
                return True
            except ValueError:
                return False
        else:
            return False


    def quit(self,event=None):
        self.value=self.ent.get()
        self.root.destroy()

class OptionBox(object):
    def __init__(self,
                 root=None,
                 title="EntryBox",
                 instruct="Pick an option",
                 options=["Yes","No"],
                 default="Yes"):
        self.__dict__.update(locals().copy())
        
        if root is None:
            self.root=tk.Tk()
        label=tk.Label(root,
                       foreground="red",
                       text=instruct,
                       width=100)
        label.pack(side="top",fill="both",expand=True,padx=20,pady=20)
        self.buttons=[]
        self.value=None
        for i,opt in enumerate(self.options):
            button=tk.Button(root,
                             text=opt,
                             command=self.quit)
            button.focusindex=i
            button.pack(side="left",fill="both",expand=True,pady=5)
            button.bind("<Left>",self.cycleleft)
            button.bind("<Right>",self.cycleright)
            button.bind("<Escape>",self.quitnone)
            button.bind("<Return>",self.quit)
            button.bind("<Button-1>",self.quit)

            self.buttons.append(button)
        if self.default in self.options:
            self.focusindex=self.options.index(self.default)
        else:
            self.focusindex=0
        self.focus_on_index()

        if root is None:
            self.root.mainloop()

    def focus_on_index(self):
        self.buttons[self.focusindex].focus_force()

    def quitnone(self,event=None):
        self.root.destroy()

    def quit(self,event=None):
        if hasattr(event,"widget"):
            if hasattr(event.widget,"focusindex"):
                self.focusindex=event.widget.focusindex
        self.value=self.options[self.focusindex]
        self.root.destroy()

    def cycleleft(self,event=None):
        self.focusindex-=1
        if self.focusindex<0:
            self.focusindex=0
        self.focus_on_index()

    def cycleright(self,event=None):
        self.focusindex+=1
        if self.focusindex>len(self.buttons)-1:
            self.focusindex=len(self.buttons)-1
        self.focus_on_index()


if __name__ == '__main__':
    root=tk.Tk()
    def printdelete(*args):
        print ">>",args
        
    W=MultiColumnListbox(root,
                         lists=[(c,ord(c),'3') for c in "abcdefghijklm"],
                         default=["c","f"],
                         notselectable=["a"],
                         headers=["char","ord","3"],
                         delete_fn=printdelete,
#                        linkedselectionindices=[0,0,0,0,0,0,0,0,
#                                                 0,1,1,1,0],
                         selectmode="extended")
    #W=EntryBox(root,
    #           instruct="Blah",
    #           default="ENKJN")
    #W=OptionBox(root,options=["A","B","C","D"])
    #complete=[False]
    #W=PleaseWaitBox(root,complete)
    root.focus_force()
    root.mainloop()
    #import time
    #time.sleep(4)
    #complete=[True] #waits for selection/cancel
    print ">",W.values
    
