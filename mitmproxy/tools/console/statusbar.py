import os.path

import urwid

from mitmproxy.tools.console import common
from mitmproxy.tools.console import signals
from mitmproxy.tools.console import commandexecutor
import mitmproxy.tools.console.master # noqa
from mitmproxy.tools.console.commander import commander


class PromptPath:
    def __init__(self, callback, args):
        self.callback, self.args = callback, args

    def __call__(self, pth):
        if not pth:
            return
        pth = os.path.expanduser(pth)
        try:
            return self.callback(pth, *self.args)
        except IOError as v:
            signals.status_message.send(message=v.strerror)


class PromptStub:
    def __init__(self, callback, args):
        self.callback, self.args = callback, args

    def __call__(self, txt):
        return self.callback(txt, *self.args)


class ActionBar(urwid.WidgetWrap):

    def __init__(self, master):
        self.master = master
        urwid.WidgetWrap.__init__(self, None)
        self.clear()
        signals.status_message.connect(self.sig_message)
        signals.status_prompt.connect(self.sig_prompt)
        signals.status_prompt_onekey.connect(self.sig_prompt_onekey)
        signals.status_prompt_command.connect(self.sig_prompt_command)

        self.prompting = None

        self.onekey = False

    def sig_message(self, sender, message, expire=1):
        if self.prompting:
            return
        w = urwid.Text(message)
        self._w = w
        if expire:
            def cb(*args):
                if w == self._w:
                    self.clear()
            signals.call_in.send(seconds=expire, callback=cb)

    def prep_prompt(self, p):
        return p.strip() + ": "

    def sig_prompt(self, sender, prompt, text, callback, args=()):
        signals.focus.send(self, section="footer")
        self._w = urwid.Edit(self.prep_prompt(prompt), text or "")
        self.prompting = PromptStub(callback, args)

    def sig_prompt_command(self, sender, partial=""):
        signals.focus.send(self, section="footer")
        self._w = commander.CommandEdit(self.master, partial)
        self.prompting = commandexecutor.CommandExecutor(self.master)

    def sig_prompt_onekey(self, sender, prompt, keys, callback, args=()):
        """
            Keys are a set of (word, key) tuples. The appropriate key in the
            word is highlighted.
        """
        signals.focus.send(self, section="footer")
        prompt = [prompt, " ("]
        mkup = []
        for i, e in enumerate(keys):
            mkup.extend(common.highlight_key(e[0], e[1]))
            if i < len(keys) - 1:
                mkup.append(",")
        prompt.extend(mkup)
        prompt.append(")? ")
        self.onekey = set(i[1] for i in keys)
        self._w = urwid.Edit(prompt, "")
        self.prompting = PromptStub(callback, args)

    def selectable(self):
        return True

    def keypress(self, size, k):
        if self.prompting:
            if k == "esc":
                self.prompt_done()
            elif self.onekey:
                if k == "enter":
                    self.prompt_done()
                elif k in self.onekey:
                    self.prompt_execute(k)
            elif k == "enter":
                self.prompt_execute(self._w.get_edit_text())
            else:
                if common.is_keypress(k):
                    self._w.keypress(size, k)
                else:
                    return k

    def clear(self):
        self._w = urwid.Text("")
        self.prompting = None

    def prompt_done(self):
        self.prompting = None
        self.onekey = False
        signals.status_message.send(message="")
        signals.focus.send(self, section="body")

    def prompt_execute(self, txt):
        p = self.prompting
        self.prompt_done()
        msg = p(txt)
        if msg:
            signals.status_message.send(message=msg, expire=1)


class StatusBar(urwid.WidgetWrap):
    keyctx = ""

    def __init__(
        self, master: "mitmproxy.tools.console.master.ConsoleMaster"
    ) -> None:
        self.master = master
        self.ib = urwid.WidgetWrap(urwid.Text(""))
        self.ab = ActionBar(self.master)
        super().__init__(urwid.Pile([self.ib, self.ab]))
        signals.update_settings.connect(self.sig_update)
        signals.flowlist_change.connect(self.sig_update)
        master.options.changed.connect(self.sig_update)
        master.view.focus.sig_change.connect(self.sig_update)
        master.view.sig_view_add.connect(self.sig_update)
        self.redraw()

    def sig_update(self, sender, flow=None, updated=None):
        self.redraw()

    def keypress(self, *args, **kwargs):
        return self.ab.keypress(*args, **kwargs)

    def get_status(self):
        r = []

        sreplay = self.master.addons.get("serverplayback")
        creplay = self.master.addons.get("clientplayback")

        if len(self.master.options.setheaders):
            r.append("[")
            r.append(("heading_key", "H"))
            r.append("eaders]")
        if len(self.master.options.replacements):
            r.append("[")
            r.append(("heading_key", "R"))
            r.append("eplacing]")
        if creplay.count():
            r.append("[")
            r.append(("heading_key", "cplayback"))
            r.append(":%s]" % creplay.count())
        if sreplay.count():
            r.append("[")
            r.append(("heading_key", "splayback"))
            r.append(":%s]" % sreplay.count())
        if self.master.options.ignore_hosts:
            r.append("[")
            r.append(("heading_key", "I"))
            r.append("gnore:%d]" % len(self.master.options.ignore_hosts))
        if self.master.options.tcp_hosts:
            r.append("[")
            r.append(("heading_key", "T"))
            r.append("CP:%d]" % len(self.master.options.tcp_hosts))
        if self.master.options.intercept:
            r.append("[")
            if not self.master.options.intercept_active:
                r.append("X")
            r.append(("heading_key", "i"))
            r.append(":%s]" % self.master.options.intercept)
        if self.master.options.view_filter:
            r.append("[")
            r.append(("heading_key", "f"))
            r.append(":%s]" % self.master.options.view_filter)
        if self.master.options.stickycookie:
            r.append("[")
            r.append(("heading_key", "t"))
            r.append(":%s]" % self.master.options.stickycookie)
        if self.master.options.stickyauth:
            r.append("[")
            r.append(("heading_key", "u"))
            r.append(":%s]" % self.master.options.stickyauth)
        if self.master.options.default_contentview != "auto":
            r.append("[")
            r.append(("heading_key", "M"))
            r.append(":%s]" % self.master.options.default_contentview)
        if self.master.options.has_changed("view_order"):
            r.append("[")
            r.append(("heading_key", "o"))
            r.append(":%s]" % self.master.options.view_order)

        opts = []
        if self.master.options.anticache:
            opts.append("anticache")
        if self.master.options.anticomp:
            opts.append("anticomp")
        if self.master.options.showhost:
            opts.append("showhost")
        if not self.master.options.refresh_server_playback:
            opts.append("norefresh")
        if self.master.options.replay_kill_extra:
            opts.append("killextra")
        if not self.master.options.upstream_cert:
            opts.append("no-upstream-cert")
        if self.master.options.console_focus_follow:
            opts.append("following")
        if self.master.options.stream_large_bodies:
            opts.append(self.master.options.stream_large_bodies)

        if opts:
            r.append("[%s]" % (":".join(opts)))

        if self.master.options.mode != "regular":
            r.append("[%s]" % self.master.options.mode)
        if self.master.options.scripts:
            r.append("[")
            r.append(("heading_key", "s"))
            r.append("cripts:%s]" % len(self.master.options.scripts))

        if self.master.options.save_stream_file:
            r.append("[W:%s]" % self.master.options.save_stream_file)

        return r

    def redraw(self):
        fc = len(self.master.view)
        if self.master.view.focus.flow is None:
            offset = 0
        else:
            offset = self.master.view.focus.index + 1

        if self.master.options.view_order_reversed:
            arrow = common.SYMBOL_UP
        else:
            arrow = common.SYMBOL_DOWN

        marked = ""
        if self.master.view.show_marked:
            marked = "M"

        t = [
            ('heading', ("%s %s [%s/%s]" % (arrow, marked, offset, fc)).ljust(11)),
        ]

        if self.master.options.server:
            host = self.master.options.listen_host
            if host == "0.0.0.0" or host == "":
                host = "*"
            boundaddr = "[%s:%s]" % (host, self.master.options.listen_port)
        else:
            boundaddr = ""
        t.extend(self.get_status())
        status = urwid.AttrWrap(urwid.Columns([
            urwid.Text(t),
            urwid.Text(boundaddr, align="right"),
        ]), "heading")
        self.ib._w = status

    def selectable(self):
        return True
