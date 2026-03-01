VENV    := .venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
APPNAME := sage
VERSION := 0.1.0

.PHONY: help setup build build-linux build-windows install run icon clean

help:           ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup:          ## Create venv and install all dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]" 2>/dev/null || $(PIP) install -e .
	@echo "✓ Setup complete. Run: make run"

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

# ── Windows binary + installer ────────────────────────────────────────────────
build-windows:  ## Build Windows installer via Nuitka + Inno Setup  (run on Windows)
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

# ── dev ───────────────────────────────────────────────────────────────────────
run:            ## Run Sage in development mode
	PYTHONPATH=. $(PYTHON) app.py

clean:          ## Remove all build artifacts
	rm -rf dist/ build/ *.egg-info/ __pycache__/ *.spec.bak
	find . -name "*.pyc" -delete
