# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    # Python < 3.8 fallback
    from pkg_resources import get_distribution, DistributionNotFound as PackageNotFoundError
    def version(name):
        return get_distribution(name).version

try:
    __version__ = version('Trac')
except PackageNotFoundError:
    __version__ = '1.7.1'

# Import auth modules to ensure component registration
try:
    from . import auth
    # Force import of clerk module for component discovery
    from .auth import clerk
except ImportError:
    pass
