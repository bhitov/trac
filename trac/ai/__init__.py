# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

"""AI Chatbot plugin for Trac - provides intelligent Q&A about tickets."""

from trac.ai.context_service import ContextService
from trac.ai.search_service import FuzzySearchService
from trac.ai.chat_handler import ChatHandler

__all__ = ['ContextService', 'FuzzySearchService', 'ChatHandler']