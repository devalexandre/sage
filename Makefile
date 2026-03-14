VENV    := .venv
PYTHON_BIN ?= python3.12
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
APPNAME := sage
VERSION := 0.1.3
PKGREL  := 5

.PHONY: help setup build build-linux build-windows build-deb build-arch install run icon clean

help:           ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup:          ## Create venv and install all dependencies
	@PYTHON_BIN=$$(command -v $(PYTHON_BIN)); \
		if [ -z "$$PYTHON_BIN" ]; then \
			echo "✗ $(PYTHON_BIN) not found. Install Python 3.12 or run 'make setup PYTHON_BIN=/path/to/python3.12'."; \
			exit 1; \
		fi; \
		$$PYTHON_BIN -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]" 2>/dev/null || $(PIP) install -e .
	@echo "✓ Setup complete. Run: make run"

check-python:   ## Ensure local build uses a supported Python for Nuitka
	@$(PYTHON) -c 'import sys; v=sys.version_info; \
		assert v[:2] in ((3, 12), (3, 13)), \
		f"Python {v.major}.{v.minor} detected in .venv; use Python 3.12 or 3.13 for Nuitka builds."'

# ── wheel (source distribution) ──────────────────────────────────────────────
build:          ## Build the wheel — dist/sage-*.whl  (code is readable)
	$(PIP) install --quiet build
	$(PYTHON) -m build --wheel
	@echo "✓ Wheel written to dist/"

install:        ## Install the wheel from dist/ into the venv
	$(PIP) install dist/*.whl --force-reinstall

# ── icon ──────────────────────────────────────────────────────────────────────
icon:           ## Generate assets/sage.png and assets/sage.ico
	$(PIP) install --quiet pillow
	$(PYTHON) packaging/generate_icon.py

# ── Linux binary + AppImage ───────────────────────────────────────────────────
build-linux:    ## Build Linux AppImage via Nuitka + appimagetool
	@$(MAKE) check-python
	@command -v patchelf >/dev/null 2>&1 || { \
		echo "✗ patchelf not found. Install with:"; \
		echo "  Arch:   sudo pacman -S patchelf"; \
		echo "  Ubuntu: sudo apt install patchelf"; \
		exit 1; \
	}
	@command -v appimagetool >/dev/null 2>&1 || { \
		echo "✗ appimagetool not found."; \
		echo "  Download: https://github.com/AppImage/AppImageKit/releases"; \
		echo "  Then:     sudo install -m755 appimagetool-x86_64.AppImage /usr/local/bin/appimagetool"; \
		exit 1; \
	}
	$(MAKE) icon
	$(PIP) install --quiet nuitka ordered-set zstandard
	$(PYTHON) -m nuitka \
		--onefile \
		--enable-plugin=pyside6 \
		--include-package=core \
		--include-package=ui \
		--include-package=db \
		--include-package=pynput \
		--output-dir=dist \
		--output-filename=$(APPNAME) \
		--linux-icon=assets/sage.png \
		app.py
	@echo "Packaging AppImage..."
	@rm -rf packaging/linux/sage.AppDir/usr
	@mkdir -p packaging/linux/sage.AppDir/usr/bin
	@cp dist/$(APPNAME) packaging/linux/sage.AppDir/usr/bin/$(APPNAME)
	@chmod +x packaging/linux/sage.AppDir/usr/bin/$(APPNAME)
	@cp assets/sage.png packaging/linux/sage.AppDir/sage.png
	@ARCH=x86_64 appimagetool packaging/linux/sage.AppDir dist/Sage-$(VERSION)-x86_64.AppImage
	@echo ""
	@echo "✓ Binary    → dist/$(APPNAME)"
	@echo "✓ AppImage  → dist/Sage-$(VERSION)-x86_64.AppImage"
	@if command -v makepkg >/dev/null 2>&1; then \
		echo ""; \
		$(MAKE) build-arch; \
	fi

# ── Windows binary + installer ────────────────────────────────────────────────
build-windows:  ## Build Windows installer via Nuitka + Inno Setup  (run on Windows)
	@$(MAKE) check-python
	$(MAKE) icon
	$(PIP) install --quiet nuitka ordered-set zstandard
	$(PYTHON) -m nuitka \
		--onefile \
		--enable-plugin=pyside6 \
		--include-package=core \
		--include-package=ui \
		--include-package=db \
		--output-dir=dist \
		--output-filename=$(APPNAME).exe \
		--windows-icon-from-ico=assets/sage.ico \
		--windows-disable-console \
		app.py
	@echo "Building installer with Inno Setup..."
	@iscc packaging/windows/sage.iss
	@echo ""
	@echo "✓ Binary    → dist/$(APPNAME).exe"
	@echo "✓ Installer → dist/Sage-$(VERSION)-Setup.exe"

# ── .deb package ─────────────────────────────────────────────────────────────
build-deb:      ## Build .deb package for Debian/Ubuntu
	@test -f dist/$(APPNAME) || { echo "✗ dist/$(APPNAME) not found. Run 'make build-linux' first."; exit 1; }
	@command -v dpkg-deb >/dev/null 2>&1 || { \
		echo "✗ dpkg-deb not found. Install with:"; \
		echo "  Arch:   sudo pacman -S dpkg"; \
		echo "  Ubuntu: (already installed)"; \
		exit 1; \
	}
	@echo "Building .deb package..."
	@rm -rf dist/deb-staging
	@mkdir -p dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/DEBIAN
	@mkdir -p dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/usr/bin
	@mkdir -p dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/usr/share/applications
	@mkdir -p dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/usr/share/icons/hicolor/512x512/apps
	@cp dist/$(APPNAME) dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/usr/bin/$(APPNAME)
	@chmod 755 dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/usr/bin/$(APPNAME)
	@cp assets/sage.png dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/usr/share/icons/hicolor/512x512/apps/sage.png
	@cp packaging/linux/sage.AppDir/sage.desktop dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/usr/share/applications/sage.desktop
	@INSTALLED_SIZE=$$(du -sk dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/usr | awk '{print $$1}'); \
		sed -e 's/__VERSION__/$(VERSION)/' \
		    -e "s/__INSTALLED_SIZE__/$$INSTALLED_SIZE/" \
		    packaging/linux/deb/control.in > dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/DEBIAN/control
	@cp packaging/linux/deb/postinst dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/DEBIAN/postinst
	@cp packaging/linux/deb/postrm dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/DEBIAN/postrm
	@chmod 755 dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/DEBIAN/postinst
	@chmod 755 dist/deb-staging/$(APPNAME)_$(VERSION)_amd64/DEBIAN/postrm
	@dpkg-deb --build --root-owner-group dist/deb-staging/$(APPNAME)_$(VERSION)_amd64 dist/$(APPNAME)_$(VERSION)_amd64.deb
	@rm -rf dist/deb-staging
	@echo ""
	@echo "✓ .deb      → dist/$(APPNAME)_$(VERSION)_amd64.deb"

# ── Arch Linux package ───────────────────────────────────────────────────────
build-arch:     ## Build Arch Linux package (.pkg.tar.zst)
	@test -f dist/$(APPNAME) || { echo "✗ dist/$(APPNAME) not found. Run 'make build-linux' first."; exit 1; }
	@command -v makepkg >/dev/null 2>&1 || { echo "✗ makepkg not found. This target requires Arch Linux (pacman)."; exit 1; }
	@echo "Building Arch package..."
	@rm -rf dist/arch-staging
	@mkdir -p dist/arch-staging
	@cp packaging/linux/arch/PKGBUILD dist/arch-staging/
	@cp packaging/linux/arch/sage.install dist/arch-staging/
	@sed -i \
		-e 's/^pkgver=.*/pkgver=$(VERSION)/' \
		-e 's/^pkgrel=.*/pkgrel=$(PKGREL)/' \
		dist/arch-staging/PKGBUILD
	@cp dist/$(APPNAME) dist/arch-staging/$(APPNAME)
	@cp assets/sage.png dist/arch-staging/sage.png
	@cp packaging/linux/sage.AppDir/sage.desktop dist/arch-staging/sage.desktop
	@cd dist/arch-staging && makepkg -f
	@cp dist/arch-staging/$(APPNAME)-$(VERSION)-$(PKGREL)-x86_64.pkg.tar.zst dist/
	@rm -rf dist/arch-staging
	@echo ""
	@echo "✓ Arch pkg  → dist/$(APPNAME)-$(VERSION)-$(PKGREL)-x86_64.pkg.tar.zst"

# ── dev ───────────────────────────────────────────────────────────────────────
run:            ## Run Sage in development mode
	PYTHONPATH=. $(PYTHON) app.py

clean:          ## Remove all build artifacts
	rm -rf dist/ build/ *.egg-info/ __pycache__/ *.spec.bak
	find . -name "*.pyc" -delete
