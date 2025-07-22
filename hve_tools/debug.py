
import sys
import platform
import bpy


def debug_mode():
    # return True
    return (bpy.app.debug_value != 0)


def colorize(msg, ):
    if(platform.system() == 'Windows'):
        return msg
    return "{}{}{}".format("\033[42m\033[30m", msg, "\033[0m", )


def log(msg, indent=0, prefix='>', ):
    m = "{}{} {}".format("    " * indent, prefix, colorize(msg, ), )
    if(debug_mode()):
        print(m)


class Progress():
    def __init__(self, total, indent=0, prefix="> ", ):
        self.current = 0
        self.percent = -1
        self.last = -1
        self.total = total
        self.prefix = prefix
        self.indent = indent
        self.t = "    "
        self.r = "\r"
        self.n = "\n"
    
    def step(self, numdone=1):
        if(not debug_mode()):
            return
        self.current += numdone
        self.percent = int(self.current / (self.total / 100))
        if(self.percent > self.last):
            sys.stdout.write(self.r)
            sys.stdout.write("{0}{1}{2}%".format(self.t * self.indent, self.prefix, self.percent))
            self.last = self.percent
        if(self.percent >= 100 or self.total == self.current):
            sys.stdout.write(self.r)
            sys.stdout.write("{0}{1}{2}%{3}".format(self.t * self.indent, self.prefix, 100, self.n))
