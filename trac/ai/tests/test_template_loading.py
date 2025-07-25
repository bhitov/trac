# -*- coding: utf-8 -*-
"""Test template loading issues."""

import os
import sys

def test_template_paths():
    """Check where templates should be located."""
    from trac.ai.chat_handler import ChatHandler
    from trac.test import EnvironmentStub
    
    env = EnvironmentStub(enable=['trac.ai.*'])
    handler = ChatHandler(env)
    
    print("\nTemplate loading test:")
    print("======================")
    
    # Get template directories
    template_dirs = handler.get_templates_dirs()
    print(f"\nTemplate directories returned by handler:")
    for d in template_dirs:
        print(f"  - {d}")
        print(f"    Exists: {os.path.exists(d)}")
        if os.path.exists(d):
            files = os.listdir(d)
            print(f"    Files: {files}")
    
    # Check if templates are in the expected location
    import trac.ai
    ai_module_path = os.path.dirname(trac.ai.__file__)
    expected_template_dir = os.path.join(ai_module_path, 'templates')
    
    print(f"\nExpected template directory:")
    print(f"  {expected_template_dir}")
    print(f"  Exists: {os.path.exists(expected_template_dir)}")
    
    if os.path.exists(expected_template_dir):
        files = os.listdir(expected_template_dir)
        print(f"  Files: {files}")
    
    # Check ai_chat.html specifically
    template_file = os.path.join(expected_template_dir, 'ai_chat.html')
    print(f"\nChecking ai_chat.html:")
    print(f"  Path: {template_file}")
    print(f"  Exists: {os.path.exists(template_file)}")
    if os.path.exists(template_file):
        print(f"  Size: {os.path.getsize(template_file)} bytes")

if __name__ == '__main__':
    test_template_paths()