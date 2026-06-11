import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import ownskin


ROOT = Path(__file__).resolve().parent
CLI = ROOT / "ownskin.py"


class OwnSkinGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OwnSkinTool")
        self.geometry("920x620")
        self.minsize(820, 540)
        self.selected_mod = tk.StringVar()
        self.package_license_required = tk.BooleanVar(value=True)
        self._build_ui()
        self.refresh_all()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        self.game_path = tk.StringVar()
        self.mod_tools = tk.StringVar()
        self.pengu_loader = tk.StringVar()

        self._path_row(top, 0, "Game", self.game_path, self.browse_game_path)
        self._path_row(top, 1, "mod-tools", self.mod_tools, self.browse_mod_tools)
        self._path_row(top, 2, "Pengu", self.pengu_loader, self.browse_pengu)

        actions = ttk.Frame(self, padding=(10, 0, 10, 8))
        actions.grid(row=1, column=0, sticky="ew")
        for i in range(13):
            actions.columnconfigure(i, weight=0)
        actions.columnconfigure(13, weight=1)

        ttk.Button(actions, text="Save Paths", command=self.save_paths).grid(row=0, column=0, padx=3)
        ttk.Button(actions, text="Import Mod", command=self.import_mod).grid(row=0, column=1, padx=3)
        ttk.Button(actions, text="Import Cache", command=self.import_cache).grid(row=0, column=2, padx=3)
        ttk.Button(actions, text="Skin Browser", command=self.open_skin_browser).grid(row=0, column=3, padx=3)
        ttk.Button(actions, text="Quick Run ID", command=self.quick_run_cache).grid(row=0, column=4, padx=3)
        ttk.Button(actions, text="Build", command=self.build_mod).grid(row=0, column=5, padx=3)
        ttk.Button(actions, text="Run", command=self.run_mod).grid(row=0, column=6, padx=3)
        ttk.Button(actions, text="Stop", command=lambda: self.run_cli(["stop"])).grid(row=0, column=7, padx=3)
        ttk.Button(actions, text="Monitor On", command=lambda: self.run_cli(["monitor-start", "--stop-on-lobby"])).grid(row=0, column=8, padx=3)
        ttk.Button(actions, text="Monitor Off", command=lambda: self.run_cli(["monitor-stop"])).grid(row=0, column=9, padx=3)
        ttk.Button(actions, text="Pengu On", command=lambda: self.run_cli(["pengu", "activate"])).grid(row=0, column=10, padx=3)
        ttk.Button(actions, text="Pengu Off", command=lambda: self.run_cli(["pengu", "deactivate"])).grid(row=0, column=11, padx=3)
        ttk.Button(actions, text="Audit Cache", command=lambda: self.run_cli(["cache-audit"])).grid(row=0, column=12, padx=3)
        ttk.Button(actions, text="Refresh", command=self.refresh_all).grid(row=0, column=13, padx=3)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        left = ttk.Frame(body, padding=8)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        body.add(left, weight=1)

        ttk.Label(left, text="Installed Mods").grid(row=0, column=0, sticky="w")
        self.mods_list = tk.Listbox(left, exportselection=False)
        self.mods_list.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        self.mods_list.bind("<<ListboxSelect>>", self.on_mod_select)

        pkg = ttk.LabelFrame(left, text="Package / License", padding=8)
        pkg.grid(row=2, column=0, sticky="ew")
        pkg.columnconfigure(1, weight=1)
        self.package_version = tk.StringVar(value="1.0.0")
        self.buyer = tk.StringVar(value="customer")
        self.machine_id = tk.StringVar()

        ttk.Label(pkg, text="Version").grid(row=0, column=0, sticky="w")
        ttk.Entry(pkg, textvariable=self.package_version, width=12).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Checkbutton(pkg, text="Require license", variable=self.package_license_required).grid(row=0, column=2, sticky="w")
        ttk.Button(pkg, text="Create Package", command=self.package_mod).grid(row=0, column=3, padx=3)

        ttk.Label(pkg, text="Buyer").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(pkg, textvariable=self.buyer).grid(row=1, column=1, sticky="ew", padx=5, pady=(8, 0))
        ttk.Label(pkg, text="Machine ID").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(pkg, textvariable=self.machine_id).grid(row=2, column=1, sticky="ew", padx=5, pady=(4, 0))
        ttk.Button(pkg, text="Create License", command=self.create_license).grid(row=2, column=2, padx=3, pady=(4, 0))
        ttk.Button(pkg, text="Activate License", command=self.activate_license).grid(row=2, column=3, padx=3, pady=(4, 0))

        ttk.Button(pkg, text="Export Public Key", command=self.export_public_key).grid(row=3, column=2, padx=3, pady=(8, 0))
        ttk.Button(pkg, text="Import Public Key", command=self.import_public_key).grid(row=3, column=3, padx=3, pady=(8, 0))

        right = ttk.Frame(body, padding=8)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        body.add(right, weight=2)

        ttk.Label(right, text="Command Log").grid(row=0, column=0, sticky="w")
        self.log = tk.Text(right, wrap="word", height=10)
        self.log.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        scroll = ttk.Scrollbar(right, orient="vertical", command=self.log.yview)
        scroll.grid(row=1, column=1, sticky="ns", pady=(4, 0))
        self.log.configure(yscrollcommand=scroll.set)

    def _path_row(self, parent, row, label, var, browse):
        ttk.Label(parent, text=label, width=10).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        ttk.Button(parent, text="Browse", command=browse).grid(row=row, column=2, pady=2)

    def append_log(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def run_cli(self, args, on_done=None):
        command = [sys.executable, str(CLI)] + args
        self.append_log("> " + " ".join(command))

        def worker():
            proc = subprocess.run(command, cwd=str(ROOT.parent), text=True, capture_output=True)
            output = (proc.stdout or "") + (proc.stderr or "")
            self.after(0, lambda: self._finish_command(proc.returncode, output, on_done))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_command(self, code, output, on_done):
        if output.strip():
            self.append_log(output.strip())
        if code != 0:
            self.append_log(f"Command failed: exit {code}")
        if on_done:
            on_done(code)

    def refresh_all(self):
        cfg = ownskin.load_config()
        self.game_path.set(cfg.get("game_path", ""))
        self.mod_tools.set(cfg.get("mod_tools", ""))
        self.pengu_loader.set(cfg.get("pengu_loader", ""))
        self.machine_id.set(ownskin.get_machine_id())
        self.refresh_mods()

    def refresh_mods(self):
        self.mods_list.delete(0, "end")
        ownskin.ensure_dirs()
        for mod in sorted(p for p in ownskin.MODS_DIR.iterdir() if p.is_dir()):
            manifest = ownskin.read_json(mod / "ownskin.manifest.json", {})
            label = mod.name + (" [licensed]" if manifest.get("license_required") else "")
            self.mods_list.insert("end", label)

    def on_mod_select(self, _event=None):
        selected = self.mods_list.curselection()
        if not selected:
            self.selected_mod.set("")
            return
        label = self.mods_list.get(selected[0])
        self.selected_mod.set(label.split(" ", 1)[0])

    def require_selected_mod(self):
        mod = self.selected_mod.get()
        if not mod:
            messagebox.showwarning("OwnSkinTool", "Select a mod first.")
            return ""
        return mod

    def browse_game_path(self):
        path = filedialog.askdirectory(title="Select League Game folder")
        if path:
            self.game_path.set(path)

    def browse_mod_tools(self):
        path = filedialog.askopenfilename(title="Select mod-tools.exe", filetypes=[("EXE", "*.exe"), ("All files", "*.*")])
        if path:
            self.mod_tools.set(path)

    def browse_pengu(self):
        path = filedialog.askopenfilename(title="Select Pengu Loader.exe", filetypes=[("EXE", "*.exe"), ("All files", "*.*")])
        if path:
            self.pengu_loader.set(path)

    def save_paths(self):
        args = [
            "init",
            "--game-path", self.game_path.get(),
            "--mod-tools", self.mod_tools.get(),
            "--pengu-loader", self.pengu_loader.get(),
        ]
        self.run_cli(args, lambda _code: self.refresh_all())

    def import_mod(self):
        path = filedialog.askopenfilename(
            title="Import mod archive",
            filetypes=[("Mod archives", "*.zip *.fantome"), ("All files", "*.*")],
        )
        if not path:
            folder = filedialog.askdirectory(title="Or select extracted mod folder")
            path = folder
        if not path:
            return
        default_name = ownskin.safe_name(Path(path).stem)
        name = simpledialog.askstring("Mod name", "Name for this mod:", initialvalue=default_name)
        if not name:
            return
        self.run_cli(["import", path, "--name", name, "--force"], lambda _code: self.refresh_mods())

    def import_cache(self):
        skin_id = simpledialog.askstring("Skin ID", "Enter cached skin ID, for example 39037:")
        if not skin_id:
            return
        name = simpledialog.askstring("Mod name", "Name for this cached skin:", initialvalue=f"skin_{skin_id}")
        if not name:
            return
        self.run_cli(["import-cache", skin_id, "--name", name, "--force"], lambda _code: self.refresh_mods())

    def quick_run_cache(self):
        skin_id = simpledialog.askstring("Quick Run Skin ID", "Enter cached skin ID, for example 39037:")
        if not skin_id:
            return
        self.quick_run_skin_id(skin_id)

    def open_skin_browser(self):
        win = tk.Toplevel(self)
        win.title("Cached Skin Browser")
        win.geometry("760x520")
        win.minsize(620, 400)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(2, weight=1)

        search = tk.StringVar()
        ttk.Label(win, text="Search").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        entry = ttk.Entry(win, textvariable=search)
        entry.grid(row=1, column=0, sticky="ew", padx=10)

        columns = ("id", "name", "author")
        tree = ttk.Treeview(win, columns=columns, show="headings", selectmode="browse")
        tree.heading("id", text="ID")
        tree.heading("name", text="Name")
        tree.heading("author", text="Author")
        tree.column("id", width=90, stretch=False)
        tree.column("name", width=380)
        tree.column("author", width=160)
        tree.grid(row=2, column=0, sticky="nsew", padx=10, pady=8)

        scroll = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        scroll.grid(row=2, column=1, sticky="ns", pady=8)
        tree.configure(yscrollcommand=scroll.set)

        status = tk.StringVar(value="Loading cached skins...")
        ttk.Label(win, textvariable=status).grid(row=3, column=0, sticky="w", padx=10)

        footer = ttk.Frame(win, padding=10)
        footer.grid(row=4, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)

        state = {"skins": []}

        def selected_skin_id():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("OwnSkinTool", "Select a skin first.", parent=win)
                return ""
            return tree.item(selected[0], "values")[0]

        def quick_run_selected():
            skin_id = selected_skin_id()
            if skin_id:
                self.quick_run_skin_id(skin_id)

        def import_selected():
            skin_id = selected_skin_id()
            if skin_id:
                self.run_cli(["import-cache", skin_id, "--name", f"skin_{skin_id}", "--force"], lambda _code: self.refresh_mods())

        ttk.Button(footer, text="Import", command=import_selected).grid(row=0, column=1, padx=3)
        ttk.Button(footer, text="Run Selected", command=quick_run_selected).grid(row=0, column=2, padx=3)
        ttk.Button(footer, text="Close", command=win.destroy).grid(row=0, column=3, padx=3)

        def populate(items):
            tree.delete(*tree.get_children())
            for skin in items:
                tree.insert("", "end", values=(skin.get("id", ""), skin.get("name", ""), skin.get("author", "")))
            status.set(f"{len(items)} skins shown")

        def apply_filter(_event=None):
            term = search.get().lower().strip()
            if not term:
                populate(state["skins"])
                return
            filtered = [
                skin for skin in state["skins"]
                if term in f"{skin.get('id', '')} {skin.get('name', '')} {skin.get('author', '')} {' '.join(skin.get('aliases') or [])}".lower()
            ]
            populate(filtered)

        def worker():
            try:
                skins = ownskin.list_cached_skins()
            except Exception as exc:
                self.after(0, lambda: status.set(f"Failed to load cache: {exc}"))
                return
            self.after(0, lambda: state.update({"skins": skins}))
            self.after(0, lambda: populate(skins))

        entry.bind("<KeyRelease>", apply_filter)
        tree.bind("<Double-1>", lambda _event: quick_run_selected())
        entry.focus_set()
        threading.Thread(target=worker, daemon=True).start()

    def quick_run_skin_id(self, skin_id):
        name = f"skin_{skin_id}"

        def after_import(code):
            self.refresh_mods()
            if code == 0:
                self.run_cli(["run", name])

        self.run_cli(["import-cache", skin_id, "--name", name, "--force"], after_import)

    def build_mod(self):
        mod = self.require_selected_mod()
        if mod:
            self.run_cli(["build", mod])

    def run_mod(self):
        mod = self.require_selected_mod()
        if mod:
            self.run_cli(["run", mod])

    def package_mod(self):
        mod = self.require_selected_mod()
        if not mod:
            return
        output = filedialog.asksaveasfilename(
            title="Save OwnSkin package",
            defaultextension=".ownskin.zip",
            initialfile=f"{mod}-{self.package_version.get()}.ownskin.zip",
            filetypes=[("OwnSkin package", "*.zip"), ("All files", "*.*")],
        )
        if not output:
            return
        args = ["package", mod, "--version", self.package_version.get(), "--output", output]
        if self.package_license_required.get():
            args.append("--license-required")
        self.run_cli(args, lambda _code: self.refresh_mods())

    def create_license(self):
        mod = self.require_selected_mod()
        if not mod:
            return
        output = filedialog.asksaveasfilename(
            title="Save license",
            defaultextension=".license.json",
            initialfile=f"{mod}.license.json",
            filetypes=[("License", "*.json"), ("All files", "*.*")],
        )
        if not output:
            return
        args = ["license-create", mod, "--buyer", self.buyer.get(), "--output", output]
        if self.machine_id.get():
            args += ["--machine-id", self.machine_id.get()]
        self.run_cli(args)

    def activate_license(self):
        path = filedialog.askopenfilename(title="Select license file", filetypes=[("License", "*.json"), ("All files", "*.*")])
        if path:
            self.run_cli(["license-activate", path], lambda _code: self.refresh_mods())

    def export_public_key(self):
        output = filedialog.asksaveasfilename(
            title="Export public key",
            defaultextension=".json",
            initialfile="vendor_public_key.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if output:
            self.run_cli(["vendor-public-key", "--output", output])

    def import_public_key(self):
        path = filedialog.askopenfilename(title="Import vendor public key", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            self.run_cli(["vendor-public-key-import", path])


def main():
    app = OwnSkinGui()
    app.mainloop()


if __name__ == "__main__":
    main()
