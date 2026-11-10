"""Minimal input for the verification script's private Xvfb display only."""
import ctypes as c
import os
import time


class PrivateDisplay:
    def __init__(self, expected_display):
        if os.environ.get('DISPLAY') != expected_display or not expected_display.startswith(':'):
            raise RuntimeError('Private display mismatch')
        self.x = c.CDLL('libX11.so.6')
        self.xt = c.CDLL('libXtst.so.6')
        ptr, win = c.c_void_p, c.c_ulong
        self.x.XOpenDisplay.argtypes = [c.c_char_p]; self.x.XOpenDisplay.restype = ptr
        self.x.XDefaultRootWindow.argtypes = [ptr]; self.x.XDefaultRootWindow.restype = win
        self.x.XQueryTree.argtypes = [ptr, win, c.POINTER(win), c.POINTER(win), c.POINTER(c.POINTER(win)), c.POINTER(c.c_uint)]
        self.x.XFetchName.argtypes = [ptr, win, c.POINTER(c.c_char_p)]
        self.x.XFree.argtypes = [ptr]
        self.x.XMoveResizeWindow.argtypes = [ptr, win, c.c_int, c.c_int, c.c_uint, c.c_uint]
        self.x.XSetInputFocus.argtypes = [ptr, win, c.c_int, c.c_ulong]
        self.x.XSync.argtypes = [ptr, c.c_int]
        self.x.XCloseDisplay.argtypes = [ptr]
        self.x.XStringToKeysym.argtypes = [c.c_char_p]; self.x.XStringToKeysym.restype = c.c_ulong
        self.x.XKeysymToKeycode.argtypes = [ptr, c.c_ulong]; self.x.XKeysymToKeycode.restype = c.c_uint
        self.xt.XTestFakeMotionEvent.argtypes = [ptr,c.c_int,c.c_int,c.c_int,c.c_ulong]
        self.xt.XTestFakeButtonEvent.argtypes = [ptr,c.c_uint,c.c_int,c.c_ulong]
        self.xt.XTestFakeKeyEvent.argtypes = [ptr,c.c_uint,c.c_int,c.c_ulong]
        self.display = self.x.XOpenDisplay(expected_display.encode())
        if not self.display:
            raise RuntimeError('Cannot connect private Xvfb')
        self.window = self.find(self.x.XDefaultRootWindow(self.display))
        if not self.window:
            raise RuntimeError('No Herdr window in private Xvfb')

    def find(self, window):
        title = c.c_char_p()
        if self.x.XFetchName(self.display, window, c.byref(title)) and title.value:
            found = title.value == b'Herdr'; self.x.XFree(title)
            if found:
                return window
        root, parent, children, count = c.c_ulong(), c.c_ulong(), c.POINTER(c.c_ulong)(), c.c_uint()
        if not self.x.XQueryTree(self.display, window, c.byref(root), c.byref(parent), c.byref(children), c.byref(count)):
            return None
        values = [children[i] for i in range(count.value)]
        if children:
            self.x.XFree(children)
        for child in values:
            result = self.find(child)
            if result:
                return result
        return None

    def resize(self, width, height):
        self.x.XMoveResizeWindow(self.display,self.window,0,0,width,height)
        self.x.XSetInputFocus(self.display,self.window,2,0)
        self.x.XSync(self.display,0)
        time.sleep(.3)

    def click(self, x, y, button=1):
        self.xt.XTestFakeMotionEvent(self.display,-1,x,y,0)
        self.xt.XTestFakeButtonEvent(self.display,button,1,0)
        self.xt.XTestFakeButtonEvent(self.display,button,0,0)
        self.x.XSync(self.display,0)
        time.sleep(.2)

    def key(self, name):
        code = self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(name.encode()))
        self.xt.XTestFakeKeyEvent(self.display,code,1,0)
        self.xt.XTestFakeKeyEvent(self.display,code,0,0)
        self.x.XSync(self.display,0)
        time.sleep(.15)

    def type_ascii(self, value):
        for char in value:
            if not (char.isascii() and (char.islower() or char.isdigit() or char == ' ')):
                raise ValueError('Fixture text supports lowercase ASCII, digits and spaces')
            self.key('space' if char == ' ' else char)

    def scroll(self, x, y, down=True, count=8):
        self.xt.XTestFakeMotionEvent(self.display,-1,x,y,0)
        for _ in range(count):
            self.xt.XTestFakeButtonEvent(self.display,5 if down else 4,1,0)
            self.xt.XTestFakeButtonEvent(self.display,5 if down else 4,0,0)
        self.x.XSync(self.display,0)
        time.sleep(.2)

    def close(self):
        self.x.XCloseDisplay(self.display)
