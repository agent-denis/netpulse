# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>
"""Native window: GTK 4 + WebKitGTK 6.0 via PyGObject (optional).

The window shows the same local web UI as the browser mode. It follows the
desktop's dark-style preference (libadwaita if present, otherwise the GNOME
``color-scheme`` setting), unless the user picked Light or Dark in the app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from netpulse import APP_ID, APP_NAME

if TYPE_CHECKING:
    from netpulse.server import App

_GI: dict[str, Any] = {}


def _load() -> bool:
    """Import the GTK/WebKit bindings once. False if they are not usable."""
    if _GI:
        return _GI.get("ok", False)
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("WebKit", "6.0")
        from gi.repository import Gio, GLib, Gtk, WebKit

        _GI.update(Gio=Gio, GLib=GLib, Gtk=Gtk, WebKit=WebKit, Adw=None)
        try:
            gi.require_version("Adw", "1")
            from gi.repository import Adw

            _GI["Adw"] = Adw
        except (ImportError, ValueError):
            pass
        _GI["ok"] = True
    except (ImportError, ValueError):
        _GI["ok"] = False
    return _GI["ok"]


def available() -> bool:
    """A native window is possible: bindings installed and a display to draw on."""
    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        return False
    return _load()


class _Theme:
    """Keeps GTK (and therefore WebKit's prefers-color-scheme) in line with the user's choice."""

    def __init__(self) -> None:
        self.Gtk = _GI["Gtk"]
        self.Gio = _GI["Gio"]
        self.Adw = _GI["Adw"]
        self.pref = "system"
        self.gsettings = None
        if self.Adw is None:
            source = self.Gio.SettingsSchemaSource.get_default()
            schema = source.lookup("org.gnome.desktop.interface", True) if source else None
            if schema is not None and schema.has_key("color-scheme"):
                self.gsettings = self.Gio.Settings.new("org.gnome.desktop.interface")
                self.gsettings.connect("changed::color-scheme", lambda *_: self.apply())

    def desktop_prefers_dark(self) -> bool:
        if self.gsettings is not None:
            return bool(self.gsettings.get_string("color-scheme") == "prefer-dark")
        return False

    def set(self, pref: str) -> None:
        if pref in ("system", "light", "dark"):
            self.pref = pref
            self.apply()

    def apply(self) -> None:
        if self.Adw is not None:
            manager = self.Adw.StyleManager.get_default()
            scheme = {
                "system": self.Adw.ColorScheme.DEFAULT,
                "light": self.Adw.ColorScheme.FORCE_LIGHT,
                "dark": self.Adw.ColorScheme.FORCE_DARK,
            }[self.pref]
            manager.set_color_scheme(scheme)
            return
        dark = self.pref == "dark" or (self.pref == "system" and self.desktop_prefers_dark())
        settings = self.Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", dark)


def run(app: App) -> int:
    """Open the window and run the GTK main loop until it is closed."""
    if not _load():
        raise RuntimeError("GTK 4 / WebKitGTK 6.0 bindings are not available")
    Gio, GLib, Gtk, WebKit, Adw = (_GI[k] for k in ("Gio", "GLib", "Gtk", "WebKit", "Adw"))
    GLib.set_prgname(APP_ID)
    GLib.set_application_name(APP_NAME)
    application_cls = Adw.Application if Adw is not None else Gtk.Application
    gtk_app = application_cls(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
    state: dict[str, Any] = {}

    def on_activate(application: Any) -> None:
        if "window" in state:
            state["window"].present()
            return
        theme = _Theme()
        theme.set(app.settings.get().get("theme", "system"))

        # Ephemeral session: the web view keeps no cookies, cache or storage on disk.
        session = WebKit.NetworkSession.new_ephemeral()
        content = WebKit.UserContentManager()
        content.register_script_message_handler("netpulse", None)

        def on_message(_mgr: Any, value: Any) -> None:
            try:
                data = value.to_json(0)
            except (AttributeError, GLib.Error):
                return
            import json

            try:
                msg = json.loads(data)
            except ValueError:
                return
            if isinstance(msg, dict) and msg.get("type") == "theme":
                theme.set(str(msg.get("value")))

        content.connect("script-message-received::netpulse", on_message)
        view = WebKit.WebView(network_session=session, user_content_manager=content)
        settings = view.get_settings()
        settings.set_enable_developer_extras(bool(os.environ.get("NETPULSE_DEVTOOLS")))
        settings.set_javascript_can_open_windows_automatically(False)
        settings.set_enable_back_forward_navigation_gestures(False)

        origin = app.url.rstrip("/")

        def on_policy(_view: Any, decision: Any, kind: Any) -> bool:
            # Only our own pages load inside the window; anything else opens externally.
            if kind in (
                WebKit.PolicyDecisionType.NAVIGATION_ACTION,
                WebKit.PolicyDecisionType.NEW_WINDOW_ACTION,
            ):
                uri = decision.get_navigation_action().get_request().get_uri() or ""
                if uri.startswith(origin + "/") or uri == origin or uri.startswith("blob:"):
                    if kind == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
                        decision.ignore()
                        return True
                    return False
                decision.ignore()
                if uri.startswith(("http://", "https://")):
                    Gtk.UriLauncher.new(uri).launch(state.get("window"), None, None, None)
                return True
            return False

        view.connect("decide-policy", on_policy)

        def on_download(_session: Any, download: Any) -> None:
            def decide(dl: Any, suggested: str) -> bool:
                dialog = Gtk.FileDialog(title="Export result", initial_name=suggested)
                downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
                if downloads:
                    dialog.set_initial_folder(Gio.File.new_for_path(downloads))

                def done(dlg: Any, result: Any) -> None:
                    try:
                        target = dlg.save_finish(result)
                    except GLib.Error:
                        dl.cancel()
                        return
                    dl.set_allow_overwrite(True)
                    dl.set_destination(target.get_path())

                dialog.save(state.get("window"), None, done)
                return True

            download.connect("decide-destination", decide)

        session.connect("download-started", on_download)

        window = Gtk.ApplicationWindow(application=application, title=APP_NAME)
        window.set_default_size(1180, 820)
        window.set_size_request(900, 560)
        window.set_icon_name(APP_ID)
        window.set_child(view)
        state["window"] = window
        state["view"] = view

        snapshot = os.environ.get("NETPULSE_WINDOW_SNAPSHOT")  # development self-check
        if snapshot:
            _arm_snapshot(view, snapshot, gtk_app)

        view.load_uri(app.launch_url)
        window.present()

    def present() -> None:
        def raise_window() -> bool:
            if "window" in state:
                state["window"].present()
            return False

        GLib.idle_add(raise_window)

    app.on_present = present
    gtk_app.connect("activate", on_activate)

    # Python signal handlers don't run while GTK waits in C; let GLib deliver them.
    import signal

    def on_signal() -> bool:
        gtk_app.quit()
        return False

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, on_signal)
    quit_action = Gio.SimpleAction.new("quit", None)
    quit_action.connect("activate", lambda *_: gtk_app.quit())
    gtk_app.add_action(quit_action)
    gtk_app.set_accels_for_action("app.quit", ["<Control>q"])
    gtk_app.set_accels_for_action("window.close", ["<Control>w"])
    return int(gtk_app.run([sys.argv[0]]))


def _arm_snapshot(view: Any, path: str, gtk_app: Any) -> None:
    """Save a PNG of the page a few seconds after it loaded, then quit (for testing)."""
    GLib, WebKit = _GI["GLib"], _GI["WebKit"]

    def take() -> bool:
        def done(v: Any, result: Any) -> None:
            texture = v.get_snapshot_finish(result)
            texture.save_to_png(str(Path(path)))
            gtk_app.quit()

        view.get_snapshot(WebKit.SnapshotRegion.VISIBLE, WebKit.SnapshotOptions.NONE, None, done)
        return False

    def on_load(v: Any, event: Any) -> None:
        if event == WebKit.LoadEvent.FINISHED:
            GLib.timeout_add(2500, take)

    view.connect("load-changed", on_load)
