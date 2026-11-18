# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>

%global app_id io.github.agent_denis.NetPulse

Name:           netpulse
Version:        1.0.0
Release:        1%{?dist}
Summary:        Network diagnostics GUI for ping, traceroute, DNS, HTTP and TLS checks

License:        GPL-3.0-or-later
URL:            https://github.com/agent-denis/netpulse
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-pytest
BuildRequires:  desktop-file-utils
BuildRequires:  appstream

Requires:       python3
Requires:       iputils
Requires:       bind-utils
# stdbuf (line-buffered tracepath output)
Requires:       coreutils

Recommends:     traceroute
Recommends:     mtr
Recommends:     whois
Recommends:     curl
Recommends:     openssl
Recommends:     iproute
Recommends:     systemd-resolved
# Native window; without these NetPulse opens in the web browser.
Recommends:     python3-gobject
Recommends:     webkitgtk6.0
Suggests:       libadwaita

%description
NetPulse is a local, single-user network diagnostics tool with a calm graphical
interface. It runs the real system tools (ping, traceroute, mtr, dig, nslookup,
host, whois, curl, openssl, ip, ss and resolvectl), streams their output live
and shows a parsed summary: an RTT chart for ping, hop tables for traceroute
and MTR, DNS sections and resolver comparisons, an HTTP timing breakdown, TLS
certificate details, TCP port checks, local network information, a subnet
calculator and a one-page quick diagnosis.

The interface is served on the loopback interface only, protected by a
per-launch token, and opens in a native GTK window or the default browser.
Missing optional tools are shown with the command to install them.


%prep
%autosetup -p1


%generate_buildrequires
%pyproject_buildrequires


%build
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files -l netpulse

install -Dpm 0644 data/%{app_id}.desktop \
    %{buildroot}%{_datadir}/applications/%{app_id}.desktop
install -Dpm 0644 data/%{app_id}.metainfo.xml \
    %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml
install -Dpm 0644 data/icons/hicolor/scalable/apps/%{app_id}.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
install -Dpm 0644 data/icons/hicolor/symbolic/apps/%{app_id}-symbolic.svg \
    %{buildroot}%{_datadir}/icons/hicolor/symbolic/apps/%{app_id}-symbolic.svg
install -Dpm 0644 data/netpulse.1 %{buildroot}%{_mandir}/man1/netpulse.1


%check
desktop-file-validate %{buildroot}%{_datadir}/applications/%{app_id}.desktop
appstreamcli validate --no-net %{buildroot}%{_metainfodir}/%{app_id}.metainfo.xml
%pyproject_check_import
# Test the installed package (not src/); tests needing the network are skipped.
%pytest -o pythonpath= -p no:cacheprovider


%files -f %{pyproject_files}
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/netpulse
%{_datadir}/applications/%{app_id}.desktop
%{_metainfodir}/%{app_id}.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
%{_datadir}/icons/hicolor/symbolic/apps/%{app_id}-symbolic.svg
%{_mandir}/man1/netpulse.1*


%changelog
* Wed Nov 18 2026 NetPulse contributors <noreply@github.com> - 1.0.0-1
- First release
