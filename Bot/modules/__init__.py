import glob
import importlib
from os.path import basename, dirname, isfile, join
from Bot import LOGGER

modules = glob.glob(join(dirname(__file__), "*.py"))
module_names = [basename(f)[:-3] for f in modules if isfile(f) and not f.endswith("__init__.py")]

LOADED_MODULES = []
FAILED_MODULES = {}

for modname in module_names:
    try:
        importlib.import_module(f"Bot.modules.{modname}")
        LOADED_MODULES.append(modname)
    except Exception as e:
        LOGGER.error(f"Failed to load module 'Bot.modules.{modname}': {e}", exc_info=True)
        FAILED_MODULES[modname] = str(e)

LOGGER.info(f"{len(LOADED_MODULES)} MODULES LOADED! (Failed: {len(FAILED_MODULES)})")
__all__ = LOADED_MODULES