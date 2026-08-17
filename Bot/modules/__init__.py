from os.path import dirname, basename, isfile, join
import glob
from Bot import LOGGER

modules = glob.glob(join(dirname(__file__), "*.py"))
__all__ = [ basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py')]

LOGGER.info(f"{len(__all__)} MODULES LOADED!")