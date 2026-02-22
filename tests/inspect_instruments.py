from nautilus_trader.test_kit.providers import TestInstrumentProvider
import inspect

print("Available in TestInstrumentProvider:")
methods = [m for m in dir(TestInstrumentProvider) if not m.startswith('_')]
for m in methods:
    print(f"- {m}")
