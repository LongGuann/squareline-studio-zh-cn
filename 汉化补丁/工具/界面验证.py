#!/usr/bin/env python3
"""Narrow X11 test helper; only selects the SquareLine Studio window."""
import sys
import time
from pathlib import Path
sys.path.append('/usr/lib/python3/dist-packages')
from Xlib import display, X, XK, protocol
from Xlib.ext import xtest
from PIL import Image

d = display.Display(':0')
root = d.screen().root
windows = []
for wid in root.get_full_property(d.intern_atom('_NET_CLIENT_LIST'), X.AnyPropertyType).value:
    w = d.create_resource_object('window', int(wid))
    if w.get_wm_class() and 'SquareLine_Studio.x86_64' in w.get_wm_class():
        windows.append(w)
if not windows:
    raise SystemExit('未找到 SquareLine 窗口')
dialog_mode = '--dialog' in sys.argv
if dialog_mode:
    sys.argv.remove('--dialog')
    w = next(z for z in windows if z.get_wm_name() == 'Open Project')
else:
    w = max(windows, key=lambda z:z.get_geometry().width*z.get_geometry().height)
root.send_event(protocol.event.ClientMessage(window=w,
    client_type=d.intern_atom('_NET_ACTIVE_WINDOW'), data=(32,[1,X.CurrentTime,0,0,0])),
    event_mask=X.SubstructureRedirectMask|X.SubstructureNotifyMask)
d.sync()
time.sleep(.3)
if dialog_mode:
    w.set_input_focus(X.RevertToParent, X.CurrentTime)
    d.sync()

def key(name):
    mods = name.split('+')
    codes = [d.keysym_to_keycode(XK.string_to_keysym(
        {'ctrl':'Control_L','shift':'Shift_L','alt':'Alt_L'}.get(k,k))) for k in mods]
    for c in codes:
        xtest.fake_input(d,X.KeyPress,c)
    d.sync();time.sleep(.08)
    for c in reversed(codes):
        xtest.fake_input(d,X.KeyRelease,c)
    d.sync()

def type_ascii(value):
    for ch in value:
        sym = ord(ch)
        code = d.keysym_to_keycode(sym)
        shifted = d.keycode_to_keysym(code,0) != sym
        sh = d.keysym_to_keycode(XK.XK_Shift_L)
        if shifted:xtest.fake_input(d,X.KeyPress,sh)
        xtest.fake_input(d,X.KeyPress,code)
        d.sync();time.sleep(.025)
        xtest.fake_input(d,X.KeyRelease,code)
        if shifted:xtest.fake_input(d,X.KeyRelease,sh)
    d.sync()

args=iter(sys.argv[1:])
for cmd in args:
    if cmd=='click':
        x,y=int(next(args)),int(next(args))
        pos=root.translate_coords(w,0,0)
        xtest.fake_input(d,X.MotionNotify,x=pos.x+x,y=pos.y+y)
        d.sync();time.sleep(.12)
        xtest.fake_input(d,X.ButtonPress,1)
        d.sync();time.sleep(.12)
        xtest.fake_input(d,X.ButtonRelease,1)
        d.sync()
        time.sleep(.5)
    elif cmd=='key':
        key(next(args));time.sleep(.3)
    elif cmd=='type':
        type_ascii(next(args));time.sleep(.3)
    elif cmd=='paste':
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk, Gdk
        Gtk.init([])
        clip=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        previous=clip.wait_for_text()
        clip.set_text(next(args),-1)
        key('ctrl+v')
        until=time.monotonic()+1
        while time.monotonic()<until:
            Gtk.main_iteration_do(False)
            time.sleep(.01)
        if previous is not None:
            clip.set_text(previous,-1)
            clip.store()
    elif cmd=='snap':
        g=w.get_geometry()
        im=w.get_image(0,0,g.width,g.height,X.ZPixmap,0xffffffff)
        Image.frombytes('RGB',(g.width,g.height),im.data,'raw','BGRX').save(next(args))
    elif cmd=='close':
        w.send_event(protocol.event.ClientMessage(window=w,client_type=d.intern_atom('WM_PROTOCOLS'),
             data=(32,[d.intern_atom('WM_DELETE_WINDOW'),X.CurrentTime,0,0,0])))
        d.sync()
    else:
        raise SystemExit('未知测试命令：'+cmd)
