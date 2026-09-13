"""Compatibility module for :mod:`sawopt.studies.convergence`."""
import importlib
import sys
import types

_impl = importlib.import_module('..studies.convergence', __package__)


class _CompatModule(types.ModuleType):
    def __getattr__(self, name):
        return getattr(_impl, name)

    def __setattr__(self, name, value):
        if name in {'_impl', '__all__', '__doc__', '__file__', '__loader__', '__package__', '__spec__'}:
            return super().__setattr__(name, value)
        setattr(_impl, name, value)

    def __delattr__(self, name):
        if name in self.__dict__:
            return super().__delattr__(name)
        delattr(_impl, name)


_proxy = _CompatModule(__name__, __doc__)
_proxy.__all__ = [name for name in dir(_impl) if not name.startswith('_')]
_proxy.__file__ = __file__
_proxy.__package__ = __package__
_proxy.__spec__ = __spec__
_proxy._impl = _impl
sys.modules[__name__] = _proxy

if __name__ == '__main__':
    _impl.main()
