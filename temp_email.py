# © 2025 Fr0zst. All rights reserved. 
# Unauthorized copying prohibited.
"""
Temp Email Client — powered by Mail.tm
  - No API key needed
  - New random address every launch
  - Read inbox, open messages, auto-refresh

Run:
    pip install requests
    python temp_email.py

Requires Python 3.8+ with tkinter (standard on Windows/macOS).
Linux: sudo apt install python3-tk
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import requests
import random
import string
import html
import re

# Mail.tm API base 
BASE = "https://api.mail.tm"

# Colour tokens 
BG      = "#f7f7f8"
CARD    = "#ffffff"
ACCENT  = "#2563eb"
ACCENT_H= "#1d4ed8"
MUTED   = "#6b7280"
BORDER  = "#e5e7eb"
SUCCESS = "#16a34a"
DANGER  = "#dc2626"
FONT    = "Helvetica"
AUTO_SEC = 20


# Mail.tm client 

class MailTmClient:
    """
    Wraps the Mail.tm REST API.

    Flow:
      1. GET  /domains           → pick a domain
      2. POST /accounts          → create account (address + password)
      3. POST /token             → get Bearer token
      4. GET  /messages          → list inbox
      5. GET  /messages/{id}     → read full message
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.token   = ""
        self.address = ""
        self.account_id = ""

    def _get(self, path, **kw):
        r = self.session.get(BASE + path, timeout=12, **kw)
        r.raise_for_status()
        return r.json()

    def _post(self, path, **kw):
        r = self.session.post(BASE + path, timeout=12, **kw)
        r.raise_for_status()
        return r.json()

    def _auth_header(self):
        return {"Authorization": f"Bearer {self.token}"}

    # Account lifecycle

    def create_account(self):
        """Pick a domain, create a random account, fetch a token."""
        # 1. Domains
        data = self._get("/domains")
        domains = data.get("hydra:member", [])
        if not domains:
            raise RuntimeError("No domains available from Mail.tm")
        domain = domains[0]["domain"]

        # 2. Random address + password
        user     = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        password = "".join(random.choices(string.ascii_letters + string.digits, k=16))
        address  = f"{user}@{domain}"

        # 3. Create account
        acc = self._post("/accounts", json={"address": address, "password": password})
        self.account_id = acc.get("id", "")

        # 4. Get token
        tok = self._post("/token", json={"address": address, "password": password})
        self.token   = tok["token"]
        self.address = address

        # Update session default header for all future requests
        self.session.headers.update(self._auth_header())
        return address

    # Inbox 

    def get_messages(self):
        """Return list of message summaries."""
        data = self._get("/messages", params={"page": 1})
        return data.get("hydra:member", [])

    def get_message(self, msg_id):
        """Return full message (includes .text and .html)."""
        return self._get(f"/messages/{msg_id}")

    def delete_message(self, msg_id):
        r = self.session.delete(BASE + f"/messages/{msg_id}", timeout=10)
        return r.status_code == 204

    def mark_seen(self, msg_id):
        self.session.patch(
            BASE + f"/messages/{msg_id}",
            json={"seen": True}, timeout=10
        )


# Helpers

def strip_html(raw):
    if not raw:
        return ""
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<p[^>]*>",  "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>",   "",   raw)
    return html.unescape(raw).strip()

def make_btn(parent, text, cmd, accent=False, small=False):
    size = 10 if small else 11
    bg   = ACCENT    if accent else "#eeeeee"
    fg   = "#ffffff" if accent else "#333333"
    abg  = ACCENT_H  if accent else "#dddddd"
    return tk.Button(
        parent, text=text, command=cmd,
        bg=bg, fg=fg, activebackground=abg, activeforeground=fg,
        relief="flat", padx=10 if small else 14, pady=4 if small else 6,
        cursor="hand2", font=(FONT, size),
    )


# Main window

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Temp Email — Mail.tm")
        self.geometry("820x600")
        self.minsize(640, 460)
        self.configure(bg=BG)

        self.client  = MailTmClient()
        self._job    = None
        self._secs   = AUTO_SEC
        self.messages = []

        self._build_ui()
        # Kick off account creation in background
        threading.Thread(target=self._create_account, daemon=True).start()

    # UI build

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg=CARD, padx=14, pady=10)
        top.pack(fill="x")
        top.columnconfigure(0, weight=1)

        tk.Label(top, text="disposable address (mail.tm — no signup needed)",
                 font=(FONT, 9), fg=MUTED, bg=CARD).grid(row=0, column=0, sticky="w")

        self.addr_var = tk.StringVar(value="creating address…")
        tk.Entry(
            top, textvariable=self.addr_var, state="readonly",
            font=(FONT, 13, "bold"), relief="flat",
            readonlybackground=CARD, fg="#111"
        ).grid(row=1, column=0, sticky="ew", pady=(0, 2))

        btns = tk.Frame(top, bg=CARD)
        btns.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
        make_btn(btns, "Copy",        self._copy_addr).pack(side="left", padx=3)
        make_btn(btns, "New Address", self._new_address, accent=True).pack(side="left", padx=3)

        tk.Frame(self, height=1, bg=BORDER).pack(fill="x")

        # Style
        s = ttk.Style()
        s.configure("TNotebook",        background=BG, borderwidth=0)
        s.configure("TNotebook.Tab",    font=(FONT, 11), padding=[12, 5])
        s.configure("Treeview",         rowheight=28, font=(FONT, 11),
                    background=CARD, fieldbackground=CARD)
        s.configure("Treeview.Heading", font=(FONT, 11, "bold"))
        s.map("Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#fff")])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_inbox(nb)

    def _build_inbox(self, nb):
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="  Inbox  ")

        # Controls row
        ctrl = tk.Frame(frame, bg=BG)
        ctrl.pack(fill="x", pady=(4, 6), padx=2)

        make_btn(ctrl, "⟳  Refresh", self._manual_refresh, small=True).pack(side="left")

        self.cd_var = tk.StringVar(value="")
        tk.Label(ctrl, textvariable=self.cd_var,
                 font=(FONT, 10), fg=MUTED, bg=BG).pack(side="left", padx=10)

        self.st_var = tk.StringVar(value="")
        tk.Label(ctrl, textvariable=self.st_var,
                 font=(FONT, 10), fg=MUTED, bg=BG).pack(side="right")

        # Treeview
        lf = tk.Frame(frame, bg=BG)
        lf.pack(fill="both", expand=True, padx=2)

        sb = tk.Scrollbar(lf)
        sb.pack(side="right", fill="y")

        self.tree = ttk.Treeview(
            lf, columns=("from", "subject", "date"),
            show="headings", yscrollcommand=sb.set, selectmode="browse"
        )
        for col, w, label in [
            ("from",    200, "From"),
            ("subject", 350, "Subject"),
            ("date",    180, "Received"),
        ]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=w, anchor="w")

        self.tree.pack(fill="both", expand=True)
        sb.config(command=self.tree.yview)

        self.tree.tag_configure("unread", font=(FONT, 11, "bold"))
        self.tree.bind("<Double-1>", self._open_selected)
        self.tree.bind("<Return>",   self._open_selected)

    # Account

    def _create_account(self):
        try:
            addr = self.client.create_account()
            self.after(0, lambda: self.addr_var.set(addr))
            self.after(0, lambda: self.st_var.set("ready — waiting for mail"))
            self._fetch_inbox()
        except Exception as e:
            self.after(0, lambda: self.addr_var.set(f"Error: {e}"))
            self.after(0, lambda: self.st_var.set("failed to create address"))

    def _new_address(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = None
        self.messages = []
        for r in self.tree.get_children():
            self.tree.delete(r)
        self.addr_var.set("creating address…")
        self.st_var.set("")
        self.cd_var.set("")
        self.client = MailTmClient()
        threading.Thread(target=self._create_account, daemon=True).start()

    # Inbox

    def _manual_refresh(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = None
        threading.Thread(target=self._fetch_inbox, daemon=True).start()

    def _fetch_inbox(self):
        if not self.client.token:
            self._schedule_refresh()
            return
        self.after(0, lambda: self.st_var.set("checking…"))
        try:
            msgs = self.client.get_messages()
            self.messages = msgs
            self.after(0, self._render_inbox)
        except Exception as e:
            self.after(0, lambda: self.st_var.set(f"error: {e}"))
        self._schedule_refresh()

    def _render_inbox(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        if not self.messages:
            self.st_var.set("inbox empty — waiting for mail")
            return
        self.st_var.set(f"{len(self.messages)} message(s)")
        for m in self.messages:
            from_str = m.get("from", {})
            if isinstance(from_str, dict):
                sender = from_str.get("address", from_str.get("name", "?"))
            else:
                sender = str(from_str)
            seen = m.get("seen", True)
            tag  = "" if seen else "unread"
            date = m.get("createdAt", "")[:16].replace("T", "  ")
            self.tree.insert(
                "", "end", iid=m["id"],
                values=(sender, m.get("subject", "(no subject)"), date),
                tags=(tag,)
            )

    def _schedule_refresh(self):
        self._secs = AUTO_SEC
        self._tick()

    def _tick(self):
        self.cd_var.set(f"auto-refresh in {self._secs}s")
        if self._secs <= 0:
            threading.Thread(target=self._fetch_inbox, daemon=True).start()
            return
        self._secs -= 1
        self._job = self.after(1000, self._tick)

    # Message viewer

    def _open_selected(self, _=None):
        sel = self.tree.focus()
        if not sel:
            return
        threading.Thread(target=self._fetch_and_show, args=(sel,), daemon=True).start()

    def _fetch_and_show(self, msg_id):
        try:
            msg = self.client.get_message(msg_id)
            self.client.mark_seen(msg_id)
            self.after(0, lambda: self._show_message(msg))
            # Update tree row to read
            self.after(0, lambda: self.tree.item(msg_id, tags=()))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

    def _show_message(self, msg):
        win = tk.Toplevel(self)
        subj = msg.get("subject", "(no subject)")
        win.title(subj)
        win.geometry("680x520")
        win.configure(bg=CARD)

        # Header
        hdr = tk.Frame(win, bg="#eef2ff", padx=14, pady=12)
        hdr.pack(fill="x")

        tk.Label(hdr, text=subj,
                 font=(FONT, 13, "bold"), bg="#eef2ff",
                 wraplength=620, justify="left").pack(anchor="w")

        from_info = msg.get("from", {})
        if isinstance(from_info, dict):
            sender = f"{from_info.get('name','')} <{from_info.get('address','')}>".strip(" <>")
        else:
            sender = str(from_info)

        date = msg.get("createdAt", "")[:16].replace("T", " at ")
        tk.Label(hdr, text=f"From: {sender}",
                 font=(FONT, 10), fg=MUTED, bg="#eef2ff").pack(anchor="w")
        tk.Label(hdr, text=f"Date: {date}",
                 font=(FONT, 10), fg=MUTED, bg="#eef2ff").pack(anchor="w")

        # Body — prefer plain text, fall back to stripping HTML
        body = msg.get("text", "")
        if not body:
            html_parts = msg.get("html", [])
            raw_html   = html_parts[0] if html_parts else ""
            body       = strip_html(raw_html)
        if not body:
            body = msg.get("intro", "(no content)")

        txt = scrolledtext.ScrolledText(
            win, font=(FONT, 11), wrap="word",
            relief="flat", bg=CARD, padx=14, pady=12
        )
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", body)
        txt.config(state="disabled")

        # Footer buttons
        foot = tk.Frame(win, bg=CARD, pady=8)
        foot.pack(fill="x", padx=14)
        make_btn(foot, "Close",          win.destroy).pack(side="left", padx=(0, 8))
        make_btn(foot, "Delete Message", lambda: self._delete_msg(msg["id"], win)).pack(side="left")

    def _delete_msg(self, msg_id, win):
        ok = self.client.delete_message(msg_id)
        if ok:
            win.destroy()
            self._manual_refresh()
        else:
            messagebox.showerror("Error", "Could not delete message.")

    # Clipboard

    def _copy_addr(self):
        addr = self.addr_var.get()
        if "…" in addr or "Error" in addr:
            return
        self.clipboard_clear()
        self.clipboard_append(addr)
        old = self.st_var.get()
        self.st_var.set("address copied!")
        self.after(2000, lambda: self.st_var.set(old))


# Entry point

if __name__ == "__main__":
    app = App()
    app.mainloop()
