# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) <YEAR> <AUTHOR>

NAME     := netpulse
VERSION  := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/netpulse/__init__.py)
SPEC     := packaging/$(NAME).spec
BUILD    := $(CURDIR)/build
TOPDIR   := $(BUILD)/rpmbuild
TARBALL  := $(TOPDIR)/SOURCES/$(NAME)-$(VERSION).tar.gz
RPMDEFS  := --define "_topdir $(TOPDIR)"
PYTHON   ?= python3
MOCKCFG  ?= fedora-$(shell rpm -E %fedora)-x86_64

.PHONY: help run test test-network lint tarball srpm rpm mock clean set-author

help:
	@echo "make run           start NetPulse from the source tree (browser mode, prints URL)"
	@echo "make test          run the offline test suite"
	@echo "make test-network  also run tests that need real network access"
	@echo "make lint          ruff + SPDX header check + rpmlint on the spec"
	@echo "make tarball       git archive of HEAD into build/rpmbuild/SOURCES"
	@echo "make srpm / rpm    build source / noarch RPM under build/rpmbuild"
	@echo "make mock          clean build of the SRPM in mock ($(MOCKCFG))"
	@echo "make set-author AUTHOR='Name' YEAR=2026 EMAIL=you@example.org   fill in placeholders"

run:
	PYTHONPATH=src $(PYTHON) -m netpulse $(ARGS)

test:
	$(PYTHON) -m pytest -q

test-network:
	NETPULSE_NETWORK_TESTS=1 $(PYTHON) -m pytest -q

lint:
	ruff check src tests
	ruff format --check src tests
	$(PYTHON) tests/check_headers.py
	@# spec + built packages in one run (packaging/netpulse.rpmlintrc is loaded automatically)
	@if ls $(TOPDIR)/SRPMS/*.src.rpm $(TOPDIR)/RPMS/noarch/*.rpm >/dev/null 2>&1; then \
		echo "rpmlint $(SPEC) + built packages"; \
		rpmlint -r packaging/netpulse.rpmlintrc $(SPEC) $(TOPDIR)/SRPMS/*.src.rpm $(TOPDIR)/RPMS/noarch/*.rpm; \
	else \
		echo "rpmlint $(SPEC) (no packages built yet: run make rpm)"; \
		rpmlint --ignore-unused-rpmlintrc $(SPEC); \
	fi

tarball:
	@git diff --quiet HEAD -- || echo "warning: uncommitted changes are NOT in the tarball"
	mkdir -p $(TOPDIR)/SOURCES
	git archive --format=tar.gz --prefix=$(NAME)-$(VERSION)/ -o $(TARBALL) HEAD

srpm: tarball
	rpmbuild $(RPMDEFS) -bs $(SPEC)

rpm: tarball
	rpmbuild $(RPMDEFS) -ba $(SPEC)
	@ls -1 $(TOPDIR)/RPMS/noarch/*.rpm

mock: srpm
	mock -r $(MOCKCFG) --resultdir=$(BUILD)/mock $(TOPDIR)/SRPMS/$(NAME)-$(VERSION)-*.src.rpm
	@ls -1 $(BUILD)/mock/*.rpm

set-author:
	@test -n "$(AUTHOR)" -a -n "$(YEAR)" -a -n "$(EMAIL)" || \
		{ echo "usage: make set-author AUTHOR='Name' YEAR=2026 EMAIL=you@example.org"; exit 1; }
	git ls-files -z -- . ':!Makefile' ':!CLAUDE.md' | \
		xargs -0 grep -lZ -e '<AUTHOR>' -e '<YEAR>' -e '<CONTACT_EMAIL>' | \
		xargs -0 -r sed -i -e 's/<AUTHOR>/$(AUTHOR)/g' -e 's/<YEAR>/$(YEAR)/g' \
			-e 's/<CONTACT_EMAIL>/$(EMAIL)/g'

clean:
	rm -rf $(BUILD) dist .pytest_cache .ruff_cache src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
