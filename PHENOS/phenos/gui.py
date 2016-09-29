'''


Here the TreeView widget is configured as a multi-column listbox
with adjustable column width and column-header-click sorting.
'''

import Tkinter as tk
import tkFont
import ttk
import tkFileDialog
import os,sys

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
                 lst=[(a**20,str(a)*a) for a in range(100)],
                 default=[],
                 height=None,
                 selectmode="browse",
                 notselectable=[],
                 linkedselectionindices=[],
                 delete_function=None):
        self.__dict__.update(locals().copy())
        self.value=[]

        if type(self.default) not in [list,tuple]:
            self.default=[self.default]
        if self.height is None:
            self.height=min(len(self.lst),30)
        
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
                command=lambda c=col:self.sortby(self.tree,c,0))
            # adjust the column's width to the header string
            self.tree.column(col,width=tkFont.Font().measure(col.title()))

        self.lookup_IO={}
        for i,item in enumerate(self.lst):
            IO=self.tree.insert('','end',values=item)
            self.lookup_IO[item[0]]=IO
            #adjust column's width if necessary to fit each value
            for ix,val in enumerate(item):
                col_w=tkFont.Font().measure(val)
                #ADJUST HEIGHT
                #https://groups.google.com/forum/#!topic/comp.lang.tcl/dv2urOQTeUA
                if self.tree.column(self.headers[ix],width=None)<col_w:
                    self.tree.column(self.headers[ix],width=col_w)
        #self.tree.configure(rowheight=40)
        #preselect default or defaults
        self.autoselect_items(self.default)

    def autoselect_items(self,itemnames):
        if not itemnames:
            return
        if type(itemnames)!=list:
            itemnames=[itemnames]
        IO=None
        for itemname in itemnames:
            if itemname not in self.notselectable:
                if itemname in self.lookup_IO:
                    IO=self.lookup_IO[itemname]
                    self.tree.selection_add(IO)
        self.tree.focus_set()
        if IO:
            self.tree.focus(IO)

    def find_linkedselections(self,itemname):
        if not self.linkedselectionindices:
            return []
        else:
            if len(self.linkedselectionindices)!=len(self.lst):
                LOG.error("MultiColumnListbox argument "
                          "'linkedselectionindices' must "
                          "be a list of numbers the same "
                          "length as the items in lst")
                return []
            #create lookup if not already done
            if not hasattr(self,"lookup_linkindex"):
                self.lookup_linkindex={}
                for l,li in zip(self.lst,
                                self.linkedselectionindices):
                    self.lookup_linkindex[l[0]]=li
            #
            #return all itemnames stored under the same lookup_linkindex
            LI=self.lookup_linkindex.get(itemname,None)
            if LI:
                O=[k for k,v
                   in self.lookup_linkindex.items()
                   if v==LI]
                return O
            else:
                return [itemname]

    def sortby(self,tree,col,descending):
        """sort tree contents when a column header is clicked on"""
        # grab values to sort
        data=[(tree.set(child,col),child)
              for child in tree.get_children('')]
        # if the data to be sorted is numeric change to float
        try:
            data=self.change_numeric(data)
        except:
            pass
        # now sort the data in place
        data.sort(reverse=descending)
        for ix,item in enumerate(data):
            tree.move(item[1],'',ix)
        # switch the heading so it will sort in the opposite direction
        CMD=lambda col=col: self.sortby(tree, col, int(not descending))
        tree.heading(col,command=CMD)

    def change_numeric(self,lst):
        return [(float(v),o) for v,o in lst]

    def extraselect(self,event=None):
        self.tree.event_generate("<<TreeviewSelect>>")
        self.choose(quit=False)
        return

        print "SELECTING"
        self.value=[]
        #ignoredelay=self.tree.selection()
        for item in self.tree.selection()[:]:
            print item
            value=self.tree.item(item)['values'][0]
            if self.linkedselectionindices:
                linkeditems=self.find_linkedselections(value)
                for item in linkeditems:
                    if item not in self.value:
                        self.value.append(item)
                self.autoselect_items(linkeditems)
            else:
                if value not in self.value:
                    self.value.append(value)
        print self.value

    def selectall(self,event=None):
        self.autoselect_items(self.lookup_IO.keys())
        

    def choose(self,event=None,quit=True):
        try:
            self.value=[]
            for item in self.tree.selection():
                value=self.tree.item(item)['values'][0]
                if self.linkedselectionindices:
                    linkeditems=self.find_linkedselections(value)
                    for item in linkeditems:
                        if item not in self.value:
                            if item not in self.notselectable:
                                self.value.append(item)
                    self.autoselect_items(self.value)
                else:
                    if value not in self.value:
                        self.value.append(value)
            if len(self.value)==1:
                self.value=self.value[0]
            elif len(self.value)==0:
                self.value=None
            if quit:
                self.quit()
        except IndexError:
            self.value=None
        
    def quit(self,event=None):
        self.root.destroy()

    def delete(self,event=None):
        self.choose(event)
        if self.delete_function:
            self.delete_function(self.value)
        self.value=None

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

"""
class PleaseWaitBox(tk.Frame):
    def __init__(self,root,
                 completionlist,
                 title="PleaseWaitBox",
                 instruct="Please wait..."):
        tk.Frame.__init__(self,root)
        self.root=root
        self.popup=tk.Toplevel(self)
        label=tk.Label(self.popup,text=instruct)
        label.grid(row=0,column=0)
        label.pack(side="top",fill="both",expand=True,padx=20,pady=20)
        self.progressbar=ttk.Progressbar(self.popup,
                                         orient=tk.HORIZONTAL,
                                         length=200,
                                         mode='indeterminate')
        self.progressbar.grid(row=1, column=0)
        self.progressbar.start()
        self.completionlist=completionlist
        self.checkfile()

    def checkfile(self):
        if self.completionlist[0]==True:
            self.progressbar.stop()
            self.popup.destroy()
        else:
            #Call this method after 100 ms.
            self.after(100, self.checkfile) 

class BusyBar(tk.Frame):
    def __init__(self,master=None,**options):
        ""
        http://tkinter.unpythonic.net/wiki/BusyBar
        ""
        # make sure we have sane defaults
        self.master=master
        self.options=options
        self.width=options.setdefault('width', 100)
        self.height=options.setdefault('height', 10)
        self.background=options.setdefault('background', 'gray')
        self.relief=options.setdefault('relief', 'sunken')
        self.bd=options.setdefault('bd', 2)
        
        #extract options not applicable to frames
        self._extractOptions(options)
        
        # init the base class
        tk.Frame.__init__(self, master, options)
        
        self.incr=self.width*self.increment
        self.busy=0
        self.dir='right'
        
        # create the canvas which is the container for the bar
        self.canvas=tk.Canvas(self, height=self.height, width=self.width, bd=0,
                           highlightthickness=0, background=self.background)
        # catch canvas resizes
        self.canvas.bind('<Configure>', self.onSize)
        
        # this is the bar that moves back and forth on the canvas
        self.scale=self.canvas.create_rectangle(0, 0, self.width*self.barWidth, self.height, fill=self.fill)
                                                
        # label that is in the center of the widget
        self.label=self.canvas.create_text(self.canvas.winfo_reqwidth() / 2,
                                           self.height / 2, text=self.text,
                                           anchor="c", fill=self.foreground,
                                           font=self.font)
        self.update()
        self.canvas.pack(side=tk.TOP, fill=tk.X, expand=tk.NO)
        
    def _extractOptions(self, options):
        # these are the options not applicable to a frame
        self.foreground=pop(options, 'foreground', 'yellow')
        self.fill=pop(options, 'fill', 'blue')
        self.interval=pop(options, 'interval', 30)
        self.font=pop(options, 'font','helvetica 10')
        self.text=pop(options, 'text', '')
        self.barWidth=pop(options, 'barWidth', 0.2)
        self.increment=pop(options, 'increment', 0.05)

    # todo - need to implement config, cget, __setitem__, __getitem__ so it's more like a reg widget
    # as it is now, you get a chance to set stuff at the constructor but not after
        
    def onSize(self, e=None):
        self.width = e.width
        self.height = e.height
        # make sure the label is centered
        self.canvas.delete(self.label)
        self.label=self.canvas.create_text(self.width / 2, self.height / 2, text=self.text,
                                           anchor="c", fill=self.foreground, font=self.font)

    def on(self):
        self.busy = 1
        self.canvas.after(self.interval, self.update)
        
    def of(self):
        self.busy = 0

    def update(self):
        # do the move
        x1,y1,x2,y2 = self.canvas.coords(self.scale)
        if x2>=self.width:
            self.dir='left'
        if x1<=0:
            self.dir='right'
        if self.dir=='right':
            self.canvas.move(self.scale, self.incr, 0)
        else:
            self.canvas.move(self.scale, -1*self.incr, 0)

        if self.busy:
            self.canvas.after(self.interval, self.update)
        self.canvas.update_idletasks()
        
def pop(dict, key, default):
    value = dict.get(key, default)
    if dict.has_key(key):
        del dict[key]
    return value
        
        

if __name__=='__main__':
    root=tk.Tk()
    
    def popup():
        win=tk.Toplevel()
        win.title("I'm busy too!")
        bb1=BusyBar(win,text='Wait for me!')
        bb1.pack()
        for i in range(0,30):
                time.sleep(0.1)
                bb1.update()
                root.update()
        bb1.of()
        time.sleep(1)
        win.destroy()

    t=tk.Text(root)
    t.pack(side=tk.TOP)
    bb=BusyBar(root,text='Please Wait')
    bb.pack(side=tk.LEFT,expand=tk.NO)
    but=Button(root,text='Pop-up BusyBar',command=popup)
    but.pack(side=tk.LEFT, expand=tk.NO)
    q=Button(root, text= 'Quit', command=root.destroy)
    q.pack(side=tk.LEFT, expand=tk.NO)
    l=Label(root, text="I'm a status bar !")
    l.pack(side=tk.RIGHT)
    bb.on()
    root.update_idletasks()
    for i in range(0,30):
        time.sleep(0.1)
        root.update()
    bb.of()
    root.mainloop()
"""
if __name__ == '__main__':
    root=tk.Tk()
    W=MultiColumnListbox(root,
                         lst=[(c,ord(c),'3') for c in "abcdefghijklm"],
                         default=["c","f"],
                         notselectable=["a"],
                         headers=["char","ord","3"],
#                         linkedselectionindices=[0,0,0,0,0,0,0,0,
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
    print ">",W.value
    
