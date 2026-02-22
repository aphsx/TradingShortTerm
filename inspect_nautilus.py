import nautilus_trader
import pkgutil
import os

print(f"NautilusTrader version: {getattr(nautilus_trader, '__version__', 'unknown')}")
print(f"Path: {nautilus_trader.__path__}")

print("\nSubmodules:")
for loader, module_name, is_pkg in pkgutil.walk_packages(nautilus_trader.__path__):
    if is_pkg:
        print(f"- {module_name} (package)")
    else:
        print(f"- {module_name}")
